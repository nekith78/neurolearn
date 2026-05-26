# Changelog

All notable changes to neurolearn will be documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [0.16.1] — 2026-05-26

`--learn-into <memory_name>` flag added to `batch`, `research`, and
`subscribes update`. After transcribe finishes, the named memory file
ingests the batch via the standard learn flow (LLM diff against
existing facts + interactive approval or `--yes` for auto-approve).
Reduces a two-step workflow (transcribe → memory learn) to one
command, which matters most from Claude Code chat: Claude no longer
has to remember to chain a second tool call after batch.

### What the flag does

```bash
neurolearn batch URL1 URL2 --learn-into claude-tips
neurolearn subscribes update --group ai --days 7 --learn-into ai-news
neurolearn research "agentic safety" --days 90 --learn-into safety-research
```

For each, after the transcribe pipeline writes `combined.md` +
`videos/*.txt`, the post-hook calls
`memory.cli.run_learn_into_batch()` which:

1. Builds a `TranscriptInput` per `videos/*.txt` (with URL recovered
   from `manifest.json` when present).
2. Calls `memory.learn.learn()` with the existing cfg's
   `analyze_backend`.
3. With `--yes`, auto-approves all candidates; otherwise interactive
   TTY prompt or skip-with-hint in non-TTY (Claude Code subprocess).

### Bug surfaced + fixed alongside

Live end-to-end test exposed a silent failure mode in the v0.16.0
diff prompt: free-tier Groq llama-3.3-70b has a **12 000 TPM rate
limit**. The previous prompt used `transcript[:20000]` + `body[:8000]`
which together with scaffolding totalled ~15 000 tokens on technical
English transcripts → HTTP 413 → `run_analysis` silently swallowed
the exception and returned `""` → parser saw 0 candidates → user got
a confusing "0 candidates proposed" message with no clue why.

Two fixes:

- Tightened size budget in `_build_diff_prompt`: transcript chunk
  20000 → 9700 chars, memory body 8000 → 1600 chars. Calibrated to
  ~0.72 tokens/char on technical English (Groq tokenizer is dense),
  staying under ~8700 tokens total with headroom for the 12k TPM cap.
- `extract_candidates()` now prints an explicit stderr hint when the
  LLM returns empty: surfaces the most likely cause (rate limit /
  missing key / provider transient).

### Live verification (qa-out/v0.16.1-live/)

Two-stage demo against real subscribed channels:

- **Stage A**: `subscribes update --group test-coding --days 3 --learn-into claude-coding`
  Pulled 5 fresh videos from the @claude channel (Code with Claude
  conference talks), transcribed in 313 s, ran learn — produced
  5 facts + auto-generated 458-char description about Cloud Managed
  Agents / Agent SDK / Managed Agents / Agent Development.

- **Stage B**: feed the older "Context Management in Claude Code"
  transcript into the SAME memory. The LLM correctly identified
  8 NEW facts across 5 topics (Context Window, Slash Commands,
  MCP Servers, Skills, Sub-Agents) — none of which overlap with
  Stage A's "Managed Agents" topics. Confirmed the dedup logic
  works against accumulated memory.

### Files

- `skills/neurolearn/memory/cli.py` — new public
  `run_learn_into_batch(batch_dir, memory_name, cfg, auto_yes)`
  helper + manifest-aware URL recovery
- `skills/neurolearn/transcribe.py` — `--learn-into` option on
  `batch_cmd` and `research_cmd`; post-transcribe hook
- `skills/neurolearn/subscribes/cli.py` — same on `update_cmd`
- `skills/neurolearn/memory/learn.py` — tightened size budget,
  added "LLM returned empty response" hint with cause hypothesis

Tests: **1330 passed**, 2 skipped (no new tests — flag wiring is
straightforward; existing `test_memory_learn.py` covers the
extraction/approval/diff logic that `--learn-into` reuses).

## [0.16.0] — 2026-05-26

Two user-requested features land in this minor release: subscribes
can now resolve channels from arbitrary video / post URLs, and
neurolearn gets a brand-new **memory** subsystem — curated knowledge
bases that grow over time from transcribed content with explicit
user approval at every step.

### Feature 1 — `subscribes add` accepts video / post URLs

Previously: paste `https://youtube.com/watch?v=...` to subscribes →
`URL doesn't look like a YouTube / Instagram / TikTok profile or
channel`. You had to find the channel URL manually.

Now: `subscribes add` accepts any URL we recognise. If it's a video /
post URL, we ask yt-dlp once for the owning channel URL and recurse
into the existing channel-resolution logic. Works across YouTube
(`/watch`, `/shorts`, `/embed`, `/live`, `youtu.be/`), Instagram
(`/p/`, `/reel/`, `/reels/`, `/tv/`), and TikTok (`/@user/video/`,
short `vm.tiktok.com` and `vt.tiktok.com` redirects).

### Feature 2 — `memory` command group

Memory files are curated, append-only knowledge bases stored as
plain Markdown with YAML frontmatter at `~/.neurolearn/memories/`
(or `cfg.memories_dir` if you want them in your Obsidian vault).
The flow:

  1. `memory create <name> [--description "..."]`
  2. `memory learn <name> <URL> [<URL> ...]` ingests transcripts.
     For each transcript the LLM extracts candidate-new facts
     vs. what's already in the memory. The user approves each
     interactively (y / n / a=approve-all / q=quit) before anything
     gets written. Use `--yes` to skip the prompts.
  3. Approved facts are appended grouped by topic, with source URL
     and timestamp range preserved.

  Other commands: `memory list`, `memory show <name>`,
  `memory rename <old> <new>`, `memory delete <name>`.

  Description handling: if user passes `--description` at create,
  that's used verbatim and never overwritten. If the description is
  blank when the first `learn` completes, a 2-sentence SCOPE summary
  is auto-generated from the accumulated facts. User control over
  the description is preserved either way.

  Renaming updates BOTH the on-disk filename and the `name:`
  frontmatter field, so the file stays consistent.

  Storage format intentionally markdown-with-YAML so it's
  hand-editable and renders directly in Obsidian / Notion / GitHub
  / VSCode without tooling. No proprietary format. Comments and
  manual edits to the body survive `learn` calls.

  Use case the user described: «возьми эти видео и выпиши только
  новое относительно того что у меня уже накоплено». Smart-cascade
  prompt asks the LLM to be conservative — when unsure if something
  is genuinely new, skip it; never paraphrase duplicates.

  End-to-end smoke verified: ran `memory learn` on the cached
  transcript of "Context Management in Claude Code" — extracted 10
  facts across 7 topics (Context Window / Slash Commands / Context
  Management / MCP Servers / Sub-Agents / Skills / Claude.md File),
  each with source-URL + timestamp range. Output is hand-editable
  Markdown that renders cleanly in GitHub preview.

### Files

  skills/neurolearn/subscribes/channel_resolver.py
    + `_looks_like_video_url()`
    + `_channel_url_from_video()` — yt-dlp lookup
    `resolve_channel()` now recurses through the helper when the URL
    isn't a channel URL but matches a video/post pattern.

  skills/neurolearn/memory/                     — NEW package
    __init__.py
    store.py        — CRUD + slug + frontmatter parse/serialize
    learn.py        — LLM diff prompt + JSON-robust parser +
                      interactive approval + auto-description
    cli.py          — create/list/show/rename/delete/learn commands

  skills/neurolearn/config.py
    + `memories_dir: str = ""` field with [memory] TOML section

  skills/neurolearn/transcribe.py
    + `cli.add_command(memory_group)` at the bottom

  tests/test_memory_store.py    — 16 tests
  tests/test_memory_learn.py    — 17 tests

  Total: 33 new tests + memory-file end-to-end smoke verified
  against a real LLM call.

### Not in this release (deferred to v0.16.1)

`--learn-into <memory-name>` flag on `batch` / `subscribes update` /
`research` — convenience sugar that auto-runs `memory learn` after
the transcribes finish. The standalone `memory learn <name> <URL>
<URL> ...` covers the same use case; the flag just removes one step.
Saving for v0.16.1 to keep this release focused on the core
abstraction.

Tests: **1330 passed**, 2 skipped.

## [0.15.4] — 2026-05-24

Two UX fixes that came out of investigating the v0.15.3 release:
silent fallback is bad for both TTY and Claude Code chat users, and
the Path 2 yt-dlp subtitle fetch took whichever subtitle file
matched first rather than preferring uploader-provided (manual)
captions over machine-generated ones.

### Fix 1 — context-aware smart cascade fallback

`backends/factory.py::run_smart` previously did a silent fallback to
`whisper-local` whenever the configured fallback backend (typically
`groq`) was missing its API key. The user got a transcript via slow
local Whisper without knowing why — they'd assume Groq was working
fine, miss out on the 19× realtime speed they expected, and never
realize the key was missing.

New behavior is context-aware:

- **Claude Code chat** (`CLAUDE_PLUGIN_ROOT` env var set): raise
  `BackendNotConfigured` with a structured 4-step fix instruction:
  ```
  groq backend not configured (GROQ_API_KEY missing).
    Two-minute fix:
      1. Get a key at https://console.groq.com/keys
      2. Save it to a file (any path), e.g. ~/keys/groq.txt
      3. Register: neurolearn config set-key groq --from-file <path>
    Or pass `--backend whisper-local` to skip this video offline.
  ```
  Claude reads exit 3, recognizes the pattern (same as the v0.13.0
  onboarding gate + v0.14.0 anti-bypass), asks the user, gets the
  key file path back, registers it, and auto-resumes the original
  request.

- **TTY** (human at terminal): interactive prompt with three choices:
  `Y` (configure now — get URL + register command), `n` (one-time
  fallback to whisper-local), `c` (cancel).

- **Pure non-TTY** (CI, background batch worker, no
  `CLAUDE_PLUGIN_ROOT`): preserve the original v0.10.x silent-fallback
  behavior. Batches of 100 videos cannot hang on a stdin prompt.

### Fix 2 — yt-dlp subtitle fetch prefers manual over auto-generated

`backends/subtitles.py::_fetch_via_yt_dlp` previously invoked yt-dlp
with BOTH `--write-subs` and `--write-auto-subs`, then took whichever
subtitle file matched `glob("*.srv3")` first. yt-dlp's filename
convention doesn't reliably indicate which is which, so the choice
was effectively arbitrary.

The new two-pass logic explicitly prefers uploader-provided captions:

```
Pass 1: yt-dlp --write-subs ONLY (manual / uploader-provided)
   ↓ found a file?
        yes → use it, return
        no  → continue
Pass 2: yt-dlp --write-auto-subs ONLY (YouTube's machine ASR)
   ↓ found a file?
        yes → use it, return
        no  → BackendError → smart cascade falls to groq/whisper-local
```

Path 1 (youtube-transcript-api) already preferred manual by library
default (`YouTubeTranscriptApi.fetch()` calls `find_transcript()`
which checks manual lineage first). Now both paths have consistent
preference order.

### Files

- `skills/neurolearn/backends/factory.py` — new
  `_handle_unconfigured_fallback()` helper with TTY / Claude Code
  chat / non-TTY branching
- `skills/neurolearn/backends/subtitles.py` — extracted
  `_run_yt_dlp_subtitle_pass()` helper; `_fetch_via_yt_dlp()` now
  calls it twice with `write_auto=False` then `write_auto=True`
- `tests/test_factory.py` — 4 new tests for the context branching
- `tests/test_subtitles.py` — 3 new tests for the manual-preference
  cascade

Tests: **1297 passed**, 2 skipped.

## [0.15.3] — 2026-05-24

Closes the last open finding from the v0.15.2 benchmark — `subtitles`
backend silently failing with `IpBlocked` even when cookies are
registered. The investigation surfaced **three separate causes**
stacked on top of each other; this release addresses all three.

### Investigation summary

After three years of "the subtitles backend sometimes IP-blocks,
just use smart cascade", we finally dug in:

1. **Config slot mismatch.** `neurolearn config set-cookies` writes
   the YouTube cookies path into `cfg.cookies_file` (legacy slot
   from pre-v0.10.7 lineage). But `resolve_cookies_file("youtube")`
   only checked `cfg.youtube_cookies_file`. So even though `doctor`
   correctly reported the file as registered (it falls back to the
   legacy slot for display), the subtitles backend's session
   builder got an empty path and proceeded anonymously → IpBlocked.

2. **No yt-dlp fallback path.** The subtitles backend used only
   `youtube-transcript-api`, which talks to the timedtext endpoint
   directly via Python requests. YouTube rate-limits this endpoint
   aggressively — even with full auth cookies (SID, SAPISID,
   LOGIN_INFO, etc.) — because the requests don't carry the player
   handshake yt-dlp performs.

3. **No TLS impersonation.** Even when yt-dlp could be invoked, it
   warned "extractor specified to use impersonation for this
   download, but no impersonate target is available" because
   `curl_cffi` wasn't in our dep tree. YouTube increasingly
   distinguishes bot traffic at the TLS-fingerprint level
   (ClientHello), distinct from cookies and PO Token. Without
   curl_cffi yt-dlp can't spoof Chrome/Firefox TLS → 429 on
   subtitle endpoints regardless of other auth.

### Why we didn't use the YouTube Data API instead

YouTube Data API v3's `captions.download` endpoint requires OAuth
**as the video owner** (or 3rd-party-contribution permission on the
specific video). For arbitrary public videos: 403 Forbidden. So
`youtube-transcript-api`, `yt-dlp --write-subs`, `pytube`,
`innertube` — they all use the same internal `timedtext` endpoint.
The difference is only in the auth layer they wrap around it.

### Fixes

**1. Slot fallback in `resolve_cookies_file()`**
   `cookies_onboarding.py` now reads `cfg.youtube_cookies_file or
   cfg.cookies_file` for the youtube platform. Existing users with
   cookies registered via the legacy `config set-cookies` command
   get them recognized immediately — no re-registration needed.

**2. Two-tier subtitle fetch in `SubtitlesBackend`**
   Path 1 (fast, ~3 s): youtube-transcript-api with cookies session
   — unchanged from before, just now actually gets the cookies.
   Path 2 (slower, ~5-8 s): yt-dlp `--write-auto-subs --write-subs`
   using our full anti-block stack (cookies + PO Token plugin +
   curl_cffi). Falls through automatically on Path 1 IpBlocked /
   RequestBlocked / PoTokenRequired / YouTubeRequestFailed /
   YouTubeDataUnparsable. Permanent errors (TranscriptsDisabled,
   NoTranscriptFound) skip Path 2 since yt-dlp can't help either.

**3. New dep: `curl_cffi>=0.10,<0.15`**
   yt-dlp uses curl_cffi automatically for TLS-fingerprint
   impersonation when available. The version range matches yt-dlp
   2026.03.17's supported set (importing 0.15+ raises ImportError).
   No code change needed — yt-dlp picks it up at import.

### Files

- `skills/neurolearn/subscribes/cookies_onboarding.py` — legacy-slot fallback
- `skills/neurolearn/backends/subtitles.py` — Path 1 / Path 2 cascade,
  new `_parse_yt_dlp_subtitle_file()` for json3/srv3 formats
- `pyproject.toml` — `curl_cffi>=0.10,<0.15`
- `tests/test_subtitles.py` — 4 new test cases (json3 parser, srv3
  parser, transcript-api-blocked-falls-through-to-yt-dlp, legacy-slot
  fallback)

### Live verification

On my IP at release time, YouTube is rate-limiting subtitle endpoints
across *both* paths (429 Too Many Requests even with full TLS
impersonation + auth cookies + PO Token). Confirms the cascade
correctly tries Path 2 when Path 1 blocks. Smart cascade then falls
through to groq, transcribing the video in 16.3 s. Users on `--backend
smart` (the default) never see a failure.

Tests: **1290 passed**, 2 skipped.

## [0.15.2] — 2026-05-24

Cleanup release for the four real issues surfaced by the v0.15.2
benchmark run on a 3:30 reference video (see `docs/BENCHMARKS.md`):

### Fixed

1. **Vision pipeline crashed with `GroqTokenUsage.cached_tokens`
   AttributeError** (`pipeline_v02.py`). The pipeline assumed all
   vision backends expose a cached-tokens counter. Groq doesn't —
   it has no prompt cache. Fix: `getattr(usage, "cached_tokens", 0)`.
   Shipped in 450bc94, included here for completeness.

2. **`report` now accepts single-video transcribe output directories.**
   Previously `report` only accepted batch dirs (with `manifest.json`).
   Users running `transcribe URL` then `report .` got `exit 3 — No
   manifest.json`. Fix: when no manifest is found, synthesize a
   minimal 1-video manifest on the fly from the `.txt` + `.srt` files
   present in the dir. `_try_synthesize_single_video_manifest()` in
   `report/orchestrator.py`.

3. **`research` no longer silently exhausts the Gemini free-tier
   quota** (`research/pipeline.py`). When user's `default_backend` is
   `gemini` and they run `research --limit N`, the previous behavior
   was to call gemini for every video, exhausting the 20 req/day free
   limit on call #1 and leaving the entire batch as `failed`. New
   behavior: auto-switch this batch to `smart`, which cascades to
   `fallback_backend` (typically `groq`, 14 400 req/day free) on
   gemini quota exhaustion. The user's persistent config isn't
   touched — only this one batch. A stderr line surfaces the
   auto-switch.

