"""Chunked map-reduce analysis for groq.

Groq's per-request token limit (free tier ≈ 12k TPM) can't hold a large
or multi-transcript analyze prompt in one shot — the request 413s and the
caller's fallback chain silently switches to another backend. This module
keeps the work ON groq by splitting it:

  map:    summarize each transcript. A single transcript larger than the
          per-call budget is itself split into sequential max-size chunks.
  reduce: one final call applying the user's prompt to the summaries. If
          the assembled summaries still exceed the budget they are
          collapsed in groups (extra condense calls) until they fit.

For NON-groq backends, or when the normal single-shot prompt already fits
the budget, this transparently falls through to the existing
`build_prompt` + `run_analysis` path — one call, no behaviour change.
"""
from __future__ import annotations
from skills.neurolearn.constants import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

from typing import Callable

from skills.neurolearn.analyze import runner
from skills.neurolearn.analyze.prompt_builder import (
    SYSTEM_PROMPT, build_prompt, _transcript_body, _video_header,
)
from skills.neurolearn.analyze.source_resolver import VideoSource

# Groq free-tier limit is 12_000 tokens per request. A conservative
# upper-bound token density across EN/RU transcripts is ≈ 0.75 tok/char,
# and we leave headroom for the output, so cap each request's INPUT at
# ~12_000 chars (~9k tokens). Verified empirically 2026-05-27: ~22k-char
# (≈10k token) requests pass, ~32k-char (≈14k token) requests 413.
MAX_INPUT_CHARS = 12_000

_HUGE = 10 ** 9  # "no truncation" sentinel for _transcript_body


