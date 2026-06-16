# AGENTS.INVARIANTS.md

> Defensive code, guards, and behavioral guarantees in this project.
> Part of the AGENTS.md ecosystem — readable by Claude Code, Codex CLI, Cursor, Copilot.
> Auto-injected into Claude's context by hooks (`~/.claude/scripts/agents_doc_hook.py`) on:
> - SessionStart (full file)
> - PreCompact (re-inject after auto-compaction)
> - PreToolUse on critical paths (module-specific subset if modular layout used)

## How to use this file

- Every guard, validation, or "never do X" check in the code must have an entry here.
- Entries are **append-only**. Deprecated guards move to `## Archived` — preserve IDs, never reuse.
- When this file exceeds ~250 lines (~2,500 tokens), split entries into `docs/agents/modules/<module>.INVARIANTS.md` and configure the mapping in `.claude/agents-config.toml`. Hooks handle both flat and modular layouts.
- ID format: `INV-NNN` (zero-padded, sequential, monotonic).

## Entry format

```
## INV-NNN — <one-line summary>
- **Where:** path/to/file.ext:<line>
- **Guard:** <exact line of code, quoted>
- **Prevents:** <what failure mode this guard prevents>
- **Source:** <commit hash / PR number / spec section / memory id>
- **Added:** YYYY-MM-DD
```

---

## INV-001 — <example, replace with first real invariant>
- **Where:** path/to/file.ext:42
- **Guard:** `if not input.valid: raise ValueError(...)`
- **Prevents:** Downstream code crashing on malformed input.
- **Source:** initial scaffolding
- **Added:** YYYY-MM-DD

<!-- Add more entries below -->

## INV-002 — API key rejected if it contains newline
- **Where:** skills/neurolearn/config.py:504
- **Guard:** `if "\n" in value or "\r" in value: raise ValueError("API key value cannot contain newline characters")`
- **Prevents:** Multi-line API key value would corrupt the `.env` file — the second line could be parsed as another `KEY=value` pair, silently injecting or overwriting an unrelated environment variable. This is a write-time guard for `set_api_key` / `config set-key`.
- **Source:** memory `feedback_no_anthropic_api` lineage + v0.13.0 secure key handoff design
- **Added:** 2026-05-27