4. **`report` shows a clearer message when the outliner returns 0
   sections** instead of just `✓ Report rendered (0 sections)`. New
   wording explains the outliner found no sectional structure
   (common on short videos < 5 min) and notes the PDF still has
   title + metadata.

### Not fixed (documented as workarounds in docs/BENCHMARKS.md)

5. **`subtitles` backend can still IP-block even with cookies
   registered.** This is a `youtube-transcript-api` limitation — it
   talks to a different endpoint than yt-dlp and doesn't share our
   cookies file. Workaround: smart cascade auto-falls-back to `groq`
   on subtitles miss. A proper fix means routing subtitles through
   yt-dlp directly — bigger change deferred.

### Files

- `skills/neurolearn/report/orchestrator.py` — `_try_synthesize_single_video_manifest()`
- `skills/neurolearn/transcribe.py` — synthesis fallback in `report` cmd
  + new clearer 0-sections message
- `skills/neurolearn/research/pipeline.py` — auto-switch to smart when
  default_backend=gemini for batch context

Tests: **1281 passed**, 3 skipped (no new tests — fixes are runtime UX,
not algorithmic).

## [0.15.1] — 2026-05-23

User regression-tested v0.14.2's hallucination filter across 5
different content formats (music / tech-talk / interview / news /
tutorial) in EN + RU. Found 1 false positive: the Rick Astley intro
filter dropped the real lyric "We're no strangers to love" because
Whisper stretched its timestamp across the 21.88s instrumental intro,
giving 1.19 chars/sec — below the v0.14.2 density threshold.

Then user laid down a hard requirement: *transcribe what was said,
don't invent or modify content*. The density heuristic was technically
right (low cps = suspicious) but happened to discard real speech
content. That was a deal-breaker.

This release replaces the single-heuristic filter with a 3-layer
input + output mitigation stack, informed by an empirical Groq API
probe and the OpenAI Whisper community's published mitigations.

### What we tried that turned out to NOT work on Groq

Research said: use Whisper's own confidence fields from `verbose_json`
to filter low-confidence segments. Empirical probe of Groq's actual
response (`qa-out/v0.15.1-probe/probe_groq_confidence.py`) revealed:

- `no_speech_prob` is always 0 or near-zero (e.g. 2e-11) regardless
  of whether the segment is real speech, silence, or hallucination.
  Not discriminative.
- `avg_logprob` returns the SAME value across batches of segments
  (e.g. -0.13 for "Python Python" and the following real sentence
  in the same window). Per-segment confidence is not actually
  per-segment on Groq.
- `compression_ratio` peaks at 2.31 across our corpus — never crosses
  OpenAI's 2.4 hallucination threshold. Filter would never fire.
- `temperature` always 0 (no fallback retries).

So Whisper-confidence-based filtering simply doesn't work on Groq's
deployment. Recommendation stayed for openai/faster-whisper users.

### What we built instead — 3 layers

**1. Silence-edge trim (input-side).**
`utils/audio_chunker.trim_silence_edges()` — finds leading/trailing
silence > 1.5s via ffmpeg `silencedetect`, cuts it before sending to
Groq. Tracks `leading_trim_seconds` so the caller can offset segment
timestamps back to the original timeline. The Groq backend now trims
every chunk (whether chunked or not) before upload, and the merged
segment timestamps include the trim offset.

Validated on Python tutorial: "Python Skynet sky net" hallucination
that v0.14.2 caught at the output side now never appears in Groq's
output at all — silence-trim removed the trigger.

**2. Word-variety check on density filter (output-side).**
`hallucination_filter._distinct_word_stems()` — counts distinct word
stems (first 4 chars, case-insensitive, punctuation-stripped). The
density filter now requires BOTH `cps < 2` AND `distinct_stems ≤ 2`
before dropping. Real speech with mistimed bounds (like the Rick
Astley lyric: 6 distinct stems "were/no/stra/to/love" + grammar
words) survives. Whisper-invented repetitive fillers ("Python Python"
= 1 stem, "Subscribe to my channel" = 4 stems but blocklisted) still
drop.

**3. Blocklist (unchanged from v0.14.2).**
Conservative whole-segment-match against documented Whisper fillers.

### Removed

`compression_ratio` / `avg_logprob` / `no_speech_prob` post-filter
ideas — empirically don't work on Groq.

### Verified

Re-ran the 5-video regression with v0.15.1:

| Video | v0.14.2 drops | v0.15.1 drops | Δ |
|---|---|---|---|
| Rick Astley | 1 FALSE POSITIVE | **0** | lyric preserved ✓ |
| TED-Ed | 0 | 0 | — |
| Interview RU | 3 (all empty) | 4 (all empty) | +1 caught |
| BBC News | 0 | 0 | — |
| Python tutorial | 3 ("Python Python" + "Python Skynet sky net" + empty) | 2 ("Python Python" + empty) | "Python Skynet sky net" prevented at input via silence-trim |

Result: **0 false positives**, still catches all Whisper-invented
phantoms, real speech with mistimed bounds is preserved.

### Files

- `skills/neurolearn/utils/audio_chunker.py` — new `trim_silence_edges()`
- `skills/neurolearn/utils/hallucination_filter.py` — `_distinct_word_stems()`
  + word-variety check folded into `is_hallucination()`
- `skills/neurolearn/backends/groq.py` — per-chunk silence-trim with
  `trim_offset` propagated through segment reassembly + cleanup of
  trim tmp files
- `tests/test_hallucination_filter.py` — new word-variety + Rick
  Astley keep-test cases

Tests: **1281 passed**, 3 skipped.

## [0.15.0] — 2026-05-22

User running research across multiple projects hit YouTube IP blocks
(*"Sign in to confirm you're not a bot"*) with no fallback path. The
existing cookies feature was already in the codebase but the wizard
never asked about it, so most users never registered them. Same story
for Instagram and TikTok — cookies slots existed, never surfaced.

v0.15.0 introduces a 3-layer **anti-block cascade** that works
across YouTube, Instagram, and TikTok transparently. Same philosophy
as the smart audio cascade: figure out at runtime what's available,
escalate automatically, fail loudly with a platform-specific fix
instruction when escalation is exhausted.

### Three layers

1. **Cookies** (user-registered) — logged-in session gets ~10× the
   rate limit of anonymous requests. Wizard now asks during step 4.
2. **PO Token plugin** (`bgutil-ytdlp-pot-provider`, auto-installed)
   — generates the cryptographic anti-bot token YouTube wants from
   real browser sessions. Auto-registers with yt-dlp at import.
   Needs Node.js 16+ on PATH; degrades gracefully without it.
3. **Residential proxy** (user-supplied, optional) — IP-level escape
   hatch for very heavy research. Not wired into a CLI flag yet but
   `HTTPS_PROXY=` env var works today. Documented in the new
   `docs/UNLIMITED_RESEARCH.md`.

### Cascade behavior

  ```
  Attempt 1: anonymous   (if user picked "light" volume)
          or with cookies (if "heavy" volume + cookies registered)
     ↓ blocked
  Attempt 2: with cookies (if attempt 1 was anonymous + cookies registered)
     ↓ blocked OR no cookies were available
  Fail: exit code 8 + platform-specific fix instruction
  ```

  Maximum 2 attempts. Most calls = 1 attempt.

### Wizard step 4 — platforms + cookies + volume

`config wizard` (now 4 stages instead of 3) asks at install time:

  - Multi-select: YouTube / Instagram / TikTok / local-only
  - For each picked platform: path to cookies.txt (skippable)
  - For each picked platform: "light" (< 20 videos/week) or "heavy"
    (20+) — drives whether the cascade starts anonymous (preserves
    cookie lifetime) or goes straight to cookies (avoids the doomed
    anonymous attempt for heavy users).

Pre-v0.15.0 users keep their existing config; the cascade defaults
to "light" volume + uses whatever cookies are already registered.

### Platform-aware error classification

New `utils/platform_errors.py` distinguishes:

  - **Anti-bot / rate-limit blocks** — retryable with cookies; cascade escalates.
  - **Login-required resources** — private accounts, members-only — cookies of an authorized user help.
  - **Truly unavailable** — deleted, geo-blocked, extractor broken — no retry, distinct error path so the cascade doesn't waste cycles.

Per-platform error patterns (YouTube / Instagram / TikTok) + generic
fallback patterns. New `fix_instruction()` generates the exact
platform-specific multi-line message printed on exit code 8.

### New exit code 8

`transcribe` / `batch` now exit with code 8 (was code 4) when blocked
by a platform. CI / Claude in chat can branch on this to surface
the right one-shot action instead of treating it as a generic
transcription failure.

Batch keeps going on per-video block (records `BatchFailure(stage="block")`
with the fix instruction in `errors.log`); only single `transcribe`
exits the process with code 8.

### Cookies via `--from-file <path>`

Both `config set-cookies` and `subscribes cookies set` now accept
`--from-file <path>` as an alias for the positional form. Consistent
with `set-key --from-file` (v0.13.0). Driven from Claude Code chat
so the file path stays out of conversation logs.

### Doctor surfaces the cascade

`neurolearn doctor` (and `doctor --json`) now show:

  - Node.js availability
  - PO Token plugin installation
  - Per-platform cookies registration + volume preference
  - Recommended setup hints (e.g. "you picked heavy YouTube but no cookies registered")

The JSON payload exposes `anti_block.*` so Claude in chat can read
the current cascade state and walk the user through the right fix.

### Files

  - `skills/neurolearn/utils/platform_errors.py` — new
  - `skills/neurolearn/utils/anti_block_cascade.py` — new
  - `skills/neurolearn/utils/downloader.py` — `download_audio` / `download_video` opt into cascade via new `cfg` arg
  - `skills/neurolearn/config.py` — `selected_platforms`, per-platform `*_research_volume`
  - `skills/neurolearn/wizard.py` — step 4 (platform multi-select + cookies + volume)
  - `skills/neurolearn/transcribe.py` — exit code 8, doctor anti-block section, `--from-file` alias
  - `skills/neurolearn/subscribes/cli.py` — `--from-file` alias
  - `pyproject.toml` — `bgutil-ytdlp-pot-provider>=1.3` as regular dep
  - `tests/test_platform_errors.py` — 29 cases
  - `tests/test_anti_block_cascade.py` — 18 cases
  - `docs/UNLIMITED_RESEARCH.md` — new — 3-layer guide
  - `docs/TROUBLESHOOTING.md` — rewritten yt-dlp 403 section

Tests: **1279 passed**, 3 skipped.

## [0.14.2] — 2026-05-22

Verification of v0.14.1 on a real 4-hour video surfaced a separate
issue: Whisper hallucinates a phantom segment at the end of audio
with trailing silence. User caught it: their 3h57m34s video produced
a transcript with a final segment "Продолжение следует..." (To be
continued...) spanning **30 seconds** for 3 words at 03:57:34 →
03:58:04 — past the actual video end.

This is a well-documented Whisper failure mode (`m-bain/whisperX#1064`,
`Whisper-WebUI/blob/master/modules/utils/blacklist.py`): the model
fills silent / musical tails with phrases it has seen often in
training data (Russian YouTube credits like "Продолжение следует",
English vlog closers like "Subscribe to my channel"). The chunker
preserved end-to-end timestamps correctly — the bug is in Groq's
returned segments, not our reassembly.

### Two-layer hallucination filter

New `utils/hallucination_filter.py`:

1. **Density filter** — segments where `duration ≥ 5s` AND
   `chars_per_second < 2` are dropped. Real speech is 8-20 cps; a
   phrase under 2 cps on a multi-second segment can only be a
   silence-fill.

2. **Blocklist** — case-insensitive whole-segment match against a
   conservative list of known Whisper fillers (RU: "Продолжение
   следует", "Субтитры сделал dimatorzok", credit-line patterns;
   EN: "Subscribe to my channel", "(music)", "(applause)"). Common
   real-speech endings ("спасибо большое", "thanks for watching")
   are deliberately NOT blocklisted — they're real in interviews
   and vlogs, and the density filter catches them when they're
   actually hallucinations.

The two filters compose; a segment dropped by either is excluded.
Conservative by design — when in doubt, the segment stays. The
filter runs on the merged Groq result so it sees the full
reassembled timeline.

### Effect on real data

Re-applying the filter to the v0.14.1 verification SRT
(`qa-out/v0.14.1-real-test/`, 4477 segments):

| Caught | Span | Density | Text |
|---|---|---|---|
| Tail | 14254→14284s | 0.73 cps | "Продолжение следует..." ← user's report |
| Mid | 2820→2850s | 0.87 cps | "Это лимитированная работа." (30 s for 26 chars) |
| Mid | 1772→1786s | 0.51 cps | "100 100" |
| Mid | 3550→3561s | 0.53 cps | "4 4 90" |
| Mid | 10677→10690s | 0.24 cps | "5 7" |
| Mid | 12462→12473s | 1.23 cps | "Rolls 900 170" |
| 2× | various | 0.00 cps | empty-text segments |

**8 of 4477 segments dropped; 4469 real segments preserved.** All
short real signoffs survived ("Спасибо.", "Честь.", "Сила в любви.").

### Files

- `skills/neurolearn/utils/hallucination_filter.py` — new module
- `skills/neurolearn/backends/groq.py` — applies the filter after
  reassembling chunks
- `tests/test_hallucination_filter.py` — 20 cases covering the
  density filter, the blocklist, and the user's exact tail pattern

Other backends (whisper-local, OpenAI, Deepgram, AssemblyAI) have
the same hallucination class; wiring the filter into them is
follow-up work. Groq is fixed today because that's where the user
caught it.

Tests: **1232 passed**, 3 skipped.

## [0.14.1] — 2026-05-22

User hit a confusing failure: Groq Whisper rejected a video as
"too large" with no warning ahead of time. Groq's free tier caps
audio uploads at 25 MB — typical m4a from yt-dlp crosses that
around 17 minutes. Above ~2 hours even Opus-recompressed audio
won't fit, so the existing recompress path was a half-fix.

v0.14.1 makes audio size handling **fully transparent**: the user
never has to think about it, even from inside a Claude Code chat
session (no TTY assumptions).

### Opus 24 kbps mono recompression (replaces AAC 32k)

`GroqBackend` now re-encodes oversized inputs to **Opus 24 kbps
mono at 16 kHz** instead of AAC. Whisper internally downsamples
everything to 16 kHz mono anyway, so this is lossless for
transcription — but ~5.4× smaller payload than typical YouTube
audio. Math:

- 1 hour of audio → ~11 MB (was ~14 MB on AAC 32k)
- 2h15m → ~25 MB (just under the free-tier limit before chunking)

Side-by-side comparison artifact:
`qa-out/v0.14.1-opus-compare/{original_1min.m4a, recompressed_opus_24k_mono.ogg}`.

### Adaptive chunking with silence-boundary cuts

Beyond 2h15m on free tier (or ~9 hours on paid), even Opus can't
squeeze it in one upload. The new `utils/audio_chunker` module:

1. Computes the **minimum N chunks** that fit the tier's limit.
   A 3-hour Opus file (~33 MB) splits into 2 halves, not eight
   10-minute pieces.
2. Runs `ffmpeg silencedetect` to find silent intervals (<-30 dB,
   ≥0.4 s). For each ideal cut point, picks the closest silence
   in a progressively widening window (5% → 50% of segment width).
3. Splits with `ffmpeg -c copy` (stream copy, no re-encode) so the
   chunks stay the same size as the planned slices.
4. **Reassembles segment timestamps** by adding each chunk's
   start offset to every segment's start/end. End-to-end timeline
   matches the original video.

Verification on a real 10:32 video at `qa-out/v0.14.1-chunking-verify/`:

- 3 chunks, both cuts landed inside silence intervals
  ([212.64, 213.17] and [429.54, 430.16])
- Baseline single-call span: 0.00–631.72 s
- Chunked reassembled span:   0.00–631.70 s — timestamps align
- Boundary gaps: +0.15 s and +0.54 s (under 2 s, no mid-word cuts)
- Text fidelity: 99.7% chars between baseline and chunked

### Tier-aware upload limits

`GroqBackend.tier` (forwarded from `cfg.groq_tier`) picks the right
ceiling per tier with a 1-2 MB headroom for HTTP multipart overhead:

| tier | wire limit | usable |
|---|---|---|
| free | 25 MB | ~24 MB |
| paid / paid-tier2 / paid-tier3 | 100 MB | ~98 MB |

Unknown tier strings fall back to free — typos can't silently
enable a 100 MB upload that would then 413 on the wire.

### v0.14.0's "even after recompress, still too large" hard-error is gone

The old BackendError message that said "split the source into
shorter clips" no longer fires — the chunker handles that
automatically.

### Files

- `skills/neurolearn/utils/audio_chunker.py` — new module
- `skills/neurolearn/backends/groq.py` — Opus codec, chunked
  upload loop, segment offset reassembly, temp-file cleanup