def run_analysis_chunked(
    user_prompt: str,
    videos: list[VideoSource],
    *,
    backend: str,
    api_key: str | None,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    max_input_chars: int = MAX_INPUT_CHARS,
    build_max_chars: int = 60_000,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """Run analyze, chunking the groq path when the prompt is too large.

    `build_max_chars` is the per-video truncation passed to `build_prompt`
    for the single-shot path (preserves the `analyze --max-chars` flag);
    the map-reduce path reads each transcript in full instead.

    Returns the LLM response text (or "" on failure, like `run_analysis`).
    """
    note = on_status or (lambda _msg: None)

    def call(prompt: str) -> str:
        # Call via the module (not a bound name) so patching
        # `analyze.runner.run_analysis` in tests / callers still applies.
        return runner.run_analysis(
            prompt, backend=backend, api_key=api_key,
            ollama_model=ollama_model, ollama_host=ollama_host,
        )

    full = build_prompt(user_prompt, videos, max_chars=build_max_chars)
    # Only groq needs chunking; other backends have large contexts. And if
    # the single-shot prompt already fits, send it as-is (no behaviour change).
    if backend != "groq" or len(full) <= max_input_chars:
        return call(full)

    note(
        f"groq: analyze prompt is {len(full)} chars (> {max_input_chars} "
        f"budget) — chunked map-reduce over {len(videos)} transcript(s)"
    )

    # Keep speaker and viewer material separate through all map and collapse calls.
    with_comments = any(v.comments_text is not None for v in videos)
    transcripts: list[tuple[str, str]] = []
    comments: list[tuple[str, str]] = []
    for idx, v in enumerate(videos, start=1):
        header = _video_header(idx, v)
        sources = [("transcript", _transcript_body(v, _HUGE), transcripts)]
        if v.comments_text is not None:
            sources.append(("audience comments", v.comments_text, comments))
        for material, body, summaries in sources:
            scaffold = len(_map_prompt(header if with_comments else "", "", "", material))
            pieces = _split(body, max(800, max_input_chars - scaffold - 100))
            parts = []
            for i, piece in enumerate(pieces, start=1):
                ctx = f" (part {i}/{len(pieces)})" if len(pieces) > 1 else ""
                summary = call(_map_prompt(header, ctx, piece, material)).strip()
                parts.append((header + ctx, summary))
            if with_comments:
                summaries.extend(parts)
            else:
                # Transcript-only runs have historically reduced one summary per video.
                summaries.append((header, "\n".join(text for _, text in parts if text)))
            note(f"  summarized [{idx}/{len(videos)}] {len(pieces)} chunk(s)")

    prefix = f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\n---\n"
    groups = [("Transcript summaries:", transcripts, "transcript")]
    if comments:
        prefix += "Keep speaker statements and audience reactions attributed to their sources.\n"
        groups.append(("Audience comment summaries:", comments, "audience comments"))

    # Reserve space for each source's heading even if its summaries require truncation.
    overhead = len(prefix) + sum(len(heading) + 2 for heading, _, _ in groups) + 2 * (len(groups) - 1)
    available = max(0, max_input_chars - overhead)
    budgets = [available]
    if comments:
        sizes = [len(_summary_text(items)) for _, items, _ in groups]
        half = available // 2
        speaker_budget = min(sizes[0], max(half, available - sizes[1]))
        budgets = [speaker_budget, available - speaker_budget]
    sections = []
    for (heading, summaries, material), budget in zip(groups, budgets):
        body = _fit_summaries(summaries, material=material, budget=budget, call=call, note=note)
        sections.append(f"{heading}\n\n{body}")
    return call((prefix + "\n\n".join(sections))[:max_input_chars])


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _split(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _map_prompt(header: str, ctx: str, piece: str, material: str) -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Condense the following {material}{ctx} into faithful, concise "
        f"bullet points. Preserve specifics — names, numbers, terms, claims. "
        f"Do not add commentary. Reply in the language of the {material}.\n\n"
        f"{header}{ctx}\n\n{piece}"
    )


def _summary_text(summaries: list[tuple[str, str]]) -> str:
    return "\n".join(f"{header}\n\n{summary or '(no summary)'}\n\n---\n" for header, summary in summaries)


def _fit_summaries(
    summaries: list[tuple[str, str]], *, material: str, budget: int,
    call: Callable[[str], str], note: Callable[[str], None],
) -> str:
    text = _summary_text(summaries)
    rounds = 0
    while len(text) > budget and len(summaries) > 1 and rounds < 6:
        note(f"  reduce: collapsing {len(summaries)} {material} summaries (round {rounds + 1})")
        summaries = _collapse_once(summaries, budget=max(800, budget), call=call, material=material)
        text = _summary_text(summaries)
        rounds += 1
    return text[:budget]


def _item_len(item: tuple[str, str]) -> int:
    header, summ = item
    return len(header) + len(summ)


def _collapse_once(
    summaries: list[tuple[str, str]],
    *,
    budget: int,
    material: str,
    call: Callable[[str], str],
) -> list[tuple[str, str]]:
    """Merge summaries into fewer items so the reduce prompt shrinks.

    Greedy packing, but every group is forced to hold at least 2 items
    while more remain — this guarantees the count strictly decreases each
    round (so the collapse loop terminates), even when the budget is too
    small for a clean fit.
    """
    groups: list[list[tuple[str, str]]] = []
    i, n = 0, len(summaries)
    while i < n:
        group = [summaries[i]]
        size = _item_len(summaries[i])
        i += 1
        while i < n and (len(group) < 2 or size + _item_len(summaries[i]) <= budget):
            group.append(summaries[i])
            size += _item_len(summaries[i])
            i += 1
        groups.append(group)

    out: list[tuple[str, str]] = []
    for g in groups:
        if len(g) == 1:
            out.append(g[0])
            continue
        block = "\n\n".join(f"{h}\n{s}" for h, s in g)
        merged = call(
            f"{SYSTEM_PROMPT}\n\n"
            f"Merge the following {material} summaries into one consolidated, "
            "faithful set of bullet points. Keep specifics; drop duplication. "
            "Reply in the language of the summaries.\n\n"
            f"{block}"
        )
        out.append(("### Combined summary", merged.strip()))
    return out