## INV-003 — `.env` file written with 0600 in single open() call (no TOCTOU)
- **Where:** skills/neurolearn/config.py:522
- **Guard:** `fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)`
- **Prevents:** A `write_text()` + post-hoc `chmod 0600` sequence leaves a TOCTOU window where another local user on a shared box could read the freshly-written API key before chmod runs. The atomic `os.open(..., O_CREAT, 0o600)` closes that window. (Windows path falls back to `write_bytes` — NTFS ACLs apply, mode bits don't.)
- **Source:** inline code comment + v0.13.0 secure key handoff design
- **Added:** 2026-05-27

## INV-004 — Unknown backend name in `set_api_key` raises immediately
- **Where:** skills/neurolearn/config.py:507
- **Guard:** `if not var: raise ValueError(f"Unknown backend for env var: {backend}")`
- **Prevents:** Typo in `set_api_key("groqq", ...)` would silently miss the lookup table and route the key into an undefined env var, OR pollute `.env` with a garbage entry. Hard-fail keeps the .env consistent with `_BACKEND_ENV_VAR` map.
- **Source:** scan
- **Added:** 2026-05-27

## INV-005 — Backend factory rejects unknown backend names
- **Where:** skills/neurolearn/backends/factory.py:92
- **Guard:** `raise ValueError(f"Unknown backend: {name!r}")` (terminator of the `build_backend` if-cascade)
- **Prevents:** This is the gatekeeper of the 8-backend abstraction (`subtitles`, `whisper-local`, `gemini`, `groq`, `openai`, `deepgram`, `assemblyai`, `custom`). Without the terminating raise, a typo in `cfg.default_backend` would silently fall through to `None` and crash later in `transcribe_batch` with an unhelpful `AttributeError`. CLAUDE.md "Backend abstraction" invariant depends on this guard.
- **Source:** CLAUDE.md "Backend abstraction" section
- **Added:** 2026-05-27

## INV-006 — `memory append-facts` rejects malformed JSON
- **Where:** skills/neurolearn/memory/learn.py:635
- **Guard:** `raise ValueError(f"approved.json is not valid JSON ({approved_path}): {e}") from e`
- **Prevents:** v0.16.2 Claude-extract flow ends with the user running `memory append-facts <name> --from-file approved.json`. If Claude in chat wrote corrupted JSON, this guard surfaces the parse error rather than silently appending nothing (or garbage) to the memory file. Pure-write command — no LLM call — so this is the only safety net.
- **Source:** commit ffb14a0 (v0.16.2)
- **Added:** 2026-05-27

## INV-007 — `memory append-facts` validates `candidates` list shape
- **Where:** skills/neurolearn/memory/learn.py:640
- **Guard:** `if not isinstance(candidates, list): raise ValueError(f"approved.json must contain a 'candidates' list. ...")`
- **Prevents:** A JSON with the wrong top-level shape (`{"facts": [...]}` instead of `{"candidates": [...]}`) would silently produce zero appends with no warning. Hard-fail forces Claude (or the user) to fix the JSON to the contract documented in the briefing.
- **Source:** commit ffb14a0 (v0.16.2)
- **Added:** 2026-05-27

## INV-008 — Memory diff prompt is capped under Groq free-tier TPM limit
- **Where:** skills/neurolearn/memory/learn.py:79 (`existing[:1600]`) and skills/neurolearn/memory/learn.py:85 (`transcript.text[:9700]`)
- **Guard:** Hard-coded character caps on the two variable-size sections of the diff prompt. Together with the ~600-token fixed scaffold, the total stays under ~8700 tokens.
- **Prevents:** Groq free-tier `llama-3.3-70b` has a 12 000 TPM (tokens per minute) rate limit. Without the caps, a 30-minute transcript would produce a ~15 000-token prompt → HTTP 413 → `run_analysis` silently swallows the exception and returns `""` → the parser sees "0 candidates" with no diagnostic, masking a real bug. v0.16.1 lesson; the cap is the only reason memory learn works on free tier. (Paid Groq tier = 50k TPM and can take 5× more; `cfg.groq_tier` could lift this in the future.)
- **Source:** commit 982cf90 (v0.16.1) + inline docstring rationale
- **Added:** 2026-05-27

## INV-009 — `--days` and `--since`/`--until` are mutually exclusive
- **Where:** skills/neurolearn/shared/date_filter.py:31
- **Guard:** `if days is not None and (since is not None or until is not None): raise ValueError("--days and --since/--until are mutually exclusive")`
- **Prevents:** Passing both forms produces undefined behavior downstream (which window wins?). Hard-fail at CLI argument parse forces user to pick one. Used by batch / research / subscribes update.
- **Source:** scan
- **Added:** 2026-05-27

## INV-010 — Date window rejects reversed `--since`/`--until`
- **Where:** skills/neurolearn/shared/date_filter.py:46
- **Guard:** `if since > end: raise ValueError("--since must be before --until")`
- **Prevents:** A reversed window would yield zero candidate videos with no obvious error message, looking like "nothing found" when really the args are wrong.
- **Source:** scan
- **Added:** 2026-05-27

## INV-011 — Work commands refuse to run before onboarding completes
- **Where:** skills/neurolearn/transcribe.py:614 (`_require_onboarding_complete`) — called from `transcribe_cmd`, `batch_cmd`, `analyze_cmd`, `research_cmd`
- **Guard:** `if cfg.onboarding_complete: return` else stderr message + `sys.exit(7)`. The `allow_offline=True` parameter lets `--backend whisper-local` / `--backend subtitles` bypass the gate.
- **Prevents:** v0.13.0+ forced-onboarding gate: without it, a fresh install with half-configured stack would attempt to run work-commands and fail with cryptic per-backend errors. Exit code 7 is the contract Claude Code's `/setup` flow uses to detect "needs setup" state and re-run the original command after wizard completes. The `--no-auto-bypass` warning in the error message also blocks Claude from silently routing around the gate via `--backend whisper-local`.
- **Source:** CLAUDE.md "Onboarding gate (v0.13.0+)" + commit a2e06c8 lineage
- **Added:** 2026-05-27

## INV-012 — Memory diff defaults to Claude-extract mode inside Claude Code
- **Where:** skills/neurolearn/memory/learn.py:309-313
- **Guard:** `use_claude_extract = claude_extract if claude_extract is not None else bool(os.environ.get("CLAUDE_PLUGIN_ROOT"))`. When True, `learn()` writes a briefing manifest and exits without calling Groq.
- **Prevents:** Architectural rule `feedback_no_anthropic_api`: analysis-style work inside Claude Code must be done by Claude in chat through the user's subscription, NOT by routing to a paid external LLM API. v0.16.0/v0.16.1 violated this by unconditionally calling Groq for the memory diff; v0.16.2 fixed it via this auto-detect, mirroring the v0.12.1 vision extract-only pattern. Override is `--no-claude-extract` (memory learn) or `--no-learn-claude-extract` (host commands batch/research/subscribes).
- **Source:** commit ffb14a0 (v0.16.2) + memory `feedback_no_anthropic_api`
- **Added:** 2026-05-27

## INV-013 — `anthropic` SDK is NOT a backend (convention)
- **Where:** convention (no code guard — tacit architectural rule)
- **Guard:** DO NOT import `anthropic` SDK as a backend. The 8 valid backends are `subtitles`, `whisper-local`, `gemini`, `groq`, `openai`, `deepgram`, `assemblyai`, `custom`. Anthropic was removed from base deps in v0.12.0. Claude integration happens through the user's Claude Code chat subscription — we hand over raw data (transcripts, briefings, manifests), Claude does the analysis in chat. Vision uses Groq Llama-4-Scout default + Gemini fallback. Memory diff uses briefing pattern when `CLAUDE_PLUGIN_ROOT` is set (see INV-012).
- **Prevents:** Routing analysis to `anthropic.Anthropic()` burns the user's wallet on work their subscription already covers. Architectural violation: v0.16.0/v0.16.1 broke this rule for the memory diff path (routed to Groq, equivalent severity — paid API instead of free subscription analysis), required v0.16.2 to fix. Re-introducing `import anthropic` as a backend is the same class of mistake.
- **Source:** memory `feedback_no_anthropic_api` + CLAUDE.md "Anthropic API is NOT a backend" + commits ffb14a0 / 982cf90 / a2e06c8 lineage
- **Added:** 2026-05-27

---

## Archived

<!-- Deprecated invariants — kept for ID continuity, NOT injected by hooks. -->
<!-- Move entries here when the guarded code is removed. -->