- `skills/neurolearn/backends/factory.py` — forwards `cfg.groq_tier`
- `tests/test_audio_chunker.py` — chunker unit tests
- `tests/test_backend_groq.py` — tier limits, chunked transcribe,
  cleanup invariants
- `qa-out/v0.14.1-opus-compare/` — side-by-side audio comparison
- `qa-out/v0.14.1-chunking-verify/` — real-Groq round-trip report

Tests: **1212 passed**, 3 skipped.

## [0.14.0] — 2026-05-22

User reported that even after v0.13.0's forced onboarding gate, Claude
Code would STILL bypass the gate on first install. Specifically: user
pastes a URL, Claude runs transcribe → sees exit 7 → reads the offered
`--backend whisper-local` "override" in the error message → silently
re-runs with that flag to "not block the user". Result: onboarding
never happens, user gets slow local whisper, no API keys ever
registered, no preferred backend chosen.

v0.14.0 closes the bypass via three coordinated changes.

### Gate error message reworded

`_require_onboarding_complete` no longer presents `--backend whisper-local`
as an "override" option. The new message:

1. Frames setup as ONE-TIME ("under a minute"), not an obstacle.
2. Explicitly tells Claude to run `/setup` and **auto-resume the
   original request** after — no need to ask the user again.
3. Includes a "⚠ Claude:" addressed warning: "DO NOT auto-bypass this
   gate by adding `--backend whisper-local` to the command. Offline
   mode is a CHOICE the user makes during setup, not a workaround for
   the gate."

### SKILL.md HARD RULE strengthened

The Onboarding section now lists the explicit failure mode the gate
prevents:
- User never picks preferred audio backend (probably Groq).
- User never registers an API key.
- User runs slow local whisper instead of fast cloud Groq.
- Future runs continue to bypass setup forever.

The "Correct response when the gate fires" subsection makes the
stop-settings-resume pattern explicit:

```
User: "Transcribe https://youtu.be/xxx"
You:  [doctor --json → onboarding_complete=false]
You:  "neurolearn isn't fully set up yet — I'll walk you through setup
       first, then come back to transcribe right after."
You:  [/setup multi-step]
You:  [config complete-onboarding]
You:  [neurolearn transcribe https://youtu.be/xxx]   ← auto-resumed
You:  "Here's the transcript: ..."
```

The "When IS offline mode appropriate?" subsection enumerates the only
acceptable triggers for `--backend whisper-local`:
- User says "I don't want to give you any API keys".
- User says "use whisper-local".
- User says "skip setup".

Without one of those explicit signals, Claude must NOT pick offline.

### commands/transcribe.md + commands/setup.md updated

Both files got the same anti-bypass language and an explicit auto-
resume section. `commands/setup.md` now ends with a "Auto-resume the
original request (CRITICAL)" section that tells Claude not to stop
after the setup verification step.

### Tests

1184 → 1185 (+1):
- `test_onboarding_gate.py`: new `test_error_message_warns_against_auto_bypass_v014`
  verifies the stderr message contains "DO NOT", "auto-bypass" / "auto-resume",
  and "one-time" / "ONE-TIME" — without these, Claude reads the gate
  message and routes around it.

### Migration

No action needed. `onboarding_complete` semantics unchanged. The
behavior change is in the message text and Claude's instructions; the
gate itself still gates the same commands.

## [0.13.1] — 2026-05-22

Doc-and-cleanup release. A documentation audit against v0.13.0 code
surfaced 6 CRITICAL gaps where docs still pointed at v0.10/v0.11-era
behavior, and 25 HIGH-priority inconsistencies. This release fixes
all of them plus 2 small code cleanups discovered during the audit.

### Code

- **`doctor --json` exposes `config.onboarding_complete`** — was
  missing from the JSON payload, so `commands/setup.md` Step 0
  instructed Claude to read a non-existent field. Now exposed at
  `config.onboarding_complete` (boolean). Also added `vision_backend`
  and `analyze_backend` to the JSON config block for completeness.
- **`backend_resolver._VALID_BACKENDS` cleaned** — still contained
  `"claude"` despite v0.12.2 removing it from the Click choices.
  Cleanup: `("skip", "groq", "gemini", "openai", "ollama")`.
- **`_prompt_for_default` TTY menu** in `backend_resolver.py`
  reshuffled: option 2 is now `groq` (was `gemini`), option 3
  `gemini` (was `claude`).

### Documentation rewrites

CRITICAL fixes:
- **`commands/setup.md`** Step 0 — clarified the `config.onboarding_complete`
  read path (now in JSON since v0.13.1, plus alternative via
  `config get onboarding-complete --json`).
- **`commands/transcribe.md`** Step 0 — full rewrite. Old version told
  Claude to ask the user to paste API keys directly in chat. New version:
  hard gate based on `onboarding_complete` (exit 7), explicit
  "never accept keys in chat" rule, points at `--from-file` flow.
- **`commands/transcribe.md`** backend recommendation — v0.10.5-era
  "smart cascade subtitles → Gemini URL → fallback, 1 Gemini call"
  prose replaced with v0.12+ reality (Groq primary; vision quota
  uses Groq Llama-4-Scout default; extract-only mode inside Claude Code).
- **`HANDOFF.md`** — v0.8.0 → v0.13.0+, 898 → 1184 tests, full command
  list updated (added `report`, `doctor`, `schedule`,
  `complete-onboarding`), wizard described as TTY-only with Claude
  Code → `/setup` branch noted, dropped `anthropic` from the
  set-key example list (removed in v0.12.0).
- **`docs/agent-reference.md`** — added exit code 7 row to the failure
  table.
- **`CLAUDE.md`** — added v0.11/v0.12/v0.13 architecture invariants
  (Groq-default audio + vision, Anthropic API removal, onboarding gate
  + exit 7, secure key handoff via `--from-file`, vision extract-only
  mode under `$CLAUDE_PLUGIN_ROOT`); test count 1030 → 1184; `v0.10.2`
  "Out of scope" header re-versioned to v0.13.

HIGH fixes (sweep across all docs):
- Smart-cascade description corrected to v0.12+ flow
  (subtitles → Groq → whisper-local) in README, SKILL.md, agent-reference.
- Default vision backend = Groq Llama-4-Scout (not Gemini) across all
  vision-related sections.
- `--analyze-backend` choice lists no longer mention `claude` in
  README, SKILL.md, agent-reference (matches v0.12.2 Click choices).
- README Roadmap section refreshed: was frozen at v0.7, now spans
  v0.1 → v0.13.1 with capsule notes per major release.
- SKILL.md sub-commands list now includes `config get`,
  `config complete-onboarding`, mentions `--from-file` on `set-key`.
- agent-reference.md `config` sub-commands block enumerates all
  v0.12.2/v0.13.0 additions.

LOW fixes:
- `docs/cookies-walkthrough.md` — backup folder renamed
  `~/yt-tr-walkthrough-bak` → `~/neurolearn-walkthrough-bak` (and any
  remaining `yt-tr` aliases). Per project memory: yt-tr is not a valid
  alias.

### Test updates

- `tests/test_analyze_backend_resolver.py` — `claude` → `groq` /
  `gemini` migration across 3 tests to match the cleaned-up TTY menu.

### Migration

No action needed. Same `onboarding_complete = false` default behavior
as v0.13.0. If you'd already configured v0.13.0 and ran
`config complete-onboarding`, nothing changes. Docs match reality now.

Tests: 1184 still green.

## [0.13.0] — 2026-05-22

Major release. Two critical UX gaps surfaced during real-world fresh-machine
plugin install testing:

1. **Claude SKIPPED setup** on first run and started transcribing with
   whatever defaults the non-TTY auto-config had written. The user
   never got to choose their backends; the plugin just decided.
2. **API key handoff went through chat history** — the existing flow
   asked the user to paste their key in chat for `set-key groq <KEY>`,
   leaving the secret in conversation logs.

v0.13.0 fixes both with a hard gate + a secure key flow.

### Forced onboarding gate

New `Config.onboarding_complete: bool = False` field. While `false`,
`transcribe` / `batch` / `analyze` / `research` REFUSE to run with
**exit code 7** and a message pointing at the `/setup` flow.

The only bypass: `--backend whisper-local` or `--backend subtitles`
(offline; no API keys needed). Everything else hits the gate.

Auto-default config writes (e.g. fresh non-TTY first run) write
`onboarding_complete = false` so Claude Code can't silently auto-
proceed. The gate flips to `true` via either:

- `neurolearn config wizard` (TTY interactive flow — flips at the end)
- `neurolearn config complete-onboarding` (new explicit subcommand for
  Claude to call after a manual `/setup` walkthrough)

### Secure key handoff via `--from-file`

New flag on `neurolearn config set-key`:

```bash
neurolearn config set-key groq --from-file <PATH>
```

Reads the first non-empty line of `<PATH>` as the API key. The intended
Claude Code flow:

1. Claude tells the user: "Create a file at e.g. `~/Desktop/groq-key.txt`
   containing only your API key on one line. Tell me the path."
2. User creates the file manually (Finder / VS Code / terminal — their
   choice). The key never enters chat.
3. User replies with the path.
4. Claude runs `set-key groq --from-file <PATH>`. The CLI reads the
   key, saves to `~/.neurolearn/.env` (mode 0600), prints masked
   confirmation + "you can delete the temp file now".
5. User deletes the temp file.

The previously-shipped non-interactive forms (positional value,
`--from-env`, `--from-stdin`) still work for users running the CLI
directly. `--from-file` is the recommended path through Claude Code.

### Documentation rewrites

- **`commands/setup.md`** — entirely rewritten as a multi-step forced
  flow:
  1. Probe `doctor --json` for current state
  2. Ask working mode (Claude Code chat-native vs Standalone CLI)
  3. Ask free vs paid tier
  4. Audio backend choice (with recommendations)
  5. Vision backend choice
  6. Analyze backend choice (with `skip` option when Claude does analysis in chat)
  7. Tier configuration (paid users only)
  8. Key handoff via `--from-file` for each chosen cloud backend
  9. `config complete-onboarding` to flip the gate
  10. Verify via `doctor --json`

  Includes a verbatim security script telling the user how to create the
  key file without exposing the value in chat, and a recovery section
  for half-finished setups.

- **`SKILL.md`** — Onboarding section restructured around the new HARD
  RULE. Explicit forbidden patterns:
  - Don't auto-proceed past `onboarding_complete = false`
  - Don't accept keys pasted into chat — refuse and walk through `--from-file`
  - Don't invoke `config wizard` from chat (TTY-only)
  Plus an "ALREADY pasted a key by mistake" recovery path: tell the
  user to revoke the leaked key at the provider console immediately.

### Tests

1175 → 1184 (+9):

- `tests/test_onboarding_gate.py` (new, 9 cases):
  - `_require_onboarding_complete` unit tests (passes when complete,
    passes with allow_offline=True, raises SystemExit(7) with the
    right error message)
  - CLI smoke for offline-backend bypass + complete-state pass-through
  - `config complete-onboarding` command flips the flag
  - `set-key --from-file` happy path + missing-file + empty-file errors
- `tests/conftest.py` autouse fixture: patches the gate to no-op for
  the rest of the suite. 15 pre-existing transcribe/batch tests would
  otherwise all break since they don't run the wizard.

### Migration

For users with existing config.toml (v0.12.x or older):

- `onboarding_complete` defaults to `False` when missing from TOML.
- Next time they run transcribe → exit 7 → message points at `/setup`
  or `config wizard`.
- Quickest unblock: `neurolearn config complete-onboarding` (assumes the
  existing config is already what they want).
- Or: `neurolearn config wizard` (interactive re-walk-through).
- Or: continue with `--backend whisper-local` for individual runs that
  bypass the gate.

This is a **breaking change** for anyone scripting around `neurolearn`
on a missing/half-configured `~/.neurolearn/config.toml`. The gate
catches what was previously a silent "use whatever defaults exist"
behavior. Per-call `--backend whisper-local` is the recommended
unattended path until setup is explicitly completed.

## [0.12.2] — 2026-05-22

Plugin UX audit follow-up. After v0.12.0 (Anthropic removal + Groq vision)
and v0.12.1 (3-stage wizard + Claude Code extract-only mode), a fresh audit
found 15 documentation/UX gaps. v0.12.2 ships fixes for all of them so the
plugin "just works" end-to-end on a fresh `/plugin install` inside Claude
Desktop.

### Code (4 fixes)

- **Click `--analyze-backend` / `--translate-backend` / `--correct-asr-backend`
  choices**: swept from `[gemini, claude, openai, ollama]` to
  `[groq, gemini, openai, ollama]` everywhere (~12 sites). The CLI was
  accepting `claude` but `analyze/runner._KNOWN` rejected it at runtime —
  users would get `unknown backend claude` AFTER the batch downloaded.
  `_select_analyze_backends` default chain order updated. Internal
  `api_key_lookup` maps purged of `claude: anthropic` entries.
- **Wizard non-TTY guard**: `run_wizard()` now exits 2 with a friendly
  stderr message when invoked from a non-TTY context (Claude Code
  subprocess). Previously hung on `rich.Prompt.ask` EOF. Error message
  points at the non-interactive escape hatches (`config set-key`,
  `config set`).
- **`neurolearn config get <key> [--json]`** — new subcommand for
  inspecting a single config field. Claude needs this to verify state
  (e.g. "is `gemini_url_fastpath` actually on?") without parsing the
  prose `config show` output. Kebab-case keys mirror `config set`.
- **`doctor` recommends fixes for stale config**: when existing config
  pins `gemini_model = "gemini-2.5-flash"` (the +63% timestamp drift
  model), doctor now emits a `recommended_setup` entry with the
  one-line fix. Also nudges users with audio configured but no
  vision-capable key to enable `vision-backend = groq`.

### Documentation (10 fixes)

