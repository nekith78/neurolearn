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

v0.16.2 — Claude Code extract-only mode:
  When the env var `CLAUDE_PLUGIN_ROOT` is set, neurolearn runs inside
  a Claude Code chat session. Per project rule `feedback_no_anthropic_api`
  (Audio через Groq, остальное Claude сам делает в чате) we MUST NOT
  call an external LLM API for analysis-style work. Instead we write a
  briefing manifest containing the existing memory + new transcripts
  and exit. Claude in chat reads the briefing natively, does the diff,
  confirms candidates with the user, writes `approved.json`, and the
  user then runs `memory append-facts <name> --from-file approved.json`
  to persist. Same env-var-driven auto-detect that the vision pipeline
  uses since v0.12.1. Override with `--no-claude-extract` to force the
  Groq path even inside Claude Code.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from skills.neurolearn.config import Config
from skills.neurolearn.memory.store import (
    MemoryFile, append_facts_to_body, memories_dir, memory_path,
    read_memory, write_memory,
)


@dataclass
class TranscriptInput:
    """One transcript to consider for memory ingestion."""
    url: str
    title: str
    text: str           # plain transcript (no timestamps for the LLM)


def _build_diff_prompt(memory: MemoryFile, transcript: TranscriptInput) -> str:
    """LLM prompt for extracting NEW facts from a transcript relative
    to what's already in memory.

    Size budget calibration (v0.16.1): Groq free-tier llama-3.3-70b has
    a 12 000 TPM rate limit. Empirical tokens-per-char on technical
    English transcripts ≈ 0.72 t/c (Groq tokenizer is dense). To stay
    safely under 10 000 tokens per call:
      - scaffold:        ~600 tokens (fixed)
      - memory body:     up to ~1100 tokens (~1600 chars cap)
      - transcript:      up to ~7000 tokens (~9700 chars cap)
      - = ~8700 tokens total budget → fits 12k TPM with headroom
    Paid Groq tier (50k TPM) can handle 5× more — controllable via
    cfg.groq_tier in a future iteration.
    """
    existing = memory.body.strip() or "(empty — this is the first ingestion)"
    description = memory.description.strip() or (
        "(no description yet — infer from accumulated content)"
    )
    return f"""You are curating a personal knowledge base called "{memory.name}".

## Memory description
{description}

## Already in this memory
{existing[:1600]}

## New transcript to consider
Title: {transcript.title}
URL: {transcript.url}

{transcript.text[:9700]}

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
    if not raw_response:
        # run_analysis swallows exceptions (rate limits, network, etc.)
        # and returns "" on failure. Surface a visible hint so the
        # learn() caller doesn't show a confusing "0 candidates" with
        # no explanation. Most common cause on free tier Groq is the
        # 12k TPM cap (especially on long transcripts).
        sys.stderr.write(
            f"[neurolearn] memory learn: LLM returned empty response for "
            f"{transcript.url[:60]!r}. Likely causes:\n"
            f"  - Rate limit on free tier (Groq llama-3.3-70b: 12k TPM)\n"
            f"  - Invalid / missing {analyze_backend.upper()}_API_KEY\n"
            f"  - Provider transient error\n"
            f"  Re-running with shorter transcripts or a higher tier may help.\n"
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
    claude_extract: bool | None = None,
    pending_dir: Path | None = None,
    on_status=None,
) -> dict:
    """High-level entry point.

    1. Read the existing memory (create empty placeholder if not found).
    2. For each transcript: extract candidates, approve, append.
    3. After approvals: auto-generate description if it was empty.
    4. Persist to disk.

    v0.16.2: when running inside Claude Code (CLAUDE_PLUGIN_ROOT set) we
    skip the Groq diff entirely, write a briefing manifest, and return
    a summary with `mode == "claude_code_extract_only"`. The caller is
    expected to print the briefing path so Claude picks it up.

    Args:
        claude_extract: True/False forces the mode explicitly;
            None = auto-detect from CLAUDE_PLUGIN_ROOT env var.
        pending_dir: when in claude-extract mode, where to write the
            briefing. Defaults to
            ~/.neurolearn/memories/.pending/<name>-<timestamp>/.

    Returns a summary dict for the caller to log.
    """
    notify = on_status or (lambda msg: sys.stderr.write(f"[neurolearn] {msg}\n"))

    if not transcripts:
        return {
            "memory": memory_name,
            "transcripts_processed": 0,
            "candidates_proposed": 0,
            "candidates_approved": 0,
            "sources_total": 0,
            "mode": "noop",
        }

    use_claude_extract = (
        claude_extract
        if claude_extract is not None
        else bool(os.environ.get("CLAUDE_PLUGIN_ROOT"))
    )

    if use_claude_extract:
        try:
            existing = read_memory(memory_name, cfg=cfg)
        except FileNotFoundError:
            existing = MemoryFile(name=memory_name)
        briefing = write_learn_briefing(
            memory_name=memory_name,
            memory=existing,
            transcripts=transcripts,
            cfg=cfg,
            pending_dir=pending_dir,
        )
        notify(
            "learn: Claude-extract mode (CLAUDE_PLUGIN_ROOT detected). "
            "No external LLM call made."
        )
        notify(f"learn: briefing written to {briefing['briefing_path']}")
        notify(
            "learn: Claude in chat should read the briefing, propose "
            "candidates, get user approval, then call "
            f"`neurolearn memory append-facts {memory_name} "
            f"--from-file {briefing['approved_json_path']}`."
        )
        return {
            "memory": memory_name,
            "transcripts_processed": len(transcripts),
            "candidates_proposed": 0,
            "candidates_approved": 0,
            "sources_total": existing.sources,
            "mode": "claude_code_extract_only",
            "briefing_path": str(briefing["briefing_path"]),
            "approved_json_path": str(briefing["approved_json_path"]),
        }

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
        "mode": "llm_diff",
    }


# ---------------------------------------------------------------------------
# v0.16.2: Claude Code extract-only briefing writer
# ---------------------------------------------------------------------------

_CLAUDE_BRIEFING_TEMPLATE = """# Memory learn — Claude-extract mode

