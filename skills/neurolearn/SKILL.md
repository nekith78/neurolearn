---
name: neurolearn
description: |
  Transcribe YouTube / Instagram / TikTok / local-file videos via 8 interchangeable backends
  (local Whisper, YouTube subtitles, Gemini, Groq, OpenAI Whisper API, Deepgram, AssemblyAI,
  OpenAI-compatible custom). Also: RESEARCH a topic ("find recent videos about X" →
  finds, transcribes, returns), SUBSCRIBES to channels ("watch these channels" → RSS
  watch + transcribe new uploads), HISTORY of past runs.
  Use this skill when the user pastes a video URL with intent to read/analyze content,
  asks to "transcribe", "get a transcript", "make text from this video", "subtitles",
  "what's in this video";
  asks to find/research videos by topic ("find videos about X", "research topic X",
  "what's new about Claude features", "research AI agents this week");
  asks to follow a channel ("subscribe to channel X", "watch @AnthropicAI",
  "what's new on this channel", "watch this channel for new videos");
  provides a YouTube channel/playlist URL ("whole channel", "last N videos", "this playlist");
  or provides a local media file. Use for explicit backend switching ("via gemini",
  "local whisper large", "use groq").
  DO NOT use for: general questions about transcription technology, requesting video
  recommendations without source URLs, recording/creating videos, or operating on
  already-existing transcripts.
---

# neurolearn Skill

> **For deep mechanics** (full CLI reference, architecture, failure modes
> per backend) read `docs/agent-reference.md` inside the plugin install
> dir. This SKILL.md covers triggers and quick decisions; the reference
> covers everything else.

## How to invoke the CLI

**Always prefer `${CLAUDE_PLUGIN_ROOT}` (zero-config).** Claude Code sets
this env var to the plugin install dir. The plugin ships its own venv
via `uv run --project`, so this form works immediately after
`/plugin install` without the user needing to run `uv tool install`:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn <subcommand> [flags]
```

**Fallback** (only if `${CLAUDE_PLUGIN_ROOT}` is empty): use plain
`neurolearn <subcommand>` — works when the user has a global install
via `uv tool install neurolearn` or pip.

If the bare `neurolearn` command returns "command not found", relay this:

> The `neurolearn` CLI isn't on PATH. Install once:
> `uv tool install --from "${CLAUDE_PLUGIN_ROOT}" neurolearn`

All examples below use the bare `neurolearn ...` form for brevity. When
you actually invoke the CLI inside Claude Code, prefix it with
`uv run --project "${CLAUDE_PLUGIN_ROOT}"`.

## Onboarding — REQUIRED first-time setup (v0.13.0+)

**HARD RULE**: `neurolearn` refuses to run transcribe / batch / analyze /
research commands while `config.onboarding_complete == false`. The CLI
exits with code **7** and a message pointing here. Only escape: passing
`--backend whisper-local` (offline; no keys needed).

**DO NOT** try to bypass this by setting whisper-local on every call —
the user wants to be asked. The correct response on a fresh install is:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Check `config.onboarding_complete`:

- **`true`** → user has completed setup. Skip onboarding and serve their
  actual request.
- **`false` (or missing field)** → STOP. Do NOT attempt the user's
  request yet. Tell them: "I see neurolearn isn't fully configured yet.
  I'm going to walk you through setup now — won't take more than a minute."
  Then run the **`/setup`** flow (see `commands/setup.md` for the full
  multi-step procedure: working mode → audio → vision → analyze → tier →
  keys via file → `complete-onboarding`).

### Key security — file-based handoff only

The user's API key must NEVER appear in chat history. When you (Claude)
need to register a key:

1. Tell the user to manually paste the key into a file at a path THEY
   choose (e.g. `~/Desktop/groq-key.txt`).
2. Ask them only for the file PATH.
3. Run:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set-key groq --from-file <PATH>
```

The CLI reads the key from the file and stores it at `~/.neurolearn/.env`
(mode 0600). It prints a masked confirmation; relay that to the user.
Tell them they can delete the temp file now.

**Forbidden**: `neurolearn config set-key groq <PASTED_KEY>` when the key
came through chat. The positional form is fine when the user is
typing it directly into their own terminal; for Claude Code → CLI
interactions, use `--from-file` only.

