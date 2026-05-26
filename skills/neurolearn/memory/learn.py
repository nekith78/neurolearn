"""Memory learn flow — LLM diff + user approval gate.

Given:
  - An existing memory file (description + accumulated facts)
  - One or more new transcripts

Output:
  - A list of candidate-new facts the LLM thinks aren't yet captured
  - User approves each interactively (or in batch via `--yes`)
  - Approved facts are appended to the memory file

The diff prompt is intentionally conservative: when in doubt, return
fewer facts. The user can always rerun with a different LLM if they
want broader extraction.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from skills.neurolearn.config import Config
from skills.neurolearn.memory.store import (
    MemoryFile, append_facts_to_body, read_memory, write_memory,
)


@dataclass
class TranscriptInput:
    """One transcript to consider for memory ingestion."""
    url: str
    title: str
    text: str           # plain transcript (no timestamps for the LLM)


def _build_diff_prompt(memory: MemoryFile, transcript: TranscriptInput) -> str:
    """LLM prompt for extracting NEW facts from a transcript relative
    to what's already in memory."""
    existing = memory.body.strip() or "(empty — this is the first ingestion)"
    description = memory.description.strip() or (
        "(no description yet — infer from accumulated content)"
    )
    return f"""You are curating a personal knowledge base called "{memory.name}".

## Memory description
{description}

## Already in this memory
{existing[:8000]}

## New transcript to consider
Title: {transcript.title}
URL: {transcript.url}

{transcript.text[:20000]}

## Your task

Extract facts from the new transcript that are NOT already covered by what's
already in memory. Be conservative — when unsure if something is new, skip it.

A "fact" should be:
- Specific (not vague restatements of common knowledge)
- Self-contained (one sentence the user can read out of context)
- On-topic for this memory based on its description
- Genuinely new — not paraphrased duplicates of what's already there

Group facts by `topic` — a short noun phrase (1-4 words) that groups related
facts together (e.g. "Hooks", "Slash commands", "MCP servers").

Return STRICT JSON only, no commentary, in this exact shape:

{{
  "candidates": [
    {{
      "topic": "Hooks",
      "text": "SessionStart hooks fire when a new Claude Code session begins.",
      "source_timestamp": "03:12-04:05"
    }},
    {{
      "topic": "Skills",
      "text": "Skills can be triggered by natural-language patterns in user messages.",
      "source_timestamp": null
    }}
  ]
}}

If you find no new facts, return: {{"candidates": []}}.
Maximum 10 candidates per call — pick the strongest.
"""


def extract_candidates(
    memory: MemoryFile,
    transcript: TranscriptInput,
    *,
    analyze_backend: str,
    cfg: Config,
) -> list[dict]:
    """Call the LLM and parse its JSON response. Returns the list of
    candidate facts, or [] when the LLM declines / returns garbage."""
    from skills.neurolearn.analyze.runner import run_analysis
    from skills.neurolearn.config import get_api_key

    prompt = _build_diff_prompt(memory, transcript)
    api_key = get_api_key(analyze_backend) if analyze_backend != "ollama" else None
    raw_response = run_analysis(
        full_prompt=prompt,
        backend=analyze_backend,
        api_key=api_key,
    )
    return _parse_candidates(raw_response)


def _parse_candidates(raw: str) -> list[dict]:
    """Robust extractor for the LLM's JSON output. LLMs sometimes wrap
    JSON in fences or add commentary — we try several patterns."""
    if not raw:
        return []
    # 1. Direct JSON
    for attempt in (raw, _extract_fenced_json(raw), _extract_first_json_object(raw)):
        if not attempt:
            continue
        try:
            data = json.loads(attempt)
            candidates = data.get("candidates", []) if isinstance(data, dict) else []
            return [c for c in candidates if isinstance(c, dict) and c.get("text")]
        except json.JSONDecodeError:
            continue
    return []


_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_fenced_json(text: str) -> str | None:
    m = _FENCE_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_first_json_object(text: str) -> str | None:
    m = _OBJECT_RE.search(text)
    return m.group(0).strip() if m else None


# ---------------------------------------------------------------------------
# Interactive approval
# ---------------------------------------------------------------------------