This file is a briefing for Claude (in the current chat). neurolearn is
running inside a Claude Code session (`CLAUDE_PLUGIN_ROOT` is set), so per
the project rule `feedback_no_anthropic_api` it has NOT called any external
LLM for the diff. Instead, it has assembled the existing memory + the
new transcripts and is asking Claude to do the diff directly in chat,
using its native context window.

## Memory metadata

- **Name:** `{memory_name}`
- **Memory file:** `{memory_path}`
- **Sources so far:** {sources}
- **Last updated:** {last_updated}

## Description (current scope of this memory)

{description}

## Already in this memory (full body)

{existing_body}

## New transcripts to consider ({transcript_count})

{transcripts_block}

## Your task (for Claude in chat)

1. **Read the existing memory body above carefully.** Note topics and
   specific facts already captured.

2. **For each transcript, propose new facts** that are NOT already
   covered. Be CONSERVATIVE — when in doubt, skip. A "fact" should be:
   - Specific (not vague restatements of common knowledge)
   - Self-contained (one sentence the user can read out of context)
   - On-topic for this memory based on its description
   - Genuinely new — not paraphrased duplicates of what's already there

   Group facts by `topic` — a short noun phrase (1-4 words) like
   "Hooks", "Slash commands", "MCP servers".

3. **Present candidates to the user** in the chat, one transcript at a
   time. For each candidate include: topic, text, source URL, and (if
   you can identify it) a `source_timestamp` range. Ask y/n per
   candidate, or accept "approve all from transcript N" if the user
   wants to skim.

4. **Write the user-approved subset** to:

   ```
   {approved_json_path}
   ```

   In this exact shape:

   ```json
   {{
     "candidates": [
       {{
         "topic": "Hooks",
         "text": "SessionStart hooks fire when a new Claude Code session begins.",
         "source_url": "https://...",
         "source_timestamp": "03:12-04:05"
       }}
     ]
   }}
   ```

   `source_url` is required (so the memory file records provenance).
   `source_timestamp` is optional (leave out the key or set null).

5. **Tell the user to run** (or run it yourself via Bash):

   ```
   neurolearn memory append-facts {memory_name} --from-file {approved_json_path}
   ```

   That command performs a PURE WRITE — no LLM call — appending the
   approved candidates to the memory file with provenance and the
   current date.

