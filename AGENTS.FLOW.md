# AGENTS.FLOW.md

> Runtime flow: how requests / operations / tasks travel through the system.
> Part of the AGENTS.md ecosystem — readable by Claude Code, Codex CLI, Cursor, Copilot.
> Auto-injected into Claude's context by hooks (`~/.claude/scripts/agents_doc_hook.py`) on:
> - SessionStart (full file)
> - PreCompact (re-inject after auto-compaction)
> - PreToolUse on critical paths (module-specific subset + targeted grep for the edited file's basename)

## How to use this file

- One `FLOW-NNN` entry per major operation: CLI command, API endpoint, background job, agent loop, pipeline stage.
- Numbered steps reference `module/file.ext:function` with a one-line description each.
- Cross-reference `INVARIANTS.md` inline using `INV-NNN`.
- When this file exceeds ~250 lines (~2,500 tokens), split into `docs/agents/modules/<module>.FLOW.md`.
- ID format: `FLOW-NNN`.

## Entry format

```
## FLOW-NNN — <operation name>

**Entry:** `<command / endpoint / trigger>` → `module/file.ext:function`

1. **<step name>** — `path/to/file.ext:function` — what this step does in one line.
2. **<step name>** — ...
3. ...

**Termination:** <success condition> OR <failure condition>.

**Related invariants:** INV-NNN, INV-NNN
```

---

## FLOW-001 — <example, replace with first real flow>

**Entry:** `command_or_endpoint` → `module/file.ext:entry_function`

1. **Parse input** — `module/parser.ext:parse` — validate and normalize.
2. **Dispatch** — `module/router.ext:route` — select handler by intent.
3. **Execute** — `module/handler.ext:handle` — run the operation.
4. **Format output** — `module/formatter.ext:format` — render result to user.

**Termination:** result ready OR limit hit (steps / time / budget).

**Related invariants:** INV-001

<!-- Add more FLOW entries below -->

## FLOW-002 — `transcribe` single URL or local file

**Entry:** `neurolearn transcribe <URL_or_path>` → `skills/neurolearn/transcribe.py:transcribe_cmd`

1. **Onboarding gate** — `skills/neurolearn/transcribe.py:_require_onboarding_complete` — refuse with exit 7 unless `cfg.onboarding_complete` OR `--backend whisper-local`/`subtitles`.
2. **Config + CLI overrides** — `skills/neurolearn/transcribe.py:_override_config` — merge `config.toml` defaults with command-line flags.
3. **Resolve target** — `skills/neurolearn/utils/resolver.py:resolve` — URL/path → `ResolvedTarget`. Channels/playlists rejected (caller should use `batch`).
4. **Run pipeline** — `skills/neurolearn/pipeline.py:run_pipeline` — dispatches to backend via `backends/factory.build_backend` (or `factory.run_smart` for the smart cascade). Smart cascade: subtitles fast-path on YouTube → audio download → fallback backend (default `groq`).
5. **v0.2 stages** — `skills/neurolearn/pipeline_v02.py:apply_v02_stages` — quality check, triggers, ASR correction, diarization, translation, vision (if `--with-visuals`).
6. **Write outputs** — txt + srt + json under `cfg.output_dir`.

**Termination:** transcript ready (exit 0) OR exit 2 (resolver failure) / 3 (backend not configured) / 4 (transcription error) / 7 (onboarding) / 8 (`PlatformBlockError`).

**Related invariants:** INV-005 (backend abstraction), INV-011 (onboarding gate).

## FLOW-003 — `batch` multiple inputs / channel / playlist

**Entry:** `neurolearn batch <inputs...>` → `skills/neurolearn/transcribe.py:batch_cmd`

1. **Onboarding gate** — `_require_onboarding_complete` — same exit-7 contract.
2. **Resolve inputs** — `utils/resolver.resolve` — URL list, `--from-file`, `--search ytsearchN:` all expand to a flat list of `ResolvedTarget`s; channel/playlist expansion includes shorts gating.
3. **Filters** — `ResolverFilters` (`--since`, `--until`, `--days`, `--min-duration`, `--max-duration`, `--no-shorts`, `--limit`) applied per spec; `--days` and `--since`/`--until` are mutex (INV-009, INV-010).
4. **Batch pipeline** — `skills/neurolearn/batch_pipeline.py:_run_batch_pipeline` — skip-existing → download → transcribe (per `cfg.default_backend`) → write per-video outputs + `combined.md` + `manifest.json`.
5. **Optional analyze** — if `--then-analyze`: `analyze/runner.run_analysis` on `combined.md` with chosen `--analyze-backend`.
6. **Optional learn-into** — if `--learn-into <memory>`: `memory/cli.py:run_learn_into_batch` ingests transcripts; respects `--learn-claude-extract` / env var auto-detect (INV-012).

**Termination:** all videos done (exit 0) OR exit 4 on `--fail-fast` early stop.

**Related invariants:** INV-005, INV-009, INV-010, INV-011, INV-012.

## FLOW-004 — `research` query → search → transcribe

**Entry:** `neurolearn research "<query>"` → `skills/neurolearn/transcribe.py:research_cmd`

1. **Onboarding gate** — `_require_onboarding_complete`.
2. **Multi-language query translation** — `skills/neurolearn/research/translator.py` — LLM-translate query into each `--languages` (default `en,ru`); reuses `analyze.runner` infrastructure.
3. **YouTube search** — `skills/neurolearn/research/source.py` — `ytsearchN:` per language, deduped by `video_id`.
4. **Filters** — date window (`--days`/`--since`/`--until` — INV-009/010), `--match` substring, `--filter` LLM pre-screen (optional, uses analyze backend), `--limit`.
5. **Optional TTY checkpoint** — `questionary` picker shows selected videos for y/n confirmation; skipped on `--yes` or non-TTY.
6. **Batch pipeline** — delegates to `batch_pipeline._run_batch_pipeline` with the resolved video list.
7. **Optional analyze + learn-into** — same as FLOW-003 steps 5-6.

**Termination:** research_batch_dir produced (exit 0) OR exit 2 on invalid args.

**Related invariants:** INV-009, INV-010, INV-011, INV-012.

## FLOW-005 — `subscribes update` — incremental channel pull

**Entry:** `neurolearn subscribes update` → `skills/neurolearn/subscribes/cli.py:update_cmd`

1. **Load store** — `subscribes/store.py:load_subscribes` from `~/.neurolearn/subscribes.toml`.
2. **Filter** — `subscribes/group.filter_by_group` (`--group`), `--platform`, optional `--match`/`--filter`.
3. **Per-channel fetch** — YouTube (v0.20+): `_fetch_youtube_entries` routes by `mode` (auto/videos-only/shorts-only/shorts-and-videos). Each stream is an early-exit walk over a channel tab (`_fetch_videos`→`/videos`, `_fetch_shorts`→`/shorts` via shared `_fetch_tab`): flat-list IDs newest-first → per-id extract for date → stop at first out-of-window. RSS retired (it leaked livestreams + was empty for some channels); `--no-rss` is a deprecated no-op. IG/TikTok always via yt-dlp + cookies (`_fetch_via_yt_dlp`).
4. **State-aware window** — default: per-channel `published > last_seen_published`. With `--days`/`--since`/`--until` override → global window, state NOT updated (INV-009 mutex still applies).
5. **Batch pipeline** — `batch_pipeline._run_batch_pipeline` on the gathered videos.
6. **Update state** — only when no override flags were used; persists `last_seen_video_id` + `last_seen_published` back to `subscribes.toml` via `store.update_seen_state`.
7. **Optional analyze + learn-into** — INV-012 auto-detect respected.

**Termination:** state updated (exit 0) OR exit 2 (`SubscribesError`) / 3 (cookies missing for IG/TT).

**Related invariants:** INV-009, INV-010, INV-011, INV-012, INV-013 (no anthropic).

## FLOW-006 — `memory learn` with Claude-extract branching

**Entry:** `neurolearn memory learn <name> <URL_or_path> ...` → `skills/neurolearn/memory/cli.py:memory_learn_cmd`

1. **Collect transcripts** — for each source: URL → `backends/factory.run_smart` (smart cascade transcribes); file/dir → `_load_transcript_from_path` reads existing transcript. Output: `list[TranscriptInput]`.
2. **Mode branch** — `memory/learn.py:learn`. `use_claude_extract = claude_extract if explicit else bool(CLAUDE_PLUGIN_ROOT)` (INV-012).
3a. **Claude-extract path** (inside Claude Code, default) — `learn.py:write_learn_briefing` writes `<pending>/briefing.md` + `transcripts.json` + reserves `<pending>/approved.json` path. NO LLM call. Exit with hint pointing at next command. User flow continues OUT-OF-PROCESS (Claude in chat reads briefing, asks user, writes approved.json).
3b. **Groq path** (`--no-claude-extract` or non-Claude-Code) — for each transcript: `learn.py:_build_diff_prompt` (with INV-008 caps) → `analyze.runner.run_analysis` (Groq llama-3.3-70b) → `_parse_candidates` → `approve_candidates_interactive` (TTY y/n/a/q; non-TTY needs `--yes` else returns `[]`) → `store.append_facts_to_body` → optional `_autogenerate_description` for new memories.
4. **Persist** — `store.write_memory` (atomic temp+rename, updates `last_updated` + `sources` count).

**Termination:** Claude-extract mode = briefing files written, exit 0. Groq mode = memory file appended (or unchanged if 0 approved), exit 0.

**Related invariants:** INV-006, INV-007, INV-008, INV-012, INV-013.

## FLOW-007 — `memory append-facts` — pure write, zero LLM

**Entry:** `neurolearn memory append-facts <name> --from-file <approved.json>` → `skills/neurolearn/memory/cli.py:memory_append_facts_cmd`

1. **Read approved.json** — `memory/learn.py:append_approved_from_file` → `json.loads` (INV-006 on parse failure).
2. **Schema check** — must be `{"candidates": [...]}` shape (INV-007 on wrong shape).
3. **Group by source_url** — each unique URL counts as one `memory.sources` increment.
4. **Append** — `store.append_facts_to_body` per source group, groups by `topic` within each source.
5. **Optional description autogen** — only if `not in_claude_code AND no description AND has body AND analyze_backend supplied`. Inside Claude Code (`CLAUDE_PLUGIN_ROOT` set) this is skipped — INV-012/INV-013 say Claude in chat should describe via `memory show` if needed.
6. **Persist** — `store.write_memory` (atomic).

**Termination:** memory file updated, exit 0. OR exit 2 (`ValueError` from schema check) / exit 3 (`FileNotFoundError` for approved.json).

**Related invariants:** INV-006, INV-007, INV-012, INV-013.