If the user has ALREADY pasted a key into chat by mistake, tell them to
revoke that key at the provider console (it's now in chat history),
then walk them through the file-based handoff for a fresh key.

### When NOT to run the pre-flight check

- The user has explicitly chosen `--backend whisper-local` or
  `--backend subtitles` (no key needed; gate auto-bypasses these).
- The user has already been onboarded earlier in this same chat — don't
  re-run `doctor` every turn (cache the result in your context).
- The user explicitly said "skip setup, just try" — relay the gate
  message exactly so they understand the trade-off, then offer the
  whisper-local fallback.

## Backend choice cheat-sheet (v0.12+)

Pick the backend BEFORE invoking, based on user intent + environment.

| User intent / situation | Recommended invocation | Why |
|---|---|---|
| Fast transcript from YouTube (default) | `--backend smart` (or omit `--backend`) | Subtitles fast-path → Groq Whisper turbo → whisper-local fallback. v0.12 default. |
| Offline / no API keys / privacy | `--backend whisper-local --whisper-model turbo` | mlx-whisper on Apple Silicon, faster-whisper elsewhere. No network. |
| Paid Gemini tier + 3.5-flash configured | `--backend gemini` | URL path: no download, no upload. Only safe with timestamp-accurate Gemini models. |
| Free Gemini tier (anyone) | `--backend smart` (NOT `--backend gemini` for audio) | Gemini 3.5-flash free tier is only 20 RPD; use Groq instead. |
| Instagram / TikTok URL | any backend (smart works) | Non-YouTube providers don't accept URL natively. Smart downloads audio then transcribes. |
| Need keyframes / visual analysis | `--with-visuals` (Groq Llama-4-Scout by default v0.12) | Or `--preset standard / premium / tutorial`. See "Visual moments" section below. |
| Diarization (who-said-what) | `--diarize` | Adds pyannote; requires HF token. Doesn't change transcription backend. |
| Very high accuracy | `--backend whisper-local --whisper-model large` | Best Whisper variant. Or `--backend deepgram --deepgram-model nova-3`. |

If unsure: `smart` is the safe default — `subtitles → groq → whisper-local`.

## Quota awareness (v0.12+)

Default audio is **Groq Whisper-large-v3-turbo**, default vision is
**Groq Llama-4-Scout**, default analyze LLM is **Groq Llama-3.3-70b**.
One Groq API key covers all three.

| Stage | Backend | Free tier limit | Comment |
|---|---|---|---|
| Audio | Groq Whisper turbo | 8 hours of audio per day, 2,000 RPD | ~12s per 17-min video |
| Audio fallback | Gemini 3.5-flash | **20 RPD only** | Use sparingly; only when Groq unavailable |
| Vision per-frame | Groq Llama-4-Scout | 1,000 RPD, 30 RPM | ~1.2s per frame, 5 frames max per request |
| Vision fallback | Gemini 2.5-flash | 250 RPD | Used when Groq vision unavailable. (2.5-flash for vision is safe — the +63% timestamp bug only affects AUDIO output.) |
| Analyze LLM | Groq Llama-3.3-70b | 14,400 RPD | Replaces Gemini's tiny 20 RPD for batch/research workloads |

**v0.10.6+ note**: the default `smart` preset does NOT enable vision
automatically. A plain `neurolearn transcribe <URL>` does audio only.
Vision is opt-in via `--with-visuals` or via `--preset standard /
premium / tutorial`.

**v0.12.0 + audio-only-on-2.5-flash warning**: if user has the legacy
`gemini-2.5-flash` audio model in their config, `doctor --json` reports
it in `ready.recommended_setup[]` and the gemini backend prints a
stderr warning at runtime. Relay the fix:
`neurolearn config set gemini-model gemini-3.5-flash`.

**On 429 `RESOURCE_EXHAUSTED`:**
- `--backend smart` (default) auto-falls-back: groq fails → whisper-local.
- `--backend gemini` exits with `BackendError`. No fallback when explicit.
- Gemini free quotas reset daily at midnight Pacific. The error message
  includes `retryDelay` for per-minute limits; daily caps don't surface
  a clean reset time.

## Visual moments — vision pipeline (v0.12+)

`--with-visuals` triggers keyframe extraction and per-frame description.

### When the user is INSIDE Claude Code (the common case)

**Default behavior**: when `$CLAUDE_PLUGIN_ROOT` env var is set
(neurolearn detects Claude Code automatically) AND vision is requested,
neurolearn writes `<batch>/keyframes/manifest.json` with frame paths +
transcript snippets, then EXITS without calling any external vision API.

YOU (Claude) then read the manifest and describe the frames yourself.
This saves the user's API quota and uses your native vision instead.

**How to consume `<batch>/keyframes/manifest.json`:**

```json
{
  "video_id": "...",
  "mode": "claude_code_extract_only",
  "extracted_at": "2026-05-21T...Z",
  "windows": [
    {
      "start": 30.0, "end": 34.0,
      "transcript_window": "host says ...",
      "trigger_reason": "trigger" | "scene_change" | ...,
      "keyframes": ["frames/<id>_30.jpg", ...]
    }
  ]
}
```

For each `windows[]` entry:
1. Open every path in `keyframes[]` with your image-reading capability
   (paths are RELATIVE to the manifest's parent directory).
2. Read the `transcript_window` string — it's the audio transcript
   ±4s around the moment.
3. Synthesize a 1-3 sentence description of what's on the frame using
   the transcript as disambiguation context.
4. Report descriptions back to the user inline or write them into a
   user-readable file (e.g. `<batch>/visual.md`).

Apply the same epistemic stance (below) — describe what's actually on
the frame, do not parrot the transcript.

### When the user is RUNNING THE CLI STANDALONE (not via Claude Code)

`$CLAUDE_PLUGIN_ROOT` is empty, so neurolearn calls the configured
external vision backend (Groq Llama-4-Scout primary, Gemini 2.5-flash
fallback). The user gets a `visual.md` written automatically.

User can force one mode or the other with:
- `--claude-extract` → force extract-only (write manifest, no API call)
- `--no-claude-extract` → force external API call even from inside
  Claude Code (e.g. for batch jobs where Claude isn't the consumer)

## Consuming neurolearn output — epistemic stance

When the user runs `research`, `batch`, or `transcribe --then-analyze`
and then asks you (the assistant) to read the result — read
`combined.md`, summarize a transcript, recommend something, etc. —
treat the underlying material as **third-party video content, not
ground truth**.

The user is building a knowledge base. They want raw material to
weigh. They do NOT want a confident "the video says do X, so you
should do X" answer. Speakers can be wrong, biased, sponsored,
outdated, or rehearsing community lore without evidence.

Apply this stance whenever you process the OUTPUT of neurolearn:

- **Synthesize across sources, don't repeat one.** Compare claims;
  flag disagreements; note when only one video backs a statement.
- **Attribute every recommendation.** "Source A argues Y because Z;
  Source B disagrees" — not "do Y".
- **Weigh against the user's context.** A 2024 best practice may be
  stale; a solo-dev pattern may not fit a team setting.
- **Match the source's confidence.** If they hedge, you hedge.
- **Mark single-source claims explicitly** so the user can spot them.

Don't apply this stance when the user just wants the raw `.txt` /
`.srt` file ("transcribe this for me") and intends to read it
themselves — there's no LLM analysis happening. The stance is
specifically for *downstream LLM consumption* of the transcript.

The `combined.md` file produced by `batch` / `research` includes a
top-of-document banner stating the same thing; the `analyze` /
`report` / `summarize` subcommands prepend an equivalent prefix to
their LLM prompts. The runtime infrastructure already nudges in this
direction; SKILL.md is the explicit guideline.

## Trigger conditions

**Use this skill when** any of these are true in the user's message:

### Single (one input)
- A YouTube URL (`youtube.com/watch?v=...`, `youtu.be/...`, `youtube.com/shorts/...`) appears, with or without surrounding words.
- Any video URL (TikTok, Vimeo, Twitter/X video, Twitch VOD, etc.) appears with intent to extract content.
- A local file path ending in `.mp3 / .mp4 / .wav / .m4a / .mkv / .webm / .opus / .flac` appears with intent to extract speech.
- Direct request: "transcribe", "get transcript", "make text from this video", "extract text".
- Request for subtitles: ".srt", "make subtitles", "give me subs", "generate captions".
- Content-question about a linked video: "what's in this video", "what's it about", "what do they say".
- Request to summarize/analyze a video by URL (transcribe first, then Claude analyzes).
- Request for timestamps, quotes, or time-coded references in a video.
- Backend switching: "via gemini", "local whisper", "use groq", "switch to subtitles".

### Batch (multiple inputs)
- The message contains **2 or more YouTube/video URLs**.
- A YouTube channel URL (`youtube.com/@name`, `youtube.com/c/...`, `youtube.com/channel/UC...`).
- A YouTube playlist URL (`youtube.com/playlist?list=...`).
- Phrases: "transcribe these videos", "process all these links", "here are several URLs", "multiple videos at once".
- Phrases: "whole channel", "last N videos from the channel", "all videos from this channel", "everything on @channel".
- Phrases: "take this playlist", "everything in this playlist", "the whole playlist".
- A path to a `.txt` file containing URLs ("here's a file with links").

### Research (find videos by topic — no URL provided)
- Phrases: "find videos about X", "find clips on topic X", "research X",
  "what's new about Claude features", "research AI agents this week",
  "what's being said about <topic> this month", "find recent videos about X".
- The user wants Claude to discover videos on a topic. NO URL is given.
- Optional language hints: "English only", "ru + en", "this week", "this month",
  "top-10", "first 5".

### Subscribes (channel watch — follow uploads over time)
- Phrases: "subscribe to channel X", "watch this channel", "subscribe to @name",
  "what's new on channel X", "check subscriptions", "update subscriptions",
  "new videos from my channels".
- The user provides a channel URL/handle and wants automatic follow-up over time.
- Group-based phrasing: "channel goes to group AI", "all AI channels", "subscribes group ai-research".

**Do NOT use this skill when:**

- The chat already contains a transcript and the user is asking about the *text* (not the source).
- The question is conceptual: "what is whisper", "how does transcription work", "compare models".
- The user wants a *recommendation* of a video (no source URL provided).
- The user wants to *create*, *record*, or *edit* video content.
- The user is asking about installing/configuring this skill itself ("how do I install", "show me your code").

## Languages

The description above is multilingual on purpose. Triggering happens by semantic match — Russian, English, Ukrainian, Kazakh, German, Spanish, French phrasings all work. Always pass `--language ru` (or whatever the user's language is) explicitly when you can detect it; otherwise omit and let Whisper auto-detect.

## How to invoke

Run the CLI from the user's shell. The CLI is installed globally (Claude Code plugin path or `uv tool install`).

### Single

```
neurolearn transcribe <URL_or_path> [flags]
```

A bare `neurolearn <URL>` (no sub-command) is also accepted for back-compat — it routes to `transcribe`.

### Batch

```
neurolearn batch <URL1> <URL2> ... [--limit N] [flags]
neurolearn batch <channel-or-playlist-URL> --limit 10 [flags]
neurolearn batch --from-file urls.txt [flags]
```

**Recommendation for big channels:** add `--backend subtitles` for the whole batch. A 50-video channel through `whisper-local` takes hours; through subtitles it's a couple of minutes. Quality is "what YouTube auto-recognized" — but enough for a summary/note. If subtitles fail on a video, individual fallback is up to the user (not the skill in v0.1).

### Research (find videos by topic)

```
neurolearn research "<query>" [--languages ru,en] [--days 30] [--limit 20] \
    [--match "substring"] [--filter "LLM pre-screening question"] \
    [--backend subtitles] [--no-analyze] [--yes] [--output-dir <path>]
```

**Default behavior:** search YouTube via the user's query (translated to each language
in `--languages` if multi-lang), filter by date (`--days N` → uses YouTube's built-in
`sp=` filter for 1d/1w/1mo/1y presets, falls back to client-side refine), dedupe by
video_id, transcribe with the chosen backend, write to `<output-dir>/research_<auto-slug>/`.

**Critical for Claude:** ALWAYS pass `--no-analyze` when invoking `research` from chat.
You are the LLM that will analyze the transcripts — there is no point routing them
through Groq/Gemini/OpenAI/Ollama via the CLI's `--analyze-backend`. After the command
returns, read `<batch_dir>/combined.md` yourself and answer the user's actual question.

### Subscribes (channel watch + incremental update)

```
neurolearn subscribes add "<channel-url>" [--group <name>]
neurolearn subscribes list [--group <name>]
neurolearn subscribes remove "<channel-url-or-handle>"
neurolearn subscribes edit
neurolearn subscribes update [--group <name>] [--days N] [--no-rss] \
    [--match "..."] [--filter "..."] [--no-analyze] [--yes] [--output-dir <path>]
neurolearn subscribes schedule install [--every 1d] [--platform auto]
neurolearn subscribes schedule uninstall
```

**Add a channel:** stores in `~/.neurolearn/subscribes.toml`. Resolves
`@handle` URLs to stable `channel_id` once at add-time, so subsequent updates
don't need to re-resolve. Group is optional — used for `--group` filtering later.

**Update flow:** for each channel, fetch its YouTube RSS feed (fast), filter to
videos newer than `last_seen_published`, transcribe, write to a fresh batch dir.
After successful run, advance `last_seen_*` so the next `update` is incremental.
On first run for a channel, `--days N` or `--since YYYY-MM-DD` is required to
bootstrap the window.

**Critical for Claude:** same rule as research — ALWAYS pass `--no-analyze` and
read `combined.md` yourself in chat. Do not pipe through `--analyze-backend`.

### History (past runs)

```
neurolearn history list [--last N] [--type research|subscribes]
neurolearn history show <run-id>
```

IDs have the form `r-MMDD-HHMMSS` (research) or `s-MMDD-HHMMSS` (subscribes). The
full timestamp is also in the `When` column. Reading `history show <id>` returns
the original query, output path, prompt preview, and status — handy when the user
asks "what was I working on last week" or "open the AI agents research I ran".

### Analyze (post-hoc on already-transcribed batch)

```
neurolearn analyze --latest --all --prompt "..." --backend gemini
neurolearn analyze --batch <batch_dir> --select "1,3,5-7" --prompt-file p.md
```

Used after a transcription run if you want one LLM pass over selected transcripts.
Most Claude-in-chat flows don't need this — just read `combined.md` directly.

### Report (PDF generation, v0.10.2)

```
neurolearn report --latest                              # most recent batch
neurolearn report <batch_dir> --yes                     # specific batch, no prompts
neurolearn report --latest --prompt "Filter scope..."   # narrow with a user filter
neurolearn report --latest --report-type tutorial       # force layout
neurolearn report --latest --no-screenshots --keep-html # text-only + HTML
```

Takes a transcribed batch (manifest.json + SRT + keyframes) and
produces a structured PDF with TOC, sections, embedded keyframes,
and inline timestamps. Auto-detects video type and language, with
flag overrides for both. Optional deps: `uv sync --extra report`.

### Default behavior

- No flags → uses configured default backend (v0.11+: `smart` cascade with Groq as primary fallback by default).
- First-run automatically launches `wizard` (interactive setup).
- Single output: `./transcripts/<name>.txt` and `<name>.srt`.
- Batch output: `./transcripts/batch_<timestamp>_<auto-slug>/` with `videos/`, `combined.md`, `manifest.json`, optional `errors.log`.

### Backend switching (3 levels)

**Per-call** — when the user explicitly mentions a backend in their message, add `--backend <name>`:

| User says | Append to command |
|---|---|
| "via gemini", "use gemini" | `--backend gemini` |
| "via groq", "use groq" | `--backend groq` |
| "local whisper large" | `--backend whisper-local --whisper-model large` |
| "use subtitles", "pull subtitles" | `--backend subtitles` |
| "via openai" | `--backend openai` |
| "deepgram", "use Nova-3" | `--backend deepgram` |
| "assemblyai" | `--backend assemblyai` |
| "via custom", "use my custom api" | `--backend custom` |
| "gemini pro" | `--backend gemini --gemini-model gemini-2.5-pro` |

**Session-level** — when the user says "until I say otherwise, use X" or "for this whole conversation use Y", remember the choice and apply `--backend X` to ALL subsequent invocations in this session. Honor it until the user changes it.

**Persistent (changes config file)** — when the user says "switch the default to groq" / "set default to gemini" / "always use whisper-local", run:

```
neurolearn config set backend <name>
```

This writes to `~/.neurolearn/config.toml` and affects all future sessions.

### Other useful sub-commands

- `neurolearn doctor [--json]` — diagnostic command; JSON is machine-parseable. Key fields: `config.onboarding_complete` (v0.13.1+ gate signal), `ready.has_fast_audio` / `has_fast_vision` / `has_analyze_backend`, `ready.recommended_setup[]` with exact fix commands.
- `neurolearn config show` — list current settings + which API keys are configured (human-readable)
- `neurolearn config get <key> [--json]` — print a single config value (v0.12.2+). Kebab-case keys (e.g. `backend`, `vision-backend`, `onboarding-complete`, `gemini-url-fastpath`).
- `neurolearn config set <key> <value>` — write a single config field.
- `neurolearn config set-key <backend> [VALUE]` — set an API key. v0.13.0+: prefer `--from-file <path>` for chat-safe handoff (key never enters chat history). Other forms: positional value (terminal-only), `--from-env VAR`, `--from-stdin`. Bare form prompts via TTY.
- `neurolearn config complete-onboarding` — v0.13.0+ — flip the gate to True after a manual /setup walkthrough. The TTY wizard does this implicitly at the end.
- `neurolearn config test <backend>` — sanity-check a backend's configuration
- `neurolearn config wizard` — re-run the first-run wizard (TTY-only; refuses non-TTY contexts with exit 2)

## Platform support — what works where

| Command | YouTube | Instagram | TikTok | Other yt-dlp sites | Local files |
|---|---|---|---|---|---|
| `transcribe <URL>` / `batch <URL>` | ✓ | ✓ (cookies) | ✓ | ✓ | ✓ |
| `research "query"` | ✓ | ✗ | ✗ | ✗ | n/a |
| `subscribes` | ✓ (RSS) | ✓ (cookies + yt-dlp / instaloader fallback) | ✓ (cookies + yt-dlp) | ✗ | n/a |

- **Instagram / TikTok** require cookies (register a `cookies.txt` via
  `neurolearn subscribes cookies set <platform> <path>`) — IG/TT
  block anonymous requests. Mention this if a user tries IG/TT URLs
  without cookies set.
- **Research** is YouTube-only because `yt-dlp ytsearchN:` only supports
  YouTube; IG/TikTok search via API would require auth tokens.
- **Subscribes (v0.8)** supports YouTube via RSS, plus Instagram and
  TikTok via yt-dlp scrape (cookies required). When yt-dlp's IG
  extractor is broken upstream, instaloader takes over (install with
  `uv sync --extra instagram`).

## Analyze backend (when CLI calls an LLM)

The CLI has an optional `--analyze-backend {groq|gemini|openai|ollama}` flag that
runs an LLM pass on the transcripts and writes `analysis-*.md` inside the batch dir.

**From inside Claude Code: you should NOT use it.** You're already the LLM in the
conversation — paying API for a second round-trip is wasteful and slow. Always pass
`--no-analyze` (or omit `--prompt`/`--prompt-file`) when invoking from chat, then
read `combined.md` yourself and answer the user directly.

**Onboarding behavior** (relevant if a user runs the CLI standalone, not via Claude):
on first interactive run without `--analyze-backend`, the CLI prompts once and
persists the choice in `~/.neurolearn/config.toml`. In a non-TTY context
(like Claude Code subprocess), no prompt is shown and analyze is skipped silently —
exactly the behavior we want.

## After running

### After single

Always read the generated `.txt` file and offer the user a short summary or answer their original question (e.g. was the URL accompanied by "what's in this video"? — answer that). Do NOT echo the entire transcript back unless asked.

### After batch / research / subscribes update

Read the generated `combined.md` from the batch directory printed in stdout. Offer the user one of:
- **Topic note** — extract key insights, group by topic, deduplicate repeated points across videos.
- **Summary** — short paragraph per video + cross-video themes.
- **Study plan** — ordered reading list, noting what each video adds.

Use the per-video `source_language` field in `manifest.json` if multi-lang research
(`--languages ru,en`) to group findings by query origin.

Mention the batch directory path so the user can re-open it later. If `errors.log` exists, briefly summarize which videos failed and why.

For `research` runs, the run is also logged to `~/.neurolearn/history.toml`
with an ID `r-MMDD-HHMMSS`. Mention this ID if the user might re-open later.

If the run fails, the CLI prints a friendly hint (yt-dlp blocked → cookies, key missing → set-key, etc.). Relay the hint to the user clearly.

## Privacy note

The default backend (`whisper-local`) processes everything locally — nothing is sent to the network. Cloud backends (gemini, groq, openai, deepgram, assemblyai, custom) DO send the audio to the respective provider. Mention this if the user asks about privacy or seems sensitive about the content.

### combined.md (v0.2)

When `--with-visuals` was used, `combined.md` contains a
`### Visual moments` section with embedded screenshots and
descriptions of the visual moments. It's a full markdown tutorial —
use it as the base for notes or a study plan.

When the user asks for "a tutorial / walkthrough for this video":
1. Use the visual moments as structural anchors.
2. Cite timestamps in `00:00:45` format.
3. Inline screenshots are already embedded — reference them via
   relative paths.

When quality < 0.6 (warning in `combined.md`):
- The transcript may contain recognition errors.
- Screenshots remain reliable.
- Help the user work with what's there; don't refuse.