def approve_candidates_interactive(
    candidates: list[dict],
    *,
    auto_yes: bool = False,
) -> list[dict]:
    """Walk the user through each candidate. Returns the approved subset.

    Actions per candidate:
      y — approve (default)
      n — skip
      a — approve all remaining
      q — quit (skip all remaining, return what's already approved)
    """
    if not candidates:
        return []

    if auto_yes:
        return candidates

    if not sys.stdin.isatty():
        # Non-TTY (Claude Code subprocess, CI): we can't prompt.
        # Auto-approve only if the caller explicitly opted in via auto_yes;
        # otherwise return nothing — caller surfaces a clear message.
        return []

    try:
        from rich.prompt import Prompt
        from rich.console import Console
        from rich.panel import Panel
    except ImportError:
        return candidates  # fall back to approve-all if rich isn't there

    console = Console()
    approved: list[dict] = []
    approve_all = False
    for i, cand in enumerate(candidates, start=1):
        if approve_all:
            approved.append(cand)
            continue
        topic = cand.get("topic", "Notes")
        text = cand.get("text", "")
        ts = cand.get("source_timestamp") or ""
        console.print(Panel(
            f"[bold]{topic}[/bold]\n\n{text}"
            + (f"\n\n[dim]Source timestamp: {ts}[/dim]" if ts else ""),
            title=f"Candidate {i}/{len(candidates)}",
            border_style="cyan",
        ))
        choice = Prompt.ask(
            "Add to memory?",
            choices=["y", "n", "a", "q"],
            default="y",
        )
        if choice == "y":
            approved.append(cand)
        elif choice == "a":
            approved.append(cand)
            approve_all = True
        elif choice == "q":
            break
        # n → skip
    return approved


# ---------------------------------------------------------------------------
# Top-level learn() orchestrator
# ---------------------------------------------------------------------------

def learn(
    *,
    memory_name: str,
    transcripts: list[TranscriptInput],
    analyze_backend: str,
    cfg: Config,
    auto_yes: bool = False,
    on_status=None,
) -> dict:
    """High-level entry point.

    1. Read the existing memory (create empty placeholder if not found).
    2. For each transcript: extract candidates, approve, append.
    3. After approvals: auto-generate description if it was empty.
    4. Persist to disk.

    Returns a summary dict for the caller to log.
    """
    notify = on_status or (lambda msg: sys.stderr.write(f"[neurolearn] {msg}\n"))

    try:
        memory = read_memory(memory_name, cfg=cfg)
    except FileNotFoundError:
        memory = MemoryFile(name=memory_name)

    total_proposed = 0
    total_approved = 0

    for t in transcripts:
        notify(f"learn: analyzing {t.title or t.url[:60]!r}...")
        candidates = extract_candidates(
            memory, t, analyze_backend=analyze_backend, cfg=cfg,
        )
        total_proposed += len(candidates)
        if not candidates:
            notify(f"learn: no new facts found in {t.url[:60]!r}.")
            continue
        approved = approve_candidates_interactive(candidates, auto_yes=auto_yes)
        if approved:
            append_facts_to_body(
                memory, approved, source_url=t.url,
            )
            total_approved += len(approved)
            notify(f"learn: appended {len(approved)} fact(s).")
        else:
            notify(f"learn: skipped all {len(candidates)} candidate(s).")

    # v0.16.0: auto-generate description if it was empty and we have body
    if not memory.description.strip() and memory.body.strip():
        try:
            memory.description = _autogenerate_description(
                memory, analyze_backend=analyze_backend, cfg=cfg,
            )
            notify(f"learn: auto-generated description ({len(memory.description)} chars).")
        except Exception as e:
            notify(f"learn: description auto-gen failed ({e}); leaving blank.")

    write_memory(memory, cfg=cfg)
    return {
        "memory": memory_name,
        "transcripts_processed": len(transcripts),
        "candidates_proposed": total_proposed,
        "candidates_approved": total_approved,
        "sources_total": memory.sources,
    }


def _autogenerate_description(
    memory: MemoryFile, *, analyze_backend: str, cfg: Config,
) -> str:
    """Two-sentence summary of what's in this memory, generated from
    the accumulated body. Triggered the first time the user runs
    `learn` without having set an explicit description."""
    from skills.neurolearn.analyze.runner import run_analysis
    from skills.neurolearn.config import get_api_key
    prompt = (
        f"Below is a knowledge-base file. Write a 2-sentence description "
        f"of WHAT it's about — what topics it covers, what kinds of facts "
        f"belong in it. Do not summarize the facts themselves; describe "
        f"the SCOPE so future readers know whether new facts belong here.\n\n"
        f"Knowledge base content:\n{memory.body[:6000]}\n\n"
        f"Return only the 2-sentence description. No preamble."
    )
    api_key = get_api_key(analyze_backend) if analyze_backend != "ollama" else None
    text = run_analysis(
        full_prompt=prompt,
        backend=analyze_backend,
        api_key=api_key,
    )
    # Trim aggressively — LLMs love adding "Here is the description:"
    text = (text or "").strip()
    for prefix in (
        "Here's the description:", "Here is the description:",
        "Description:", "Summary:", "Scope:",
    ):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    return text or ""