If the user wants to skip this whole flow and go through Groq instead,
they can re-run the original command with `--no-claude-extract`.
"""


def _format_transcripts_for_briefing(transcripts: list[TranscriptInput]) -> str:
    """Render each transcript as a markdown subsection with full text.

    Claude reads this natively — no token-budget trimming. If the user's
    Claude Code context can't hold all transcripts they'll see a clear
    error in chat and can re-run on fewer at a time.
    """
    parts: list[str] = []
    for idx, t in enumerate(transcripts, start=1):
        title = (t.title or "").strip() or "(untitled)"
        url = (t.url or "").strip() or "(no URL)"
        text = (t.text or "").strip() or "(empty transcript)"
        parts.append(
            f"### Transcript {idx}: {title}\n\n"
            f"- **URL:** {url}\n\n"
            f"```\n{text}\n```\n"
        )
    return "\n".join(parts)


def write_learn_briefing(
    *,
    memory_name: str,
    memory: MemoryFile,
    transcripts: list[TranscriptInput],
    cfg: Config,
    pending_dir: Path | None = None,
) -> dict:
    """v0.16.2: emit a learn briefing Claude can read in chat.

    Returns a dict with `briefing_path` and `approved_json_path` (both
    Path) so the caller can print them.

    Storage layout (default):
        ~/.neurolearn/memories/.pending/<memory_name>-<ISO timestamp>/
            briefing.md          ← Claude reads this
            approved.json        ← Claude writes here after user approval
            transcripts.json     ← machine-readable copy for downstream tools
    """
    ts = _now_compact()
    base = pending_dir if pending_dir is not None else (
        memories_dir(cfg) / ".pending" / f"{_safe_filename(memory_name)}-{ts}"
    )
    base.mkdir(parents=True, exist_ok=True)

    briefing_path = base / "briefing.md"
    approved_json_path = base / "approved.json"
    transcripts_path = base / "transcripts.json"

    description = memory.description.strip() or (
        "(no description yet — will be auto-generated after the first "
        "append-facts call once the body is non-empty)"
    )
    existing_body = memory.body.strip() or "(empty — this is the first ingestion)"

    briefing = _CLAUDE_BRIEFING_TEMPLATE.format(
        memory_name=memory_name,
        memory_path=str(memory_path(memory_name, cfg=cfg)),
        sources=memory.sources,
        last_updated=memory.last_updated or "(never)",
        description=description,
        existing_body=existing_body,
        transcript_count=len(transcripts),
        transcripts_block=_format_transcripts_for_briefing(transcripts),
        approved_json_path=str(approved_json_path),
    )
    briefing_path.write_text(briefing, encoding="utf-8")

    transcripts_path.write_text(
        json.dumps(
            {
                "memory_name": memory_name,
                "memory_path": str(memory_path(memory_name, cfg=cfg)),
                "transcripts": [
                    {"url": t.url, "title": t.title, "text": t.text}
                    for t in transcripts
                ],
                "approved_json_path": str(approved_json_path),
                "next_command": (
                    f"neurolearn memory append-facts {memory_name} "
                    f"--from-file {approved_json_path}"
                ),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "briefing_path": briefing_path,
        "approved_json_path": approved_json_path,
        "transcripts_path": transcripts_path,
        "pending_dir": base,
    }


def _now_compact() -> str:
    """ISO-8601 stamp safe for use in filesystem path components."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def _safe_filename(s: str) -> str:
    return _FILENAME_SAFE_RE.sub("-", (s or "").strip()) or "memory"


# ---------------------------------------------------------------------------
# v0.16.2: append-facts loader (pure write, no LLM)
# ---------------------------------------------------------------------------

def append_approved_from_file(
    *,
    memory_name: str,
    approved_path: Path,
    cfg: Config,
    autogenerate_description: bool = True,
    analyze_backend: str | None = None,
) -> dict:
    """Load Claude-produced approved.json and append candidates to memory.

    Schema (matches what `write_learn_briefing` asks Claude to write):
        {"candidates": [
            {"topic": "...", "text": "...",
             "source_url": "https://...",
             "source_timestamp": "03:12-04:05" or null}
        ]}

    Candidates are grouped by `source_url`. Each unique source counts as
    one "source" against memory.sources — same accounting as the
    interactive learn() path.

    No LLM is called for the append itself. If the memory has no
    description and the body becomes non-empty AND `autogenerate_description`
    is True AND a usable `analyze_backend` is supplied AND we're NOT in
    Claude-extract mode, we try to auto-generate the description; on any
    error we silently leave it blank (Claude can run `memory show` + an
    edit in chat instead).
    """
    if not approved_path.exists():
        raise FileNotFoundError(f"Approved facts file not found: {approved_path}")
    raw = approved_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"approved.json is not valid JSON ({approved_path}): {e}"
        ) from e
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        raise ValueError(
            f"approved.json must contain a 'candidates' list. Got: {type(candidates).__name__}"
        )

    try:
        memory = read_memory(memory_name, cfg=cfg)
    except FileNotFoundError:
        memory = MemoryFile(name=memory_name)

    by_source: dict[str, list[dict]] = {}
    for c in candidates:
        if not isinstance(c, dict):
            continue
        text = (c.get("text") or "").strip()
        if not text:
            continue
        source = (c.get("source_url") or "").strip() or "(unknown source)"
        by_source.setdefault(source, []).append({
            "topic": c.get("topic") or "Notes",
            "text": text,
            "source_timestamp": c.get("source_timestamp"),
        })

    sources_added = 0
    facts_added = 0
    for source_url, facts in by_source.items():
        if not facts:
            continue
        append_facts_to_body(memory, facts, source_url=source_url)
        sources_added += 1
        facts_added += len(facts)

    if (
        autogenerate_description
        and not memory.description.strip()
        and memory.body.strip()
        and analyze_backend
        and not os.environ.get("CLAUDE_PLUGIN_ROOT")
    ):
        try:
            memory.description = _autogenerate_description(
                memory, analyze_backend=analyze_backend, cfg=cfg,
            )
        except Exception:
            pass

    write_memory(memory, cfg=cfg)
    return {
        "memory": memory_name,
        "candidates_in_file": len(candidates),
        "facts_appended": facts_added,
        "sources_added": sources_added,
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