- **SKILL.md invocation form** (audit #1): added "How to invoke the
  CLI" section at the top telling Claude to prefix every command with
  `uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn …`. Previously
  SKILL.md examples used the bare `neurolearn` form — fresh
  `/plugin install` users hit `command not found` on the first
  transcription attempt.
- **SKILL.md quota awareness rewritten for v0.12** (audit #4, #13):
  the table assumed Gemini for everything (audio + vision +
  analyze). Replaced with a per-stage table showing Groq as primary
  with its real limits (8h audio/day, 1000 RPD vision, 14,400 RPD
  analyze) and Gemini as fallback with the much smaller free quotas.
- **SKILL.md backend cheat-sheet refreshed** (audit, #3): removed the
  v0.10.5-era "smart cascades subtitles → Gemini-URL → fallback"
  description. Updated to current v0.12.0 cascade
  (subtitles → groq → whisper-local).
- **SKILL.md visual moments section** (audit #5): documents the
  `keyframes/manifest.json` schema and step-by-step instructions for
  Claude to read each frame + transcript snippet and synthesize
  descriptions natively. Without this v0.12.1 feature is silently
  broken end-to-end — Claude doesn't know to read the manifest.
- **SKILL.md analyze backend reference** (audit #3): `--analyze-backend
  {gemini|claude|openai|ollama}` → `{groq|gemini|openai|ollama}` to
  match the v0.12.2 Click choices.
- **commands/transcribe.md**: new "Visual moments — extract-only mode"
  section mirroring the SKILL.md guidance, with the manifest schema
  inline.
- **commands/setup.md** (audit #7, #9): Step 2 now sets
  `backend smart` (not just `fallback groq`) — `fallback` only matters
  when `backend = smart`. Added Step 3 verification of `has_fast_vision`
  + `has_analyze_backend` (v0.12.1 doctor fields). New "Branch C —
  has_fast_audio but missing vision or analyze" arm iterates
  `recommended_setup[]` to upgrade users. New "Tier hint" section for
  paid users (gemini-tier / groq-tier / gemini-url-fastpath via
  `config set`). Warning that `config wizard` is TTY-only and Claude
  should never invoke it from chat.
- **README "Heads-up about smart" rewrite** (audit #10): replaced the
  contradicting v0.10.5-era "smart enables Gemini visual analysis by
  default" prose with current behavior — smart is audio-only since
  v0.10.6, vision is opt-in via `--with-visuals`, default vision
  backend is Groq Llama-4-Scout since v0.12.0.
- **README `--backend claude` example** (audit #3, #12): swapped to
  `--backend groq` with a v0.12 note.
- **docs/agent-reference.md sweep** (audit #11): removed every
  `--analyze-backend` / chain reference to `claude`; updated
  tutorial-preset description to drop the removed Claude refinement
  fallback; `--vision-backend {off, gemini}` → `{off, groq, gemini}`.
- **Plugin marketplace keywords** (audit #15): `"claude"` →
  `"claude-code"` in `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`. Old keyword set wrong expectations
  ("claude transcription" searcher landed on a plugin that doesn't
  call Anthropic API).

### Tests

1170 → 1175 (+5 net):
- test_wizard.py: helper monkey-patches `sys.stdin.isatty = True` to
  bypass the v0.12.2 guard; new `test_wizard_exits_when_not_tty` for
  the guard itself.
- test_batch_then_analyze.py: updated default chain assertion to
  `[groq, gemini, openai, ollama]`.
- test_config_cli.py: +4 `TestConfigGet` cases (known field, --json
  output, unknown field error, v0.12.1 fields reachable).

### Migration

No action needed for existing users. The `claude` → `groq` swap in
Click choices doesn't break runtime (the runtime never accepted
`claude`); it just stops misleading users via `--help`. The wizard
guard only fires when stdin is not a TTY — interactive users see no
difference. Stale `gemini_model = "gemini-2.5-flash"` now triggers a
proactive recommended_setup entry instead of silent timestamp-drift on
the next audio run.

## [0.12.1] — 2026-05-21

UX layer on top of v0.12.0 core. Two features that complete the Claude
Code plugin onboarding story: a tier-aware 3-stage setup wizard, and
auto-detection of plugin-mode runs to route vision through Claude's
chat-native vision instead of an external API.

### 3-stage setup wizard (C8)

The first-run wizard was a single audio-backend chooser. Now it walks
three stages with conditional branching:

```
Step 1: Audio backend (9 choices, recommends 'smart')
  Step 1b: Smart cascade fallback (only if audio=smart)
Step 2: Vision backend (groq / gemini / off — recommends groq)
Step 3: Analyze backend (groq / gemini / ollama / skip — recommends groq)
Step 4-5: Gemini tier + paid-model overrides (only if Gemini in any stage)
Step 6-7: Groq tier + paid-model overrides (only if Groq in any stage)
Step 8: API keys for chosen cloud backends not already configured
```

Tier-aware branching: free tier gets the constrained recommended flow,
no model-override prompts. Paid tier unlocks per-stage model overrides
(`gemini-3.5-pro` instead of `3.5-flash` for analyze, `llama-4-maverick`
for groq vision, etc.) plus the URL fast-path Y/N for paid Gemini.

New Config fields (all backward-compatible):
- `vision_backend: "off"` — picked by Step 2, persisted to config.toml
- `groq_tier: "free"` — wizard surfaces this to gate paid prompts
- `gemini_vision_model / gemini_analyze_model: ""` — paid overrides
- `groq_vision_model / groq_analyze_model: ""` — paid overrides

Bug fix in `load_config()`: returned `DEFAULT_CONFIG` by reference when
the config file was missing — the new wizard mutated it via
`cfg.default_backend = ...` and corrupted the singleton for the rest of
the process. Latent since Config became a mutable @dataclass. Fix:
`load_config()` now returns `dataclasses.replace(DEFAULT_CONFIG)`.

### Claude Code extract-only mode (C9)

When `$CLAUDE_PLUGIN_ROOT` is set in env (Claude Code plugin context)
AND vision is requested (`--with-visuals` or `--vision-backend X`),
neurolearn now defaults to extract-only mode:

1. Extracts keyframes via ffmpeg per detection window.
2. Writes `<batch>/keyframes/manifest.json` mapping windows → frames
   with the transcript snippet around each window.
3. Skips the vision-LLM API call entirely.

Claude in chat reads the manifest, opens each frame with its native
vision capability, and synthesises descriptions itself. No extra API
quota burn — the user already pays for their Claude subscription.

New CLI flag: `--claude-extract / --no-claude-extract` (Click
triple-state). Default is None ⇒ auto-detect from `$CLAUDE_PLUGIN_ROOT`.
Users can force on/off explicitly.

Manifest schema (`<batch>/keyframes/manifest.json`):

```json
{
  "video_id": "...",
  "mode": "claude_code_extract_only",
  "extracted_at": "2026-05-21T...Z",
  "windows": [
    {
      "start": 30.0, "end": 34.0,
      "transcript_window": "the host says ...",
      "trigger_reason": "trigger",
      "keyframes": ["frames/<id>_30.jpg", ...]
    },
    ...
  ]
}
```

### Minor

- `--with-visuals` shortcut now sets `vision_backend="groq"` (was
  `gemini`). Aligns with v0.12.0 default of Groq vision primary.
- `--vision-backend` choices: `off`, `groq`, `gemini`. The `claude`
  value (removed in v0.12.0) stays out — Claude integration is via
  chat extract-only mode, not via a backend choice.
- `needs_video` gate in transcribe/batch expanded to download mp4
  when `vision_backend in ('gemini', 'groq')`. Was gemini-only.

### Tests

1165 → 1170 (+5):
- `tests/test_wizard.py` fully rewritten (8 tests) for the 3-stage flow
- `tests/test_claude_extract_mode.py` (new, 5 tests): manifest schema,
  relative paths, ffmpeg-failure handling, env var visibility, CLI
  flags exist
- 2 existing tests updated to mock the new groq vision path

## [0.12.0] — 2026-05-21

Major release. Vision backend swap (Groq Llama-4-Scout as primary,
Gemini as fallback), full Anthropic API removal (Claude integration is
through Claude Code chat only — not via SDK), explicit Gemini cache
storage path removed (free tier doesn't allow it), per-model prompt
variants in the vision TOML, and several smart-cascade fixes.

### Why this is a major release

- **Dropped a base dependency** (`anthropic>=0.40.0`). Existing users
  who installed with `uv sync --extra ...` will get a smaller install.
- **Default `gemini_model` changed** from `gemini-2.5-flash` to
  `gemini-3.5-flash`. v0.11.0 didn't change this default — only the
  smart cascade routing. v0.12.0 makes the default safe everywhere
  (2.5-flash has the +63% timestamp drift bug confirmed in v0.11).
- **Vision pipeline behavior changed**: default vision backend on
  `--with-visuals` is now Groq Llama-4-Scout instead of Gemini. Users
  who relied on Gemini's vision-via-Files-API path explicitly must set
  `vision_backend = "gemini"` in their config.

### Vision pipeline overhaul (C1-C4)

- **New `GroqVisionBackend`** ([vision/groq_vision.py](skills/neurolearn/vision/groq_vision.py))
  using Llama-4-Scout via `chat.completions.create` with strict
  `response_format={"type":"json_schema","strict":true}`. 30 RPM /
  1000 RPD free tier (50x more than Gemini 2.5-flash). Per-call price
  ~5x cheaper than Gemini Flash even on paid tiers.
- **Per-model prompt variants** in `prompts_default.toml`: every
  builtin video type (`tutorial`, `lecture`, `code`, `demo`,
  `interview`, `vlog`, `review`, `talking_head`, `generic`) now has a
  sibling `[prompts.<type>.groq]` subsection tuned for Llama-4-Scout's
  literal instruction-following. Removed `GOOD: ... BAD: ...` canonical
  example strings — Scout copies them verbatim into output. Replaced
  with positive whitelists and schema-enforced 30-word brevity caps.
- **`load_prompt(model_family="groq")`** ([vision/prompts.py](skills/neurolearn/vision/prompts.py))
  extension picks the variant when present, falls back to the base
  prompt otherwise. Backward compatible — callers without `model_family`
  get v0.11 behavior.
- **Vision cascade** in [pipeline_v02.py](skills/neurolearn/pipeline_v02.py)
  dispatches `groq | gemini | openai` based on `cfg.vision_backend`.
  `claude` removed from the choices.

### Anthropic API removal (C5)

Per the durable rule `feedback_no_anthropic_api` in project memory:
neurolearn does NOT call `anthropic.Anthropic`. Claude integration
happens through Claude Code chat — the user's Pro/Max subscription —
not via SDK calls in our pipeline.

- Deleted `vision/claude_vision.py` (entire file, 167 LOC).
- Deleted `_refine_low_confidence_with_claude` helper in
  `pipeline_v02.py` (~75 LOC) and the `claude_fallback` preset
  option became a no-op (kept in registry.py for TOML backwards
  compat; ignored at runtime).
- `quality/asr_corrector.py` replaced `_call_claude` with `_call_groq`
  (Llama-3.3-70b-versatile, 14,400 RPD free tier).
- `analyze/runner.py` _KNOWN backends changed from
  `{gemini, claude, openai, ollama}` to `{groq, gemini, openai, ollama}`.
- `presets/registry.py`: `claude` removed from `vision_backend`,
  `correct_asr_backend`, `translate_backend` choice lists. Default
  `correct_asr_backend` switched from `gemini` to `groq`.
- `presets_default.toml`: tutorial preset's `vision_backend` switched
  from `gemini` to `groq`; `claude_fallback=true` removed.
- `pyproject.toml`: removed `anthropic>=0.40.0` from base dependencies.
- Removed `tests/test_vision_claude.py` + `tests/test_claude_fallback.py`.
  Replaced Claude test cases with Groq equivalents in
  `test_asr_corrector.py`, `test_translator.py`, `test_summarizer.py`,
  `test_analyze_runner.py`, `test_cli_correct_asr.py`,
  `test_presets_loader.py`.

### Explicit Gemini cached_content removal (C6)

Free-tier Gemini accounts return
`TotalCachedContentStorageTokensPerModelFreeTier limit=0` — the
v0.10.1 explicit-cache path always 4xx'd for >99% of users. Confirmed
empirically in `qa-out/v0.12.0-vision-compare/` Test 3.

- Removed `_maybe_create_cache()` async helper (~30 LOC).
- Per-window call shape simplified: every call now sends
  `[user_prompt, uploaded_video]` instead of branching on
  `cached_name`. Implicit caching deduplicates the repeated video
  reference server-side (free + automatic, no API call required).

For paid users that benefit from explicit caching (storage cost
$1/M-tok/hr but 90% discount on cached input tokens), a tier-aware
re-introduction is planned for a later release. Today's typical user
gets the implicit-cache benefit with zero configuration.

### Audio cascade fixes (C10+C11)

- **Restored Gemini URL middle-step** in smart cascade with strict
  guards: requires YouTube URL + `cfg.gemini_url_fastpath=True` (opt-in
  default off) + `cfg.gemini_model` in the
  `_GEMINI_AUDIO_URL_SAFE_MODELS` whitelist (currently
  `gemini-3.5-flash`, `gemini-3-flash-lite`, `gemini-3.1-flash-lite`).
  v0.11.0 removed this entirely after the +63% drift bug; v0.12.0
  reinstates it only for timestamp-safe models.
- **Default `gemini_model` changed** to `gemini-3.5-flash`. The
  2.5-flash default in `config.py` and `backends/gemini.py` was
  removed. When a user explicitly sets the model to `gemini-2.5-flash`
  for audio transcription, `backends/gemini.py` now prints a stderr
  warning about the timestamp drift bug with the fix command.
- **Vision use of 2.5-flash unaffected** — the bug is audio-only.

### Diagnostic command (C12)

`neurolearn doctor --json` now exposes per-stage backend readiness for
Claude Code plugin onboarding:

- New `ready.has_fast_vision` (boolean): True when Groq or Gemini key
  is configured.
- New `ready.has_analyze_backend` (boolean): True when Groq or Gemini
  key is configured.
- New `config.gemini_url_fastpath` (boolean): reflects the v0.12
  config field.

Claude reads these to branch onboarding flow ("do you want to enable
vision moments?" only if `has_fast_vision`).

### Deferred to v0.12.1

- **3-stage wizard** (audio + vision + analyze backend choice per stage,
  with tier branching + paid-tier model override prompts).
- **`$CLAUDE_PLUGIN_ROOT` auto-detection** → `--extract-only` mode where
  vision pipeline writes `keyframes/manifest.json` and lets Claude
  read the frames directly in chat (no extra API call).

These are nice-to-have UX layers on top of the v0.12.0 plumbing. The
core architecture (per-model prompts, Groq primary, Anthropic-free) is
shipping now.

### Tests

1137 → 1164 (+27 net):

- `+4` test_vision_prompts_loader.py (per-model variant resolution)
- `+5` test_vision_prompts_loader.py (parametrized × types invariants)
- `+8` test_groq_vision.py (new file)
- `+4` test_doctor_cli.py::TestDoctorV012Fields
- Removed `test_vision_claude.py` (8 tests) + `test_claude_fallback.py` (5 tests)
- Updated 7 existing test files for Anthropic / cache / model defaults

All 1164 tests green at release. No regressions vs v0.11.0.

### Migration

For users who set explicit Anthropic-based config in v0.11.x:

- `vision_backend = "claude"` → set to `"groq"` (recommended) or
  `"gemini"` (if you specifically wanted Gemini's vision-via-Files-API).
- `correct_asr_backend = "claude"` → set to `"groq"`.
- `claude_fallback = true` in tutorial preset → becomes no-op; remove or
  ignore.

Otherwise no action needed — `uv sync` will drop the `anthropic` package
on next sync and your runs continue working with Groq defaults.

## [0.11.0] — 2026-05-21

Major release. Audio default switched from Gemini-based smart-cascade to
Groq Whisper-large-v3-turbo. New Claude Code plugin onboarding flow so
the plugin works from a fresh `/plugin install` without leaving the chat.
Several speed wins on hot-path operations.

### Why this is a major (0.11.0) release, not a 0.10.x patch

The defaults changed. Users on smart-cascade who previously got Gemini's
YouTube-URL path (and lived with its quirks — see Bugs below) now get
Groq instead. That's a behavioral change visible in transcripts, in
generated `.srt` timestamps, in batch `combined.md`, and in API-call
billing patterns. The CLI surface remains backward compatible
(`--backend gemini` still works), but the *default* is different. Major
bump signals the change so anyone scripting against neurolearn knows to
look at their settings.

### Bug discovered during testing

Empirical comparison on a 17-minute YouTube test video on 2026-05-20:

| Backend | Wall-time | Reported duration | Last `.srt` timestamp | Real video duration | Drift |
|---|---|---|---|---|---|
| `gemini-2.5-flash` (pre-v0.11 default) | 50-100 s | **1045.2 s** ❌ | **17:25** ❌ | 10:40 (640 s) | **+63% stretch** |
| `gemini-3.5-flash` | 80 s | 639 s ✅ | 10:39 ✅ | 10:40 | <1 s |
| **Groq `whisper-large-v3-turbo`** | **12 s** ✅ | 640 s ✅ | **10:39** ✅ | 10:40 | <1 s |

The default backend was producing transcripts with timestamps that
*exceeded the real length of the video by 6+ minutes*. Anyone opening
the `.srt` in VLC and clicking on 17:00 landed in a black screen past
EOF. Anyone aligning keyframes by transcript timestamp got misaligned
keyframes. v0.11.0 removes Gemini from the smart cascade entirely; it
remains available via explicit `--backend gemini` for users who want
the Gemini URL path despite the bug.

### Claude Code plugin UX overhaul

Pre-v0.11 flow when a user installed the plugin in Claude Code:

1. `/plugin install neurolearn` — success.
2. User: "transcribe this URL."
3. Claude runs `neurolearn ...` — fails with `BackendNotConfigured`.
4. Claude tells user "open your terminal and run `neurolearn config set-key gemini`".
5. User: "but I'm in Claude Code, why do I have to leave?"
6. Even if user opens terminal, `set-key` was interactive (`click.prompt(hide_input=True)`).
7. **User abandons the plugin.**

v0.11.0 fixes all of this:

- **`neurolearn config set-key <backend> <VALUE>`** now accepts the key
  as a positional argument (also `--from-env VAR_NAME` and
  `--from-stdin`). Claude can call this directly when the user pastes a
  key in chat — no TTY required.
- **`neurolearn doctor`** is a new diagnostic command. `doctor --json`
  emits a structured payload with config state, key configuration per
  backend, platform info, and a `ready.recommended_setup[]` array
  carrying ready-to-relay `command` + `get_key_at` URL strings. Claude
  parses this to drive onboarding.
- **`/setup` slash command** is a new dedicated onboarding walkthrough.
  Five-step Groq key acquisition flow (open URL → sign in → create key
  → copy → paste in chat), Claude registers via `set-key`, verifies via
  `doctor --json`.
- **`commands/transcribe.md`** now has a Step 0 pre-flight check. Before
  any transcribe call, Claude runs `doctor --json`; if
  `ready.has_fast_audio == false`, it walks the user through Groq key
  setup before attempting transcription.
- **`SKILL.md`** has a top-of-document "Onboarding — first-time use"
  section that codifies the same flow for any Claude session with the
  plugin active.
- **First-run wizard** reordered to put `smart` first (with Groq pointer
  in the greeting panel) and `groq` second. `whisper-local` moved to 3rd.
  Smart-mode fallback prompt also reordered: 1=groq, 2=whisper-local,
  3=gemini (was: 1=whisper-local, 2=gemini, 3=groq).

### Audio cascade rewrite

- **Default `default_backend`**: `whisper-local` → `smart`
- **Default `fallback_backend`**: `whisper-local` → `groq`
- **Removed**: the v0.10.5 Gemini direct-URL middle step. Smart cascade
  is now strictly `subtitles → fallback_backend → whisper-local`. The
  middle step was the source of the timestamp-drift bug; users who want
  the URL path opt in via `--backend gemini`.
- **Added**: when the configured fallback backend isn't actually
  configured (e.g. fresh install with no Groq key), the smart cascade
  silently auto-drops to whisper-local instead of hard-erroring. A
  fresh install with no keys still produces a transcript.

### Speed wins on the hot path

- **`m4a` audio passthrough** ([utils/downloader.py:55-77](skills/neurolearn/utils/downloader.py#L55)):
  yt-dlp's `--audio-format` default changed from `mp3` to `m4a`. YouTube
  serves AAC in m4a natively; mp3 forced a 2-5s ffmpeg re-encode per
  video that no backend needed.
- **Gemini vision concurrency** ([vision/gemini.py:77-89](skills/neurolearn/vision/gemini.py#L77)):
  `_TIER_CONCURRENCY["free"]` and `GeminiVisionBackend.max_concurrent`
  default bumped from 3 to 6. Google raised gemini-2.5-flash free-tier
  RPM from 5 to 10 in 2026-Q1; we were under-utilizing. Saves ~8-12s on
  a 20-window video. (Vision is opt-in; remains off in the default
  smart preset.)

### Migration guide

For users who explicitly want pre-v0.11 behavior:

- `neurolearn config set fallback gemini` (forces gemini as the audio
  fallback in smart cascade). **Note**: gemini-2.5-flash still has the
  timestamp drift bug. Consider `--gemini-model gemini-3.5-flash` for
  timestamp-accurate Gemini transcription, at the cost of ~3-7× slower
  vs Groq.
- `--backend gemini` per-call still works without changing config.

For new users: no migration needed. Smart cascade with auto-fallback
will produce a transcript even before they configure Groq. After
configuring Groq, audio transcription is ~5-10× faster than v0.10.x.

### Deferred to v0.12.0

The following items from the original v0.11.0 plan were scoped out to
keep this release focused and shippable:

- **GroqVisionBackend** (Llama-4-Scout primary vision, ~1.2s/img free
  tier — the natural complement to Groq audio).
- **yt-dlp Python API migration** (currently 3 subprocess invocations
  per video — Python startup tax especially heavy on Windows).
- **Parallel audio + mp4 download** via asyncio when `--with-visuals` is
  on (would save 15-25 s on premium preset).
- **PySceneDetect + frame-diff shared decode** (currently two ffmpeg
  full-passes over the same video).
- **Semaphore-based parallelism** for `ClaudeVisionBackend` and
  `OpenAIVisionBackend` (only GeminiVisionBackend has it today).

v0.12.0 will cover these.

### Tests

1138 → 1137 (net -1 after removing 4 obsolete tests for the v0.10.5
Gemini middle step and adding 3 new tests for v0.11.0 cascade behavior
plus 19 new tests for the onboarding surfaces):

- `tests/test_config_cli.py` (+6) — non-interactive `set-key`
- `tests/test_doctor_cli.py` (+13, new file) — `doctor` command + JSON
- `tests/test_factory.py` (-4, +3) — removed Gemini middle-step tests,
  added auto-fallback + cascade reordering tests
- `tests/test_config.py` (modified) — new default expectations
- `tests/test_wizard.py` (modified) — menu reorder
- `tests/test_wizard_non_tty.py` (modified) — new default
- `tests/test_downloader.py` (modified) — m4a assertion
- `tests/test_gemini_caching_concurrency.py` (modified) — free=6
- `tests/test_v0101_e2e.py` (modified) — max_concurrent=6

## [0.10.9] — 2026-05-20

### Robustness fixes from Windows 11 / PowerShell 5.1 field testing

A run of v0.10.7 on a fresh Windows machine surfaced six rough edges
in non-TTY, GPU-dependency, and crash-recovery paths. v0.10.9 fixes
all of them without breaking changes — every fix is additive (hidden
flag, fallback path, or post-crash finalize).

**Fix F + G — `batch` accepts `--no-analyze` / `--yes` as no-ops.**
The `research` command supports both flags; the `batch` command did
not. Routing-Claude (or a power user copying examples) would often
add them to a `batch` invocation by symmetry and hit
`Error: No such option`. Now both flags are accepted on `batch` as
hidden no-ops — they don't appear in `--help` (since `batch` has no
TTY checkpoint and no `--then-analyze` by default) but they don't
error either.

**Fix H — wizard no longer blocks non-TTY runs.** First run with no
`~/.neurolearn/config.toml` would call `run_wizard()` unconditionally,
which `sys.exit(1)`s under a piped / scripted stdin. Now: if stdin is
non-TTY, the wizard is skipped, a default `Config()` is written to
disk silently, and a one-line `[neurolearn] First run, non-TTY
context...` notice goes to stderr. `config show` additionally marks
`file_status` as `(NOT PRESENT — showing defaults)` if the file is
absent — previously the path was printed regardless, leading users
to believe a missing file existed.

**Fix I — cuBLAS / cuDNN missing falls back to CPU.** On Windows with
NVIDIA drivers installed but CUDA Toolkit absent, faster-whisper
crashes at model-load time with `Could not load library cublas64_*`.
`_load_faster_whisper_model` now catches `RuntimeError` / `OSError`
with cuBLAS/cuDNN/library markers and retries on
`device="cpu", compute_type="int8"`, with a stderr warning. Unrelated
errors are re-raised unchanged. Users without CUDA Toolkit no longer
need to know about CTranslate2's separate dependency on cuBLAS.

**Fix J — `compute_type="auto"` respects user device override.** When
the user sets `whisper_compute_type = "auto"` and overrides
`whisper_device` (e.g. `cuda` on a CPU-default machine, or `cpu` on a
GPU machine), `factory.py` previously used
`info.recommended_compute_type` directly — which corresponds to the
**detected** device, not the **overridden** device. Now the factory
re-derives the compute type when the resolved device differs from
the auto-detected one (`int8` for cpu, `float16` for cuda).

**Fix K — `combined.md` / `manifest.json` / `errors_log.md` written
even on crash.** The processing loop in `_run_batch_pipeline` would
raise straight out without writing the post-batch artifacts. A long
run that crashed at item 95 of 100 would lose all 94 successful
transcripts from the combined view. Now the loop is wrapped in
`try / except Exception / except KeyboardInterrupt`, the crash is
captured into `failures` as a `(batch)` row, the
`write_combined_md` / `meta.write_manifest` / `errors_log` writes
happen unconditionally, and the original exception is re-raised
afterward so exit codes are unchanged.

### Tests

+17 net (1102 → 1119, plus 1 flaky test fixed):

- `tests/test_batch_cli_compat_flags.py` (4) — `batch` accepts
  `--no-analyze` and `--yes` without errors, neither appears in
  `--help`.
- `tests/test_wizard_non_tty.py` (5) — `_ensure_config_or_skip_wizard`
  helper behavior in TTY + non-TTY contexts; `config show` file-status
  marker.
- `tests/test_whisper_local.py` (+2) — cuBLAS fallback fires for
  CUDA-dependency markers; unrelated errors are not masked.
- `tests/test_factory.py` (+2) — compute_type re-derive when user
  overrides device.
- `tests/test_batch_finalize_on_crash.py` (4) — crash mid-loop still
  writes manifest, combined, and errors_log; `KeyboardInterrupt` path
  preserves the same finalize behavior; original exception is
  re-raised.
- `tests/test_cli_visual_wiring.py` — pre-existing flaky test fixed
  by mocking `skills.neurolearn.transcribe.resolve` so it stops
  hitting real YouTube and getting 429s on slow runners.

### Files touched

- `skills/neurolearn/transcribe.py` — hidden batch flags;
  `_ensure_config_or_skip_wizard` helper (replaces two
  `if not CONFIG_PATH.exists(): run_wizard()` sites); `config show`
  file_status marker; `_run_batch_pipeline` crash-finalize wrapper.
- `skills/neurolearn/backends/whisper_local.py` — cuBLAS / cuDNN
  fallback in `_load_faster_whisper_model`.
- `skills/neurolearn/backends/factory.py` — re-derive compute_type
  when device override differs from auto-detected device.

## [0.10.8] — 2026-05-20

### Epistemic framing for downstream LLM consumption

When the user runs `research`, `batch`, or `transcribe --then-analyze`
and then asks the assistant (Claude or any other LLM) to read the
result, the downstream LLM used to treat speaker claims as ground
truth. "The YouTube video said do X" → "you should do X". For
research-mode usage especially, that's wrong: the user runs research
to **build a knowledge base for their own judgement**, not to
delegate the decision to whoever happened to upload a video.

v0.10.8 wires explicit epistemic framing through every surface where
transcript content meets an LLM:

**1. `combined.md` banner.** A "Read this first — agent reading
combined.md" block is now prepended between the YAML frontmatter and
the body. Tells the reading agent to:

- synthesize across sources rather than repeating one,
- frame recommendations as candidate inputs, not instructions,
- weigh against the user's actual context (a 2024 tip may be stale),
- match the source's confidence level (if they hedge, you hedge),
- mark single-source claims explicitly.

**2. `manifest.json.epistemic_status` field.** Machine-readable
counterpart for tools that consume the manifest. Always set to
`"community_content_unverified"`.

**3. `analyze` prompt.** `SYSTEM_PROMPT` in
`skills/neurolearn/analyze/prompt_builder.py` now prepends a shared
`EPISTEMIC_PROMPT_PREFIX`. Every `analyze` call carries the framing
into the LLM context.

**4. `report` outliner prompt.** `_build_full_prompt` in
`skills/neurolearn/report/outliner.py` prepends the same prefix.
Single-call and hierarchical paths both get it.

**5. `summarize` prompt.** `_SUMMARY_PROMPT` in
`skills/neurolearn/quality/summarizer.py` prepends the prefix.

**6. `SKILL.md` guideline.** New "Consuming neurolearn output —
epistemic stance" section. Tells any Claude session that has the
plugin active how to handle transcript-derived content when the
user later asks for synthesis / recommendation / summary.

**7. `commands/transcribe.md` epistemic-stance section.** Slash-
command hint reinforces the stance for the routing-Claude that
invokes `neurolearn` on the user's behalf.

**8. Post-batch CLI hint update.** The final `Next: ask Claude →`
line now nudges toward synthesis and skepticism rather than
"summarize what the videos said".

### Scope — applied to LLM-consumed surfaces only

The framing reaches:

- `combined.md` (always written by `batch` / `research`).
- `manifest.json` (machine-readable signal).
- `analyze` / `report` / `summarize` LLM prompts.
- `SKILL.md` + slash command (guides the consuming Claude).

The framing does NOT reach:

- Single-file `.txt` / `.srt` from plain `neurolearn transcribe
  <URL>` — those are for the user's own reading; injecting a banner
  there would clutter the file.
- `.json` segment dumps — pure data passthrough.

Per the user's explicit guidance: "if we're just transcribing for
the user to read, framing is irrelevant; if downstream LLM analysis
happens, framing is essential."

### Tests

+9 new tests in `tests/test_epistemic_framing.py`:

- Banner text says "third-party", "synthesize", "candidate inputs",
  "hedge"/"confidence" (positive content check).
- Banner sits between YAML frontmatter and body header in
  `combined.md`.
- `manifest.json.epistemic_status == "community_content_unverified"`.
- `analyze` prompt contains "third-party" after building.
- `report` outliner `_build_full_prompt` contains "third-party".
- `summarize` `_SUMMARY_PROMPT` template contains "third-party".
- Negative: plain `.txt` writer does NOT contain banner text — only
  raw transcript content. Verifies the scope boundary.

Full suite: 1102 passed, 3 skipped (was 1093 in v0.10.7.1).

### Did not change

- Transcription itself, backend selection, smart cascade — all unchanged.
- The actual transcript bodies are untouched. We only wrap them.
- Per-video file naming, output_dir layout — unchanged.

## [0.10.7] — 2026-05-20

Bug-fix release driven by a Windows 11 / PowerShell 5.1 debug-run
report of `neurolearn research`. Five findings; the worst was a
cosmetic-but-catastrophic Unicode crash on the cp1251 console that
ate the visible result AFTER all transcripts had already been
written to disk. All five addressed.

### Fixed

**A. (critical) `UnicodeEncodeError` in Rich console output on
non-UTF-8 Windows code pages.**

When the active code page wasn't UTF-8 (cp1251 on ru-RU locales is
the canonical case), Python's stdout defaulted to that codepage.
Rich's `Console()` picked the `LegacyWindowsTerm` path and routed
writes through `cp1251.encode()`, which crashed on every Unicode
glyph the CLI printed — `✓`, `✗`, `·`, `→`, box-drawing characters.
The crash happened **after** the actual work had completed and the
transcripts were on disk, so the user saw a traceback and assumed
the tool had failed.

v0.10.7 adds `skills/neurolearn/utils/console.py::make_console()` —
a cross-platform Console factory. On Windows it both reconfigures
`sys.stdout` / `sys.stderr` to UTF-8 with `errors="replace"` and
passes `legacy_windows=False` so Rich emits ANSI escapes instead of
going through `LegacyWindowsTerm`. ANSI is supported by conhost
since Win10 1607 and natively by Windows Terminal.

All ten `Console()` instantiations across the project
(`transcribe.py`, `wizard.py`, `research/pipeline.py`,
`analyze/backend_resolver.py`, `history/cli.py`,
`subscribes/cli.py`, `subscribes/instagram_loader.py`,
`subscribes/cookies_onboarding.py`, `subscribes/pipeline.py`,
`detection/triggers_cli.py`) were converted to `make_console()`.

**B. (major) Post-batch "consider --backend smart" hint when most
of an explicit-backend batch fails.**

A user with `fallback_backend = whisper-local` in `config.toml` ran
`neurolearn research ... --backend subtitles` against 15 YouTube
videos. All 15 failed with `IpBlocked`. The configured fallback
never fired — because explicit `--backend` skips the smart cascade
and there was no per-batch retry logic. The user got an empty
`combined.md` with no hint about what to do.

`_smart_fallback_hint()` (extracted to be unit-testable) now
inspects the batch result. When the batch had ≥2 attempts, the
backend wasn't already `smart`, and failure rate ≥50%, the CLI
prints a yellow warning suggesting `--backend smart`. Skipped for
tiny batches (<2 items — no statistical signal) and for users who
already used smart.

Per-video auto-retry (the heavier "B-full" variant) was deferred —
the minimal hint is enough UX and adds no risk.

**C. (minor + actual fix) `subscribes cookies` extended for
YouTube + new `list` alias.**

`neurolearn subscribes cookies list` didn't exist (the reporter
hit `No such command 'list'`). `set` / `clear` only accepted
`instagram` / `tiktok` — but YouTube ALSO gets IpBlocked
anonymously after ~10 requests, so YouTube cookies are equally
useful.

v0.10.7:

- Adds `youtube` to the `Choice` set in `cookies set` / `cookies
  clear`.
- Adds `cookies list` as an alias for `cookies show`.
- Adds `Config.youtube_cookies_file` (mirrors `instagram_cookies_file`
  / `tiktok_cookies_file`), serialised under `[youtube]` in
  `config.toml`.
- Threads the YouTube cookies file into `SubtitlesBackend` — when
  configured, the backend builds a `requests.Session` from the
  Netscape `cookies.txt` and hands it to
  `YouTubeTranscriptApi(http_client=session)`. The authenticated
  session bypasses anonymous IP rate-limits.

**D. (observation, addressed) Research provenance in
`manifest.json`.**

YouTube's `ytsearch:` ranking is non-deterministic — two
back-to-back runs of the same command returned 12 videos then 15.
v0.10.7 records every search parameter in
`manifest.json.research`: query, per-language translated queries,
`languages` list, source-lang hint, limit, days/since/until window,
match/filter strings, in_subscribes flag, group filter, the exact
UTC timestamp of the search, and how many candidates survived
pre-checkpoint filtering. Lets a debugger answer "why these videos"
even days later. Absent for non-research batches.

**E. (low) `hint` field in error reports now populated for the
common Windows + research failure modes.**

`_diagnose_failure_hint()` was returning `null` for the exact
errors the reporter hit. v0.10.7 adds branches for:

- `IpBlocked` (from `SubtitlesBackend`) → suggests YouTube
  cookies *and* `--backend smart`.
- `subtitles unavailable` (no IpBlocked) → suggests `--backend
  smart` for auto-fallback to local transcription.
- `429 RESOURCE_EXHAUSTED` (Gemini free-tier quota) → suggests
  `--backend smart` for auto-fallback or waiting for the daily
  reset.

The hint flows into `manifest.json[].hint` and `errors.log` so the
user sees an actionable next step instead of a cryptic null.

### Tests

+21 new tests across `test_utils_console.py`,
`test_smart_fallback_hint.py`, `test_diagnose_failure_hint.py`,
`test_cli_subscribes.py` (cookies list/set/clear/reject),
`test_subscribes_cookies_onboarding.py` (youtube platform),
`test_research_manifest_provenance.py`.

Full suite: 1092 passed, 3 skipped, 1 pre-existing failure
(`test_bootstrap_first_run_initializes_state` — fragile time-zoned
fixture, unrelated to v0.10.7, not introduced here).

### Did not change

- `--backend smart` semantics (still subtitles → Gemini URL → local
  fallback; cookies are passive infrastructure).
- `youtube-transcript-api` library version or call shape (just the
  optional `http_client=` Session passthrough).
- Default vision-off behavior shipped in v0.10.6 — unchanged.

## [0.10.6] — 2026-05-19

Bug-fix release driven by a debug-run report from a fresh-machine
install. Three real findings addressed; the documented "1 Gemini call
per transcribe" claim is now actually true.

### Fixed

**1. `smart` preset no longer silently triggers visual analysis.**

Pre-v0.10.6 the built-in `smart` preset shipped with
`vision_backend = "gemini"` and `max_windows_per_video = 20`, so every
`transcribe <URL>` invocation that didn't pass an explicit `--preset`
ran the vision pipeline — 1+N Gemini calls per video, where N ≈
keyframe windows (≈4-6 per minute). On the Gemini free tier (20
calls/day) this exhausted the daily quota after one 8-minute video,
contradicting the documented "1 call per transcribe" claim in
SKILL.md.

v0.10.6 sets `smart.vision_backend = "off"` and
`smart.max_windows_per_video = 0`. Default behavior is now exactly:
subtitles fast-path → Gemini direct URL → download+fallback, with
**zero** vision calls. Vision is opt-in via either:

- `--with-visuals` flag (CLI override), or
- explicit `--preset standard / premium / tutorial` (these presets
  retain `vision_backend = "gemini"` by design — they exist
  specifically for vision-enabled workflows).

This is technically a behavior change for users who relied on the
silent vision default, but the previous behavior was undocumented and
quota-destructive on free tier. The migration is one CLI flag.

**2. ffmpeg keyframe extraction sets `-pix_fmt yuvj420p`.**

`vision/frames.py` invoked ffmpeg without an explicit pixel format.
ffmpeg 8.x's mjpeg encoder rejects non-full-range YUV with
`Non full-range YUV is non-standard, set strict_std_compliance to at
most unofficial to use it` and silently drops the frame. Reproduced
on the debug run: 2 of 16 vision-window keyframes failed encoding
without affecting exit code, but the vision pipeline lost those
moments.

Both `extract_keyframes()` and `extract_keyframes_asymmetric()` now
pass `-pix_fmt yuvj420p` (the J variant signals full-range YUV, which
mjpeg accepts on any source).

**3. Slash-command CLI invocation is zero-config.**

`commands/transcribe.md` used to say "Run `neurolearn $ARGUMENTS`",
which assumes a global `neurolearn` binary on PATH. After
`/plugin install neurolearn@neurolearn`, that binary doesn't exist —
Claude Code copies the plugin dir but doesn't run `install.sh`, so
the user has to `uv tool install` manually before any `/transcribe`
invocation works. The debug-run host hit exactly this:
`which neurolearn` → not found.

The slash-command body now uses
`uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn $ARGUMENTS`
when `${CLAUDE_PLUGIN_ROOT}` is set (Claude Code exposes it as a
documented per-plugin env var per
<https://code.claude.com/docs/en/plugins-reference>). The plugin
ships its own venv via `uv run --project`, so this form works
immediately after `/plugin install` with no user setup.

The plain `neurolearn $ARGUMENTS` form remains as a fallback for
users who have a global install. An explicit recovery hint covers
the `command not found` case (suggesting `uv tool install --from
"${CLAUDE_PLUGIN_ROOT}" neurolearn`).

### Docs

- `SKILL.md` "Quota awareness" table updated. Default
  `transcribe <URL>` is now correctly listed as **1** call instead
  of the misleading old number that didn't account for the silent
  vision-on default.
- `SKILL.md` backend cheat-sheet row for "Need keyframes" now points
  to `--with-visuals` *or* a richer preset (was previously implying
  vision was on by default).
- `docs/agent-reference.md` preset table expanded to spell out the
  vision-on-vs-off status of each preset and the v0.10.6 change.

### Tests

+5 new tests on the three fixes:

- `test_load_smart_preset_defaults` updated to assert
  `vision_backend == "off"` and `max_windows_per_video == 0`.
- `test_standard_preset_still_has_vision_on` — sanity-check that the
  v0.10.6 flip didn't accidentally affect the richer presets.
- `test_smart_preset_unaffected_no_key_no_fallback` — vision-off
  smart preset doesn't trigger the "Gemini key missing" silent
  fallback (since vision wasn't requested in the first place).
- `test_extract_keyframes_sets_pix_fmt_for_mjpeg` — proves the
  `-pix_fmt yuvj420p` flag is present in the ffmpeg command.
- `test_extract_keyframes_asymmetric_sets_pix_fmt` — same for the
  asymmetric (tutorial) path.

`test_presets_silent_fallback` rewritten to exercise the `standard`
preset since `smart` no longer has a vision_backend to fall back
from.

Full suite: 1067 passed, 3 skipped (was 1063 in v0.10.5).

### Did not change

- `--backend smart` (the transcription-backend cascade flag) behaves
  identically. The vision toggle is purely on the preset side.
- IG / TikTok / non-YouTube URL paths unchanged.
- `commands/transcribe.md` routing logic, recovery hints, and the
  rest of the body are unchanged — only the CLI-invocation form at
  the top was added.

### Not addressed in this release

- Legacy `youtube-transcribe triggers add` text in some users'
  `~/.neurolearn/triggers.toml` (Finding 4 from the debug run). That
  string lives in user-local files generated by an older CLI, not in
  the repo. Will fix itself when the user regenerates the file via
  `neurolearn config wizard`; an explicit `config migrate` subcommand
  can be added if it becomes a recurring pain.

## [0.10.5] — 2026-05-19

### `smart` preset now uses Gemini's direct YouTube URL path automatically

Previously the Gemini direct-URL fast path (no download, no upload —
shipped in v0.10.3) only activated when the user explicitly set
`fallback_backend = "gemini"` in their config. Default installs with
`fallback_backend = "whisper-local"` meant `--backend smart` always
downloaded audio after subtitles failed, even when a Gemini key was
configured.

v0.10.5 moves the Gemini-URL fast path into an unconditional middle
step between subtitles and the configured `fallback_backend`. The new
cascade is:

1. **Subtitles fast-path** (1–2 s, free) — unchanged.
2. **Gemini direct URL** (new middle step, 30–90 s, no download) —
   fires when the URL is YouTube AND a Gemini key is configured.
3. **Download + `fallback_backend`** — unchanged final fallback.

For typical users (default config, Gemini key set), `transcribe
<YouTube URL> --backend smart` now skips the audio download entirely
when subtitles aren't available — saving 10–60 s of yt-dlp work and
1–5 s/MB of upload bandwidth per video.

On Gemini failure (429 quota, private video, network), step 3 still
runs so the user always gets a transcript. No new flags; behavior is
opt-in via "have a Gemini key configured."

The now-redundant `fb_name == "gemini" and is_youtube_url(src)` branch
in the fallback section was removed — the middle step covers it
unconditionally.

### Docs: backend cheat-sheet + quota awareness in `SKILL.md`

`SKILL.md` (auto-loaded into every Claude session that has the plugin
active) now opens with:

- **Backend choice cheat-sheet** — explicit decision tree mapping user
  intent (`fast transcript` / `offline` / `paid Gemini` / `free Gemini`
  / `need keyframes`) to the recommended flags, with the reasoning.
- **Quota awareness** — per-feature Gemini call counts (`--with-visuals`
  burns 1 + N calls per video, where N is keyframe windows), what
  happens on `429 RESOURCE_EXHAUSTED` for each backend choice, and
  the daily reset window.
- **Pointer to `docs/agent-reference.md`** so LLM-driven users on a
  fresh machine know where the deep reference lives.

`commands/transcribe.md` (auto-loaded when `/transcribe` is invoked) now
includes error-recovery hints for the three most common failures:
quota exhausted, missing API key, private-video-via-Gemini.

### Tests

+3 new tests on the smart middle step:

- `test_smart_tries_gemini_url_after_subtitles_when_key_available` —
  proves the new path; download skipped.
- `test_smart_gemini_url_failure_falls_through_to_download` — proves
  graceful fallback on 429 / private / network.
- `test_smart_skips_gemini_url_when_no_key` — proves no spurious
  Gemini call when key is absent.

Existing v0.10.3 / v0.10.4 tests updated to mock `get_api_key`
explicitly so they exercise the intended code paths regardless of the
test environment's actual API keys.

Full suite: 1063 passed, 3 skipped (was 1060 in v0.10.4.1).

### Removed

- `factory.run_smart`'s `fb_name == "gemini" and is_youtube_url(src)`
  branch in the fallback section. The new unconditional middle step
  covers it identically; keeping both was a duplicate that triggered
  Gemini without checking for the key.

## [0.10.4] — 2026-05-18

### Four targeted speedups (Tier 1 of the performance survey)

A codebase-wide hot-spot survey identified four independent places
where wall-clock time was being burned on serial work that could
trivially run in parallel or be cached. All four shipped together;
each is risk-isolated to its own subsystem.

**1. Whisper-local model cache between batch items.**
[backends/whisper_local.py:30](skills/neurolearn/backends/whisper_local.py#L30)
`_load_faster_whisper_model` is now wrapped in `functools.lru_cache(maxsize=4)`,
keyed on `(name, device, compute_type)`. Previously a `batch` run
with 10 videos against `--backend whisper-local` reloaded the
WhisperModel from disk + reinitialised the GPU 10 times — 20-50 s of
pure model-load overhead. Now the model loads once on first use and
all subsequent videos in the batch reuse it.

**2. Research multi-language translation runs concurrently.**
[research/translator.py::build_queries_per_language](skills/neurolearn/research/translator.py)
`neurolearn research --languages ru,en,ja` previously translated the
query to each non-anchor language sequentially — 3 LLM calls × ~2 s =
6 s of latency before any YouTube search started. Now the translations
fan out across a `ThreadPoolExecutor(max_workers=4)`, so total wall
time is one LLM round-trip regardless of N (within the 4-worker cap).
Anchor language detection and the output dict's user-requested order
are preserved.

**3. Report hierarchical outliner runs chunks in parallel.**
[report/outliner.py::_build_outline_hierarchical](skills/neurolearn/report/outliner.py)
For videos that cross the 15 k-token threshold and trigger the
hierarchical path, per-chunk LLM calls used to run one at a time.
A 1-hour video that splits into 6 chunks at ~2.5 s/call meant 14-21 s
of sequential outline work. Now chunk calls fan out (cap 4 workers)
and rejoin with stable ordering by chunk index. Final assembly call
stays sequential (depends on all partials).

**4. Resolver probes URLs in parallel.**
[utils/resolver.py::resolve](skills/neurolearn/utils/resolver.py)
`neurolearn batch <url1> <url2> ... <urlN>` previously called
`probe_input(url)` serially — each yt-dlp metadata fetch takes 1-2 s,
so a 10-URL batch burned 10-20 s before download could start. Probes
now run in a `ThreadPoolExecutor(max_workers=4)`. Downstream
processing (dedup via `seen_video_ids`, playlist expansion) stays
single-threaded so result order is bit-identical to the serial version
and the dedup set needs no lock.

### Tests

+5 new tests assert real parallelism, not just functional equivalence:

- `test_faster_model_load_cached_between_transcribe_calls` —
  WhisperModel constructor called once for two transcribe calls
  with the same key tuple.
- `test_faster_model_cache_separate_for_different_params` —
  different (device, compute_type) → separate cache entries.
- `test_build_queries_parallelizes_translations` — concurrency
  counter proves ≥2 LLM calls in flight simultaneously; wall time
  bounded.
- `test_long_video_chunks_run_in_parallel` — same concurrency
  proof for the outliner.
- `test_resolve_probes_multiple_urls_in_parallel` — same for probes.

Full suite: 1060 passed, 3 skipped (was 1055 in v0.10.3).

### Trade-offs

- Each parallelization path is capped at 4 concurrent workers to
  avoid bursting free-tier rate limits on Gemini/OpenAI. Paid-tier
  users hitting 5-6 RPS are unaffected; users on free-tier may
  occasionally see one in-flight 429 surface as a fallback to
  the sequential path (errors do not cascade — each worker handles
  its own request).
- Whisper cache holds models in process memory. For long-running
  daemons this is fine (cap maxsize=4); for one-shot CLI invocations
  the cache is GC'd at exit.

### Did not change

The Tier 2 / Tier 3 items from the same survey are not in this
release: yt-dlp `extract_flat` caching, stream-while-download for
Groq/Deepgram, batch download↔transcribe decoupling, ASR-correction
batching. They were judged either too narrow (single-flow benefit)
or too risky for the wall-time win.

## [0.10.3] — 2026-05-18

### Gemini accepts YouTube URLs directly (no download)

Before this release, `neurolearn transcribe <YouTube URL> --backend
gemini` was a three-stage pipeline: yt-dlp downloads audio, we upload
that audio to the Gemini Files API, then we ask the model to
transcribe. That meant ~10-60 s of yt-dlp time, ~1-5 s/MB of upload
time, and 50-200 MB of temp disk usage per video.

Gemini's video-understanding endpoint accepts a YouTube URL via
`Part.from_uri` and fetches the video server-side. v0.10.3 routes
YouTube URLs through that path:

- `backends/gemini.py::GeminiBackend.transcribe(url)` detects YouTube
  URLs and uses `types.Part.from_uri(file_uri=url, mime_type="video/*")`
  with `models.generate_content`. Local file inputs still use the
  upload path unchanged.
- `supports_url` flipped to `True` for Gemini.
- Non-YouTube URLs (Instagram / TikTok / Vimeo / arbitrary `https://`)
  fail fast with an explicit "Gemini only accepts YouTube URLs
  directly; download audio first" message — the smart composer (or
  the user) handles the download.
- `backends/factory.py::run_smart` fast-paths YouTube URLs to
  Gemini when fallback is Gemini, skipping `download_audio`. On any
  `BackendError` from the URL path (429 daily-quota, private video,
  network), it falls back to the download+upload pipeline so the
  user still gets a transcript.

### Robust JSON response parsing

Gemini occasionally appends a second JSON object or a few lines of
commentary after the main response (observed in production on the
real YouTube URL path). The old parser blew up with `json.JSONDecodeError:
Extra data`. `_extract_json` now uses `JSONDecoder().raw_decode()`,
which parses up to the end of the first valid object and ignores
trailing data. Also tolerates a leading "Here is the JSON:" preamble.

### Trade-offs (read before relying on this)

- **Free tier daily cap**: 8 hours of YouTube video per day. After
  that Gemini returns 429 and the smart composer falls back to the
  download path automatically.
- **Public videos only**: private and unlisted YouTube videos can't
  be fetched via `file_uri`. The smart composer falls back to
  download (which uses cookies-file if configured for private content).
- **Preview status**: Google labels the YouTube-URL ingestion as
  preview. Pricing and limits may change.
- **Other backends unchanged**: groq / deepgram / assemblyai accept
  direct media URLs (`.mp3`, `.wav`) but NOT YouTube URLs, because
  YouTube URLs are HTML pages. Those backends still go through the
  download+upload pipeline.

### Tests

+9 tests across `tests/test_backend_gemini.py` and
`tests/test_factory.py`. Full suite: 1052 passed, 3 skipped.

## [0.10.2] — 2026-05-16

### PDF report generation

New `neurolearn report <batch_dir>` subcommand. Takes an already-
transcribed batch (manifest.json + SRT + keyframes) and produces a
structured PDF report with title, executive summary, sectioned
table of contents, per-section key points, embedded keyframes, and
inline timestamps.

**How it works:**

1. **Outliner** asks an LLM (gemini / claude / openai / ollama) to
   structure the transcript + visual segments into a JSON outline
   matching the report's prompt template.
2. **Renderer** flows the outline through a Jinja2 HTML template
   (`report/data/templates/base.html` + `base.css`), downscales any
   referenced keyframes to ≤1000px via Pillow, embeds them as base64
   data URIs, and pipes everything through WeasyPrint to produce a
   self-contained, A4-paginated PDF.

**Prompt templates** (parallel to v0.10.1 vision prompts):
- Built-in: `tutorial`, `vlog`, `generic` in
  `skills/neurolearn/report/data/report_prompts_default.toml`.
- User override: `~/.neurolearn/report_prompts.toml` with the
  same `[global] prefix` / `[prompts.<type>] prompt + append_global`
  shape.
- CLI override: `--prompt-template-file <path>` for a one-off.
- Single-call for transcripts under ~15k tokens; **hierarchical**
  chunk-then-assemble for longer ones — per-chunk outlines feed a
  final assembly call for a top-level title + summary.

**Defaults that make the report do the right thing without flags:**
- Auto-detect `report_type` from the transcript via the same
  classifier that powers vision prompts (`tutorial / lecture / code
  / demo / interview / vlog / review / talking_head / generic`,
  mapped onto the three report templates).
- Auto-pick `target_language` from the video's detected language;
  interactive prompt with the detected language as default when
  stdin is a TTY (skipped with `--yes`).
- Friendly install hint if the `report` optional extra is missing —
  no crash, just one-line instructions on how to install.

**Flags** (`neurolearn report --help`):
- `--latest`, `--video-index N` — batch selection / multi-video.
- `--prompt`, `--prompt-file`, `--prompt-template-file`.
- `--report-type {auto|tutorial|vlog|generic}`.
- `--report-language en|ru|...`.
- `--backend {gemini|claude|openai|ollama}` + `--ollama-model/host`.
- `--output <path>`, `--max-images N`, `--max-image-width N`,
  `--no-screenshots`, `--keep-html`, `--yes`.

**Optional dependencies** (`uv sync --extra report`):
- `weasyprint>=62.0` (LGPL, free) for PDF.
- `jinja2>=3.1` for templating.
- `markdown>=3.6` reserved for future inline markdown in summaries.
- On macOS the bundle also requires `brew install pango cairo` for
  WeasyPrint's native libraries; the package primes
  `DYLD_FALLBACK_LIBRARY_PATH` automatically so the brew libs are
  found.

**Resilient parsing.** LLM responses are accepted even when they
arrive wrapped in markdown fences, include preamble, return a
single timestamp/list-item as a string instead of a one-element
list, or contain bracketed timestamps; an unparseable response
produces a degraded outline (so the PDF still renders) rather than
crashing the pipeline.

**Test coverage.** 50 dedicated tests across prompts loader, outliner,
renderer, orchestrator, and CLI (`tests/test_report_*.py`). Full
suite: 1032 passed, 3 skipped, no regressions.

## [0.10.1] — 2026-05-15

### Vision prompts: per-video-type templates + user customization

Replaces the single generic YouTube-flavoured prompt with **9
context-specific templates**. The right prompt is picked
automatically from the transcript; users can override it.

**Built-in types** (in `skills/neurolearn/vision/data/prompts_default.toml`):
  • `tutorial` — UI actions, click targets, before/after states
  • `lecture` — slides, diagrams, equations
  • `code` — IDE, terminal, file paths, errors
  • `demo` — product showcase, feature reveal
  • `interview` — multi-speaker, lower-thirds, B-roll
  • `vlog` — scene, activity, location
  • `review` — product, specs, comparison
  • `talking_head` — narrative monologue with minimal visuals
  • `generic` — fallback for unclassified video

Each template is 300-500 tokens with type-specific rules + a
good/bad example. The previous YouTube-flavoured generic text is
gone; templates are source-agnostic (work for YouTube / IG / TikTok
/ local files).

**Auto-detection** lives in
`skills/neurolearn/detection/video_type_detect.py`. Counts type-specific
signal phrases (e.g. "click/press/нажимаем" for tutorial;
"slide/research shows/today we'll" for lecture) per minute. Whichever
type clears its threshold wins; long videos with no positive signal
default to `talking_head`; short signal-less clips default to `generic`.

**User overrides** at `~/.neurolearn/prompts.toml`. Same shape as the
shipped TOML:

```toml
[global]
prefix = "..."          # universal rules, prepended to every type

[prompts.tutorial]
prompt = "..."          # full per-type instruction
append_global = true    # default; set false to use ONLY this prompt

# Brand-new mode — define your own type:
[prompts.cooking-show]
prompt = "Focus on ingredients, utensils, cooking actions."
append_global = false
```

**New CLI flags** (transcribe + batch):
  • `--video-type <name>` — pin a specific type (skips auto-detect)
  • `--no-global-prefix` — with `--vision-prompt`, drop the global prefix

### Gemini API improvements

- **Caching the right thing**. Previous build cached only the system
  prompt (~150 tokens) which falls below the 1024-token cache
  minimum and never activated. v0.10.1 caches `[uploaded_video,
  system_instruction]` together — the video easily clears the
  minimum, so the bundle qualifies. Per-window calls now reference
  the cache and pay only 25% of the rate on the cached tokens (which
  are the dominant cost). Expected savings: 70-75% of vision tokens
  on multi-window videos.
- **Skip caching when N<2 windows**. For a 1-window video, the
  setup + storage cost outweighs the single cached call. Now we
  bypass cache creation entirely in that case.
- **Adaptive concurrency by Gemini tier**. New `gemini_tier` config
  field: `"free"` (default) → `max_concurrent=3` (under the 5 RPM
  free-tier limit); `"paid"` → 10; `"paid-tier2"` → 20; `"paid-tier3"`
  → 50. Override per-call via constructor `max_concurrent` if needed.
- **Honor server-side retryDelay**. 429 RESOURCE_EXHAUSTED responses
  include `"retryDelay": "31s"` — we now parse and sleep exactly
  that long instead of using the hard-coded `[3, 6, 12]` backoffs
  which previously missed the per-minute quota reset.

### Tests

- 12 new tests in `test_video_type_detect.py` — every type recognised
  on representative transcripts; lecture rejected from tutorial-style
  text; talking_head for long signal-less videos
- 16 new tests in `test_vision_prompts_loader.py` — built-in types
  load, user overrides replace, global prefix prepend, custom types,
  CLI inline template, broken TOML falls back, format_prompt substitution
- 12 new tests in `test_gemini_caching_concurrency.py` — tier mapping,
  retryDelay parsing, cache-skip-on-N=1, cache-with-video-on-N≥2,
  cached-call omits video, cache failure fall-back
- Updated `test_custom_vision_prompt.py` to the new `_resolve_vision_prompt`
  contract (was `_load_vision_prompt`)

Total: 972 passed, 3 skipped.

---

## [0.10.0] — 2026-05-15

### Visual pipeline optimization — 9 improvements

Based on a production-guide audit of our Gemini Flash vision pipeline.
On a typical 10-minute tutorial video, total Gemini cost drops ~12×
and end-to-end visual stage runs ~10× faster.

#### Cost wins

- **MEDIA_RESOLUTION_LOW** for Gemini video uploads — 66 tokens/sec
  instead of 258 (4× cheaper). UI tutorials and most lecture content
  remain legible at LOW; only 4K-detail content would benefit from
  HIGH. (`vision/gemini.py`)
- **Prompt caching** — system instruction is cached once per video,
  reused across all per-window calls. ~75% off input tokens after
  the first window. Falls back gracefully (per-call inclusion) when
  caching is unavailable.
- **Frame downscaling + quality cap** — ffmpeg output frames are
  capped at 1280px wide and JPEG quality 80%. Same description
  accuracy, ~5× smaller file size → fewer image tokens.

#### Quality wins

- **Structured output via response_schema** — Gemini cannot return
  invalid JSON anymore. New schema includes `confidence` (0-1) and
  `needs_refinement` (bool) signals.
- **temperature=0.2 + max_output_tokens=300** — determinism and
  capped output cost.
- **Tutorial preset with asymmetric frame offsets** —
  `-1.5s / +0.3s / +2.0s` relative to the speech event captures
  before-state, the click moment (motor-lag from speech to action
  is ~300ms), and the UI-settled-after state. Far more useful for
  step-by-step UI tutorials than evenly-spaced frames.
- **Claude fallback on low-confidence segments** — when Gemini
  reports `confidence < 0.7` or `needs_refinement=True` (typically
  10-20% of windows), the same windows are re-processed through
  Claude Vision. Better accuracy on small UI text / similar
  elements; only pays Claude pricing on the subset that needs it.
  Requires `ANTHROPIC_API_KEY`; silently skipped if absent.

#### Speed wins

- **Async parallelism** in `GeminiVisionBackend.annotate_segments` —
  `asyncio.Semaphore(10)` concurrent window calls. The sync facade
  is preserved; callers don't need to be async. On 18-window TED Talk
  this drops from ~5 minutes sequential to ~30 seconds.

#### Observability

- **BudgetTracker module** (`skills/neurolearn/budget.py`) — per-call
  token accounting with per-provider USD pricing. Aggregates totals
  by stage (vision_gemini, vision_claude, analyze, asr_correction,
  translate, filter, research_translate). Wired into manifest.json
  so users see what each batch cost without spelunking through
  provider dashboards.

#### New `tutorial` preset + auto-detection

- New built-in preset `tutorial` in `presets/data/presets_default.toml`:
  whisper-local transcribe, gemini vision, keywords_only detection,
  asymmetric frames, Claude fallback.
- **Auto-promotion from smart**: after transcription, when running
  the `smart` preset without explicit `--preset` override, we count
  tutorial-action triggers (click / press / нажимаем / выбираем /
  open / save / select / type / ...) in the transcript. Density
  above 1.5/min auto-promotes to the tutorial preset; a one-line
  notice tells the user. Disable with `--preset smart` explicitly
  or set `auto_tutorial_detect = false`.
- Detector lives in `skills/neurolearn/detection/tutorial_detect.py`
  with hardcoded action regex for ru/en (separate from user-editable
  triggers.toml — this is feature detection, not personalisation).

#### Schema

- `VisualSegment` gained `confidence: float` and `needs_refinement: bool`
  fields. Backward compatible — both default to safe values for old
  callers/test fixtures.

### Tests

- 6 new tests in `test_budget.py` — token math + cost edge cases
- 6 new tests in `test_tutorial_detect.py` — density heuristic in
  ru + en, lecture rejection, short-clip safeguard
- 5 new tests in `test_claude_fallback.py` — refinement triggering,
  Claude error keeps original, empty-list short-circuit
- Updated `test_vision_gemini.py` to match new defensive cache path

Total: 924 passed, 3 skipped.

---

## [0.9.0] — 2026-05-14

### Renamed
- **Project renamed from `youtube-transcribe` to `neurolearn`.**
  Scope:
  - Python package: `skills/youtube_transcribe/` → `skills/neurolearn/`
  - PyPI / CLI binary: `youtube-transcribe` → `neurolearn`
  - Config directory: `~/.youtube-transcribe/` → `~/.neurolearn/`
  - Claude Code plugin name: `youtube-transcribe` → `neurolearn`
  - GitHub repository: github.com/nekith78/youtube-transcribe → github.com/nekith78/neurolearn
    (the old URL keeps redirecting for ~3 months per GitHub policy)
  - Scheduler identifiers: `youtube-transcribe-subscribes` →
    `neurolearn-subscribes` (cron / launchd / systemd / Task Scheduler
    snippets). Any previously installed scheduler entries with the old
    label need to be reinstalled — `neurolearn subscribes schedule
    install` prints the new snippets.

### Auto-migration on first run
- If `~/.youtube-transcribe/` exists and `~/.neurolearn/` doesn't, the
  CLI renames the directory once on first invocation and prints a
  one-line notice to stderr. Idempotent. All API keys, cookies,
  subscribes.toml, history.toml, and triggers.toml carry over without
  user action.

### Why the rename
- The skill outgrew its original scope. v0.7+ added research, subscribes,
  and analyze; v0.8 added Instagram and TikTok. "youtube-transcribe" no
  longer described what the tool does. `neurolearn` better reflects the
  current focus: learning from videos across platforms — transcribe,
  analyze, research a topic, follow channels over time.

---

## [0.8.0] — 2026-05-14

### Added
- **Instagram & TikTok in `subscribes`** — `subscribes add` accepts
  IG profile URLs and TikTok user URLs. Per-platform fetch dispatch
  in `subscribes/pipeline.py`: YouTube via RSS (no cookies), Instagram
  and TikTok via yt-dlp with the user's registered Netscape
  `cookies.txt`. `subscribes update --platform {youtube|instagram|tiktok}`
  filters to a single platform.
- **Instagram fallback via instaloader** — when yt-dlp's IG profile
  extractor is marked broken upstream (which happens periodically),
  we fall back to instaloader for profile listing. Opt-in extra:
  `uv sync --extra instagram`. Prints a one-time per-process warning
  on first fallback ("intended for occasional fetches, not bulk
  scraping"). See `subscribes/instagram_loader.py`.
- **Interactive URL/query prompts** — `transcribe`, `batch`,
  `subscribes add`, and `research` accept an empty positional and
  prompt instead. Lets users paste long URLs after running the
  command (keeps them out of shell command lines / shell history).
  Non-TTY callers without args exit 2 with a clear message so CI
  scripts fail fast. See `shared/prompts.py`.
- **Spinner progress for single-video `transcribe`** — `rich.status`
  spinner with stage labels (Downloading audio... / Transcribing via
  X... / Post-processing...). `--verbose` switches to plain dim
  print lines so raw yt-dlp / SDK output stays readable. Non-TTY
  degrades automatically. See `shared/progress.py`.
- **Cookies onboarding wizard** — `subscribes cookies set <platform>`
  with interactive `questionary.path()` prompt (Tab-completion +
  drag-and-drop). Validates Netscape format before saving. Stores
  registered file at `~/.neurolearn/<platform>-cookies.txt`
  with mode 0600. See `subscribes/cookies_onboarding.py`.

### Changed
- **Security: strict file-only cookies.** All paths that previously
  accepted `--cookies-from-browser` now require an explicit Netscape
  `cookies.txt` file (`--cookies-file <path>` for transcribe/batch;
  `subscribes cookies set <platform> <path>` for IG/TT). Rationale:
  `cookies-from-browser` reads the user's entire browser cookie store
  into process memory — even on macOS where Keychain prompts, an
  "Always Allow" grant silently leaks all unrelated cookies. We
  refuse to take that risk; the cost is one manual cookies-export
  step.
- **All user-facing CLI strings migrated to English.** Wizard, error
  messages, status lines, prompts, help text — previously a Russian /
  English mix, now English-only. Industry standard for CLIs with a
  global audience.
- **`smart` backend fallback now downloads audio.** Previously
  `transcribe URL --backend smart` failed with "Audio file not found:
  <url>" when subtitles fast-path didn't succeed (e.g. YouTube
  IpBlocked on TimedText). All non-subtitles backends require a local
  audio file; `run_smart` now downloads into a temp directory before
  invoking the fallback backend.
- **yt-dlp broken-extractor diagnostic.** `_diagnose_ytdlp_error` now
  checks for "Unable to extract data" / "marked as broken" at the
  TOP of the hint ladder, before generic geo/country/auth heuristics
  could win on misleading sub-strings of the same stderr. Without
  this, the subscribes pipeline's broken-extractor detection never
  fired for IG and the instaloader fallback was silent.
- **Stale `yt-tr` references removed from README.** The real CLI
  binary has always been `neurolearn`; `yt-tr` was never an
  alias. 18 occurrences corrected.

### Dependencies
- `instaloader>=4.13` — new optional extra `[instagram]`.

### Fixed
- `subscribes` pipeline now propagates broken-extractor exceptions
  from `_fetch_via_yt_dlp` instead of swallowing them. Enables the
  instaloader fallback to actually fire for Instagram.

---

## [0.7.0] — 2026-05-12

### Added
- `research "query"` — broad topic discovery: multi-language YouTube
  search (LLM-translates query into each `--languages`), date window
  (`--days N` or `--since/--until`), substring `--match` and LLM
  `--filter` pre-screens, optional TTY checkpoint, batch transcribe,
  optional analyze. Also supports `--in-subscribes` to source from
  your subscribed channels instead of global search.
- `subscribes` command group (`add`/`remove`/`list`/`edit`/`update`)
  for tracking favourite channels. Stateful incremental updates
  (`last_seen_video_id` per channel in subscribes.toml). Override
  with `--days`/`--since`/`--until` runs ad-hoc without disturbing
  state. RSS-first discovery (~10× faster than yt-dlp scraping);
  `--no-rss` forces yt-dlp fallback (not yet implemented in v0.7).
- `subscribes schedule install --every <interval>` — generates cron /
  launchd / systemd / Windows Task Scheduler snippet + install
  instructions. Does NOT install automatically.
- `history list` / `history show` — persistent log of research and
  subscribes runs in `~/.neurolearn/history.toml`.
- Web UI tab builders — `build_research_tab(gr)` and
  `build_subscribes_tab(gr)`. (Default `build_ui()` still ships the
  v0.5 transcribe form; call the new builders from your custom
  Gradio Blocks if needed.)
- Channel groups in subscribes.toml (`group = "ai-research"`).
  `subscribes list --group X` and `subscribes update --group X`.

### Changed
- `batch_cmd` refactored: post-args-resolution core extracted as
  `_run_batch_pipeline(targets, cfg, opts)` so research/subscribes
  pipelines reuse it without duplication. External behavior of
  `neurolearn batch` preserved byte-for-byte (all 614 v0.6
  tests stay green).

### Dependencies
- No new runtime dependencies. RSS via stdlib `xml.etree.ElementTree`
  + `urllib.request`. Everything else already in v0.2/v0.6 deps.

## [0.6.0] — 2026-05-12

### Added
- `neurolearn analyze [SOURCE]` — free-form LLM analysis over
  one or more existing transcripts. Supports `--prompt`/`--prompt-file`,
  `--backend gemini|claude|openai|ollama`, `--latest`, `--all`,
  `--select "1,3,5-7"`, `--append-to <md>`, `--output <path>`,
  `--no-stdout`, `--max-chars`.
- Interactive `questionary` checkbox picker for video selection when
  SOURCE is a folder and no `--all`/`--select`/`--latest` is given.
- `batch --then-analyze --prompt "..."` runs analyze on the produced
  batch folder immediately after the batch completes.

### Changed
- `summarize` now routes through `analyze.runner` internally (same
  hardcoded TL;DR + key points + notable quotes template; same exit
  codes; same output file format). No user-visible behavior change.

### Dependencies
- New: `questionary>=2.0` (powers the analyze picker).

## [0.5.2] — 2026-05-11

Course-correct: revert / refactor v0.5.1 additions that drifted from spec.

### Removed

- **VTT output format.** Was an invented addition not in any spec.
  `--output-format vtt` choice and `write_vtt()` function removed.
- **Auto-summary `--summary` flag in `transcribe` / `batch`.** Spec
  explicitly said summarization is done by Claude in chat reading
  `combined.md`, not by the skill in v0.x. Auto-trigger removed.
- **`summary` field on `TranscriptionResult`** + `summary` param in
  `write_json()` — no longer populated by pipeline.

### Added

- **`neurolearn summarize <transcript-path>`** — standalone
  sub-command. User invokes explicitly on an existing
  transcript file (`.txt` / `.json` / `.srt`). Backend picked via
  `--backend gemini|claude|openai|ollama`. Output: `<file>.summary.md`
  next to the source (or `--output PATH`).
- **`utils/transcript_loader.py`** — reads `.txt` / `.json` / `.srt`
  back into `list[Segment]`. Used by the `summarize` command.

### Tests
- 544 unit tests green (was 533 in v0.5.1; -7 from VTT removal,
  +16 from new loader + summarize).

## [0.5.1] — 2026-05-11

Power-user polish.

### Added

- **`--summary` flag** — generates a Markdown auto-summary (`## TL;DR`,
  `## Key points`, `## Notable quotes`) alongside the transcript via a
  single cheap LLM call (gemini / claude / openai / ollama).
  `<basename>.summary.md` is written when transcript completes.
- **`--output-format {txt,srt,vtt,json,all}` (repeatable)** — choose any
  combination of output files. Defaults to `txt` + `srt` for backward
  compatibility. JSON includes full transcript + quality + visuals +
  summary — drop-in for tooling/automation.
- **`--vision-prompt FILE`** — provide a custom vision-LLM template
  file. Placeholders: `{language}`, `{transcript_snippet}`,
  `{start_sec}`, `{end_sec}`. Tutorial authors can tune the description
  style without forking the package.

### Changed

- `TranscriptionResult` gains a `summary: str = ""` field. Backward-
  compatible with v0.5.0 callers.
- `write_json()` and `write_vtt()` added to `utils/output_writer.py`.
  JSON uses `ensure_ascii=False` so Cyrillic and other scripts stay
  readable in the file.

### Tests
- 533 unit tests green (was 510 in v0.5.0; +23).

## [0.5.0] — 2026-05-11

Local-LLM + multi-speaker + multi-language.

### Added

- **Ollama backend for ASR correction** (`--correct-asr-backend ollama`).
  Local llama3.2:3b by default — no API key, no cloud round-trip.
  POSTs to http://localhost:11434/api/generate via stdlib urllib.
  Two new registry fields: `ollama_model` (default `llama3.2:3b`) and
  `ollama_host` (default `http://localhost:11434`).
- **Speaker diarization** via pyannote.audio (`--diarize`). Prepends
  each segment's text with `[SPEAKER_NN]`. Opt-in `[diarization]` extra,
  requires HF_TOKEN env var + license at
  https://huggingface.co/pyannote/speaker-diarization-3.1.
  `diarize_num_speakers` field constrains the model when known
  (0 = auto-detect).
- **Auto-translate** (`--translate-to <lang>`). Translates each segment's
  text via cheap LLM (gemini-flash / claude-haiku / gpt-4o-mini / local
  Ollama) while preserving timestamps + speaker labels. Backend chosen
  via `--translate-backend` (default `gemini`).

### Tests
- 510 unit tests green (was 484 in v0.4.1; +26 v0.5 tests).

## [0.4.1] — 2026-05-11

### Added

- **`--correct-asr` CLI flag** for both `transcribe` and `batch`
  sub-commands. Auto-enables `--check-quality` (correction triggers
  off the quality recommendation). Honored by `--no-quality-check`
  if user explicitly overrides.
- **`--correct-asr-backend gemini|claude|openai`** picks the LLM
  provider for ASR correction.
- **Rich Live progress bar in batch_cmd.** Spinner + progress bar +
  `ok=N fail=N` counters + elapsed time. Auto-disabled with
  `--verbose` or when only one video is being processed.

### Tests
- 484 unit tests green (was 480 in v0.4.0; +4 CLI ASR flag tests).

## [0.4.0] — 2026-05-11

Multimodal alternatives + post-processing + Instagram + Web UI.

### Added

- **Claude Sonnet vision backend** (`--vision-backend claude`). Images-only,
  reuses ffmpeg keyframes. Default model: claude-sonnet-4-6. Needs
  `ANTHROPIC_API_KEY`.
- **OpenAI GPT-4o vision backend** (`--vision-backend openai`). Images-only,
  base64 data URLs. Default model: gpt-4o.
- **ASR error correction** (`correct_asr: true` in preset, or future CLI
  flag). When quality check flags a transcript as fallback / low_quality,
  one cheap LLM call (gemini-flash / claude-haiku / gpt-4o-mini) fixes
  garbled/truncated words. Best-effort: returns original on any error.
  Provider via `correct_asr_backend` registry option.
- **Instagram URL recognition.** `is_instagram_url`,
  `extract_instagram_shortcode` for `/p/`, `/reel/`, `/tv/`, `/reels/`
  patterns. yt-dlp handles the downloading; tailored error message hints
  to `--cookies-from-browser` when login required.
- **Web UI** via Gradio (`neurolearn webui`). URL/file input,
  preset/backend selectors, visual + ASR-correct toggles. Output tabbed:
  Transcript / Visual moments / Quality. Local-only by default
  (127.0.0.1:7860). Opt-in via `[webui]` extra.

### Changed

- `vision_backend` choices now `["off", "gemini", "claude", "openai"]`.
- `_BACKEND_ENV_VAR` now includes `anthropic` → `ANTHROPIC_API_KEY`.
- `core deps` adds `anthropic>=0.40.0` (small; comparable to existing
  openai/groq SDKs).
- `_VISION_KEY_MAP` in presets/loader.py honors all three vision
  backends with their respective env vars for silent fallback.

### Tests
- 480 unit tests green (was 437 in v0.3.1; +43 v0.4 tests).

## [0.3.1] — 2026-05-11

### Added

- **Russian perplexity support.** `quality/perplexity.py` `_LANG_MODELS` now
  maps `ru` → `sberbank-ai/rugpt3small_based_on_gpt2` (~550 MB lazy
  download). Calibration constants (50 baseline / 150 divisor) shared
  with English — may need per-language tuning on real data.
- **README v0.3 documentation.** New `Batch power-flags (v0.3)` section
  with examples for `--since/--until/--min-duration/--max-duration/--no-shorts`,
  `--skip-existing`, `--workers N`, `--search "query"`, plus a flag
  reference table.

### Fixed

- `test_version_bumped` was hard-coded to `0.2.` prefix — fails on
  every minor bump. Now uses `int(major) >= 0 and int(minor) >= 2`.

### Tests
- 437 unit tests green (was 434 in v0.3.0; +3 Russian-perplexity tests).

## [0.3.0] — 2026-05-11

Major batch features.

### Added

- **`--since YYYY-MM-DD` / `--until YYYY-MM-DD`** — filter channel/playlist/search
  results by upload date.
- **`--min-duration SECONDS` / `--max-duration SECONDS`** — filter by duration.
- **`--no-shorts`** — skip YouTube Shorts (videos ≤ 60s heuristic).
- **`--skip-existing`** — skip videos already transcribed in `output_dir`
  (rglob `*.txt`, dedup by video_id suffix). Useful for incremental
  channel re-fetches.
- **`--workers N`** — parallel batch processing via ThreadPoolExecutor.
  Cloud backends benefit; whisper-local saturates serially. Output may
  interleave; incompatible with `--fail-fast`.
- **`--search "query"`** — YouTube search via yt-dlp `ytsearchN:`. No API
  key needed. Combines with inline URLs / `--from-file` if also set.

### Changed

- `ResolverFilters` gained `search_query` field; `Source` Literal
  extended with `"search"`.

### Tests

- 434 unit tests green (was 402 in v0.2.2; +32 v0.3 tests).

## [0.2.2] — 2026-05-11

### Real-validation fixes (v0.2.1 features broken under live testing)

- **Frame_diff dropped strong-signal windows.** LLM-classifier returned
  a valid window for an elephant zoo video (`score=0.9, "elephants visual"`),
  but `refine_with_frame_diff` dropped it as static talking-head. Same
  applied to user-defined raw / strict triggers — explicit intent that
  shouldn't be overridden by perceptual hashing. Now refinement skips
  windows whose `reason` starts with `raw` / `strict:` / `llm_full_pass:`.

- **Perplexity brick was non-functional.** `lmppl 0.3.x` is incompatible
  with current `transformers` (uses deprecated `use_auth_token` kwarg →
  `TypeError` at LM init). Replaced with direct `transformers` usage
  (already pulled by sentence-transformers). `[perplexity]` extra is now
  a no-op marker.
- **Perplexity score recalibration.** Old formula `mean_ppl / 500` barely
  fired even on garbled text. New: `max((mean_ppl - 50) / 150, 0)` capped
  at 1.0. Normal English speech (PPL 30-80) → ~0 penalty. PPL 125 → 0.5.
  PPL 200+ → 1.0 saturated.

### Polish

- **Aho-Corasick automaton caching.** Previously rebuilt on every
  `match_segment` call — 1500-segment video = 1500 × C-level
  `make_automaton()`. Now cached via `lru_cache(maxsize=16)` by
  hashable `(phrase, weight)` tuple. Identical phrase sets across
  configs share the same automaton.

- **Bag-of-Hallucinations expanded** from 22 to 59 phrases. Added more
  Whisper-typical loops ("turn on notifications", "ring the bell",
  "amara.org", "yandex subtitles", "auto-generated by"), more Russian
  goodbye patterns (kept verbatim because they are detection-list
  samples), and "subscribe + ring bell" variants.

### Tests
- 402 unit tests green (was 393 in v0.2.1; +7 cache tests).

## [0.2.1] — 2026-05-11

### Closed Important issues from final code review of v0.2.0

- **Step 1**: `keywords_only` / `semantic` / `hybrid` / `llm_full_pass`
  are now actually distinct. `match_segment` accepts a `mode=` kwarg.
  `keywords_only` no longer loads the 118MB MiniLM model — saves memory
  on pure-keyword runs.
- **Step 2**: `detect_frame_changes_in_window` integrated into the
  pipeline. In `hybrid`/`llm_full_pass`, empty (talking-head) windows
  are dropped; visually-rich windows get a score boost of ×1.3.
- **Step 3**: `llm_full_pass` now runs a real LLM classify pass. One
  text-only Gemini call per video, parses JSON timecodes, returns up to
  10 windows with `reason="llm_full_pass:<why>"`.
- **Step 4**: brick F (perplexity) implemented. Replaced `kenlm` with
  `lmppl` (uses transformers, already pulled in via
  sentence-transformers). English via GPT-2 small. Penalty in score up
  to 0.25 for fully anomalous text. Opt-in via
  `enable_perplexity=True` (or `quality_perplexity=true` in presets).

### Changed
- `[project.optional-dependencies] perplexity` now requires
  `lmppl>=0.3.0` instead of `kenlm>=0.2.0`. KenLM required pre-built
  ARPA models (impractical for end users).

### Tests
- 390 unit tests green (was 346 in v0.2.0; +44 tests).

## [0.2.0] — 2026-05-11

### Added
- Visual mode (`--with-visuals`) — multimodal video analysis via Gemini
  (frames + audio). Embedded screenshots in combined.md.
- Quality check for transcripts (smart mode picks between
  ready-made subtitles and whisper automatically).
- Multilingual triggers via local embeddings (paraphrase-multilingual-MiniLM-L12-v2).
- Triggers CLI tool: `triggers init/add/list/remove/reset/edit/test/weight`.
- Dynamic presets (eco/smart/standard/premium) backed by a single
  options registry.
- `--config` flag for alternative config files.
- `--ocr` opt-in flag for OCR on keyframes.

### Changed
- `BatchVideoStatus` extended with `quality` and `visual_segments` fields.
- `manifest.json` now includes a quality breakdown and visual_segments.
- `combined.md` contains a `### Visual moments` section with inline screenshots.

### Migration v0.1.x → v0.2
- Auto-migration of an existing `~/.neurolearn/config.toml` into
  the `[presets.custom_legacy]` shape, preserving every user setting.
- When `GEMINI_API_KEY` is set, visual mode is silently enabled in
  the smart preset. Otherwise behaviour is fully v0.1-compatible.

### Dependencies (new)
- core: pyspellchecker, pyahocorasick, langdetect, sentence-transformers,
  lemminflect, pymorphy3, tomlkit, scenedetect, imagehash
- optional: pytesseract+easyocr (extra `ocr`), kenlm (extra `perplexity`)

---

## [v0.1.1] — 2026-05-09 (planned hotfix)

### Fixed
- **`resolver.resolve()` now collect-and-continue per spec §5.** Previously raised `UnresolvableInput` on the first inline URL probe failure, aborting the whole batch. Now returns `(targets, failures)` tuple — bad URLs are logged in `errors.log` (stage `resolve`), good URLs continue. Both `transcribe` (single) and `batch` sub-commands updated.
- **`wizard.py` API key prompt now hides input** (`password=True`). Previously the entered key echoed visibly to the terminal.
- **PEP 508 marker for `faster-whisper`** uses de-Morgan form `sys_platform != 'darwin' or platform_machine != 'arm64'` (hatchling rejects `not (...)` syntax).
- **`packages = ["skills"]`** in `[tool.hatch.build.targets.wheel]` so editable install resolves `skills.neurolearn.*` correctly. Without this fix the entry-point script failed with `ModuleNotFoundError`.
- **`config.save_config` is atomic** (write-temp-then-rename) so a killed process doesn't leave a truncated TOML file.
- **`config.set_api_key` rejects `\n`/`\r` in values** to prevent newline-injection into `.env`.
- **`config.load_config` wraps malformed TOML errors** into a friendly `ValueError` pointing at the wizard.
- **`downloader.download_audio` checks `yt-dlp` BEFORE `mkdir`** so a missing binary doesn't leave debris.
- **`downloader._extract_flat` wraps `yt_dlp.utils.DownloadError`** into our own `DownloadError` so callers don't deal with foreign exception types.

### Updated
- **`google-genai>=1.0.0`** (was `>=0.3.0`). The 0.x API was unstable; our backend uses the GA `Client`/`files.upload`/`models.generate_content` pattern.
- **`deepgram-sdk>=7.0.0`** (was `>=3.7.0`). The 7.x API rewrote the request path; older versions are no longer compatible with `backends/deepgram.py`.

### Known issues / backlog
- `batch` exits 0 even when some videos fail. Smart-mode would prefer non-zero exit if `failures > 0` while at least one video succeeded; v0.2.
- Boundary tests deferred: 6144 MB VRAM (NVIDIA threshold), `parse_yt_date` malformed inputs, `_fmt_duration` ≥1 hour branch.
- `_BareURLGroup` works in `uv run`; not yet validated for `uv tool install` from scratch.
- Cloud backends (gemini, groq, openai, deepgram, assemblyai, custom) are tested via mocks only — no live API call has been exercised in CI yet.

---

## [v0.1.0] — 2026-05-09

First public release.

### Architecture
- 8 interchangeable backends behind a single `Transcriber` Protocol:
  - `subtitles` — youtube-transcript-api 1.x (instance API).
  - `whisper-local` — `mlx-whisper` on macOS arm64, `faster-whisper` everywhere else (auto-selected by `platform_detect`).
  - `gemini` — Google AI Studio (google-genai 2.x).
  - `groq` — Groq Whisper API.
  - `openai` — OpenAI Whisper API.
  - `deepgram` — Deepgram Nova-3 (sdk 7.x), word-level → segment grouping.
  - `assemblyai` — AssemblyAI (`best`/`nano`), ms→s conversion.
  - `custom` — generic OpenAI-compatible endpoint.
- `smart` is a composition (subtitles fast-path → fallback), not a backend.
- `Resolver` translates inline URLs / channel-URLs / `--from-file` lists into `ResolvedTarget`s with dedup by `video_id`.
- Single (`transcribe`) and batch (`batch`) sub-commands share a single `run_pipeline()` core (single = batch of 1).
- Bare-URL routing: `neurolearn https://youtu.be/X` lands on `transcribe` via `_BareURLGroup`.

### Output
- Single: `<output-dir>/<slug>_<id>.txt` (with timestamps) + `.srt`.
- Batch: `<output-dir>/batch_<timestamp>_<slug>/{combined.md, manifest.json, videos/, errors.log?}`.
- `combined.md` has YAML frontmatter + per-video sections (flat text, no timestamps) — designed to be read by Claude in a chat.

### Distribution
- Three install paths: Claude Code plugin, personal skill folder, `uv tool install`.
- `install.ps1` (Windows) and `install.sh` (Mac/Linux) bootstrap fallback if `uv` is missing.

### Privacy
- `whisper-local` and `subtitles` never send audio to third parties.
- API keys live in `~/.neurolearn/.env` (mode `0600` on Unix); they are never echoed back unmasked.

### Tests
- 207 unit tests + 2 e2e smoke tests gated by `RUN_E2E_SMOKE=1`.
- mlx-whisper validated end-to-end on a real 19-second public-domain YouTube video on M-series.
