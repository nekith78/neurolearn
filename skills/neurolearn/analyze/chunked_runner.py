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

from typing import Callable

from skills.neurolearn.analyze import runner
from skills.neurolearn.analyze.prompt_builder import (
    SYSTEM_PROMPT, build_prompt, _video_body, _video_header,
)
from skills.neurolearn.analyze.source_resolver import VideoSource

# Groq free-tier limit is 12_000 tokens per request. A conservative
# upper-bound token density across EN/RU transcripts is ≈ 0.75 tok/char,
# and we leave headroom for the output, so cap each request's INPUT at
# ~12_000 chars (~9k tokens). Verified empirically 2026-05-27: ~22k-char
# (≈10k token) requests pass, ~32k-char (≈14k token) requests 413.
MAX_INPUT_CHARS = 12_000

_HUGE = 10 ** 9  # "no truncation" sentinel for _video_body


def run_analysis_chunked(
    user_prompt: str,
    videos: list[VideoSource],
    *,
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
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

    # Per-chunk budget = request budget minus the fixed map scaffold.
    scaffold = len(_map_prompt("", "", ""))
    chunk_chars = max(800, max_input_chars - scaffold - 100)

    # MAP — one (or more) summary per transcript.
    summaries: list[tuple[str, str]] = []
    for idx, v in enumerate(videos, start=1):
        header = _video_header(idx, v)
        body = _video_body(v, _HUGE)
        pieces = _split(body, chunk_chars)
        parts: list[str] = []
        for i, piece in enumerate(pieces, start=1):
            ctx = f" (part {i}/{len(pieces)})" if len(pieces) > 1 else ""
            parts.append(call(_map_prompt(header, ctx, piece)))
        summaries.append((header, "\n".join(p.strip() for p in parts if p.strip())))
        note(f"  summarized [{idx}/{len(videos)}] {len(pieces)} chunk(s)")

    # REDUCE — apply the user's prompt to the collected summaries.
    return _reduce(
        user_prompt, summaries, call=call, max_input_chars=max_input_chars,
        note=note,
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _split(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _map_prompt(header: str, ctx: str, piece: str) -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Condense the following transcript{ctx} into faithful, concise "
        f"bullet points. Preserve specifics — names, numbers, terms, claims. "
        f"Do not add commentary. Reply in the language of the transcript.\n\n"
        f"{header}{ctx}\n\n{piece}"
    )


def _assemble(user_prompt: str, summaries: list[tuple[str, str]]) -> str:
    parts = [SYSTEM_PROMPT, "", user_prompt, "", "---", "Transcript summaries:", ""]
    for header, summ in summaries:
        parts.append(header)
        parts.append("")
        parts.append(summ or "(no summary)")
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _reduce(
    user_prompt: str,
    summaries: list[tuple[str, str]],
    *,
    call: Callable[[str], str],
    max_input_chars: int,
    note: Callable[[str], None],
) -> str:
    prompt = _assemble(user_prompt, summaries)
    reduce_scaffold = len(_assemble(user_prompt, []))
    rounds = 0
    while len(prompt) > max_input_chars and len(summaries) > 1 and rounds < 6:
        note(
            f"  reduce: {len(summaries)} summaries still exceed budget — "
            f"collapsing (round {rounds + 1})"
        )
        summaries = _collapse_once(
            summaries, budget=max(800, max_input_chars - reduce_scaffold),
            call=call,
        )
        prompt = _assemble(user_prompt, summaries)
        rounds += 1
    if len(prompt) > max_input_chars:
        # Last resort: a single summary still won't fit. Hard-truncate the
        # assembled prompt (keeps the system framing + user prompt at the
        # top, drops the tail of the summaries) so the final call succeeds.
        prompt = prompt[:max_input_chars]
    return call(prompt)


def _item_len(item: tuple[str, str]) -> int:
    header, summ = item
    return len(header) + len(summ)


def _collapse_once(
    summaries: list[tuple[str, str]],
    *,
    budget: int,
    call: Callable[[str], str],
) -> list[tuple[str, str]]:
    """Merge summaries into fewer items so the reduce prompt shrinks.

    Greedy packing, but every group is forced to hold at least 2 items
    while more remain — this guarantees the count strictly decreases each
    round (so `_reduce`'s loop terminates), even when the budget is too
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
            "Merge the following transcript summaries into one consolidated, "
            "faithful set of bullet points. Keep specifics; drop duplication. "
            "Reply in the language of the summaries.\n\n"
            f"{block}"
        )
        out.append(("### Combined summary", merged.strip()))
    return out
