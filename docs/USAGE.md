# Usage

Full command reference for `neurolearn`. For install steps see [INSTALL.md](INSTALL.md);
for backend selection see [BACKENDS.md](BACKENDS.md); for Claude Code chat patterns see
[CLAUDE_CODE.md](CLAUDE_CODE.md).

## Table of contents

- [`transcribe` — one URL / file](#transcribe)
- [`batch` — many URLs, channel, playlist](#batch)
- [`analyze` — free-form LLM over transcripts](#analyze)
- [`research` — discover videos by topic](#research)
- [`subscribes` — channels you follow](#subscribes)
- [`report` — PDF from a batch](#report)
- [`history` — log of past runs](#history)
- [`triggers` — control visual analysis](#triggers)
- [`config` — settings + API keys](#config)
- [`schedule` — cron / launchd / Task Scheduler snippets](#schedule)

---

## transcribe

```bash
# Interactive — paste the URL when prompted
neurolearn transcribe --language en

# Inline (good for scripts)
neurolearn transcribe https://youtu.be/dQw4w9WgXcQ --language en

# Pull YouTube's own subtitles (fastest, no GPU)
neurolearn transcribe https://youtu.be/dQw4w9WgXcQ --backend subtitles

# Cloud backend
neurolearn transcribe video.mp4 --backend gemini

# Local file
neurolearn transcribe /path/to/lecture.mp4 --language ru

# Slash command in Claude Code
/transcribe https://youtu.be/xyz
```

Output: `./transcripts/<title>.txt` and `<title>.srt` per video.

### Progress UI

```
⠋ Downloading audio...
⠙ Transcribing via gemini...
⠹ Post-processing...
✓ gemini | language=en | duration=58.8s
```

Modes:

- **Default** — rich.status spinner. Compact, non-disruptive.
- **`--verbose`** — spinner OFF; raw yt-dlp / SDK output + dim stage lines (`· Downloading audio...`). Use for debugging.
- **Non-TTY** (pipe, CI, Claude Code subprocess) — auto-degrades to plain text writes.

### Visual mode

Pass `--with-visuals` to get a transcript plus key visual moments with embedded
screenshots in `combined.md`:

```bash
neurolearn transcribe https://youtube.com/watch?v=... --with-visuals
```

Default vision backend is **Groq Llama-4-Scout** (`GROQ_API_KEY`), Gemini fallback.
Inside Claude Code (`$CLAUDE_PLUGIN_ROOT` detected), vision auto-uses extract-only
mode — neurolearn writes `keyframes/manifest.json` and Claude reads frames in
chat (no extra API call).

If neither Groq nor Gemini key is set, visual analysis is silently disabled and
you get a plain transcript.

### Presets

A preset bundles transcribe backend, fallback, visual analysis, keyframe
detection, and quality check under one name. Pick with `--preset <name>` or set
`default_preset` in `~/.neurolearn/config.toml`.

| Preset | Transcribe | Quality check | Vision | Detection |
|---|---|---|---|---|
| `eco` | subtitles → fallback | off | off | keywords only |
| `smart` (default) | subtitles → quality check → fallback | on | opt-in | hybrid |
| `standard` | whisper-local | on | gemini | hybrid |
| `premium` | whisper-large | on | gemini | LLM full pass |

```bash
neurolearn URL --preset eco              # nothing leaves the machine
neurolearn URL --preset standard         # whisper-local + visual moments
neurolearn URL --preset smart --frames-per-window 5
```

---

## batch

Transcribe a list of URLs, a whole channel, or a playlist with one command.

```bash
# Interactive — paste URLs one per line, empty line to finish
neurolearn batch

# Inline
neurolearn batch https://youtu.be/AAA https://youtu.be/BBB

# Whole channel, top-10 recent videos, fast path via YouTube subtitles
neurolearn batch https://youtube.com/@anthropicai --limit 10 --backend subtitles

# From a file (1 URL per line, # — comment)
neurolearn batch --from-file ~/learn/claude-videos.txt --backend gemini

# Playlist, 5 videos via local Whisper
neurolearn batch https://youtube.com/playlist?list=PLxxx --limit 5 \
    --backend whisper-local --whisper-model turbo
```

**Defaults:** `--limit 10`, sequential (not parallel), `continue-on-error` (if
one video fails, the remaining 9 still run). Stop on first failure with
`--fail-fast`.

### Output layout

```
./transcripts/batch_2026-05-09_15-30-12_anthropicai/
├── combined.md       ← one file with all transcripts + metadata (for Claude chat)
├── manifest.json     ← machine-readable copy
├── videos/           ← per-video .txt + .srt
└── errors.log        ← only if at least one video failed
```

### Power flags

```bash
# Channel filters — date and duration window
neurolearn batch https://youtube.com/@anthropicai \
    --since 2026-01-01 --until 2026-12-31 \
    --min-duration 300 --max-duration 3600 \
    --no-shorts --limit 20

# Incremental re-fetch: skip videos already transcribed
neurolearn batch https://youtube.com/@anthropicai --skip-existing --limit 50

# Run 4 videos in parallel (useful for cloud backends with large RPM budgets)
neurolearn batch <playlist> --workers 4 --backend gemini

# Search YouTube by topic — no API key needed
neurolearn batch --search "claude code tutorial" --limit 10

# Combination: search + filters + parallelism + vision
neurolearn batch --search "transformer architecture" \
    --since 2025-01-01 --no-shorts --min-duration 600 \
    --limit 20 --workers 4 --backend gemini --with-visuals
```

| Flag | Meaning |
|---|---|
| `--since YYYY-MM-DD` | Only videos uploaded on or after this date |
| `--until YYYY-MM-DD` | Only videos uploaded on or before this date |
| `--min-duration N` / `--max-duration N` | Filter by duration in seconds |
| `--no-shorts` | Skip YouTube Shorts (≤60s) |
| `--skip-existing` | Don't re-transcribe a video if `_<video_id>.txt` already exists |
| `--workers N` | Process N videos in parallel; incompatible with `--fail-fast` |
| `--search "query"` | YouTube search via yt-dlp (no API key needed) |

### Chain with analyze

```bash
neurolearn batch https://www.youtube.com/@channel --limit 5 \
  --backend smart \
  --then-analyze --prompt "Bullet the main takeaways from each video." \
  --analyze-backend gemini
```

---

## analyze

Free-form LLM analysis over one or more existing transcripts.

```bash
# Single transcript
neurolearn analyze ./transcripts/x.txt \
  --prompt "Extract the main argument and counter-examples." \
  --backend gemini

# Most recent batch (skips picker)
neurolearn analyze --latest \
  --prompt-file my-prompt.md --backend groq

# Pick a subset of videos in a folder interactively
neurolearn analyze ./transcripts/batch_2026-05-11_claude/ \
  --prompt "Compare how each speaker frames the problem." \
  --backend openai

# Append a new analysis block to an existing combined.md
neurolearn analyze --latest \
  --prompt "Now extract every URL mentioned." \
  --append-to ./transcripts/batch_X/notes.md

# Local LLM, no API keys
neurolearn analyze ./transcripts/x.json \
  --prompt "Summarize for a 12-year-old." \
  --backend ollama --ollama-model llama3.2:3b
```

Output goes to `<batch>/analysis-YYYY-MM-DD-HHMM.md` (or next to the source for
single-file mode), and is also printed to stdout so it's inline-visible when
called from Claude Code.

---

## research

Discover and analyze new videos on a topic in one command.

```bash
# Interactive
neurolearn research --prompt "Outline the key ideas" --analyze-backend gemini

# Default — last 30 days, ru+en search, top 20 results
neurolearn research "Claude updates" \
  --prompt "Outline the key ideas" --analyze-backend gemini

# Narrower
neurolearn research "AI agents 2026" \
  --days 7 --languages en --limit 10 \
  --prompt "Compare design choices"

# Historical window
neurolearn research "LangChain release" \
  --since 2024-06-01 --until 2024-08-31 \
  --prompt "What's new"

# Substring + LLM filter combo
neurolearn research "machine learning" \
  --match "tutorial" --filter "beginner-friendly tutorials" \
  --prompt "What's in common, what's unique"

# Just transcripts, no analyze
neurolearn research "AI news 2026" --no-analyze

# Cross-pollination: only from subscribed channels
neurolearn research "Claude" --in-subscribes --group ai-research \
  --days 14 --prompt "Recent updates"
```

**About the analyze step.** By default, on the first interactive run `research` /
`subscribes update` / `batch --then-analyze` asks once which LLM to use for the
analyze pass (skip / groq / gemini / openai / ollama) and persists the choice in
`~/.neurolearn/config.toml`. Override per-call with `--analyze-backend X`. In a
non-TTY context (Claude Code subprocess, CI, piped run) the prompt is skipped
and the analyze pass is silently skipped — `combined.md` is the output and the
chat-side LLM does the analysis. Force-skip with `--no-analyze`.

---

## subscribes

```bash
# Add — interactive
neurolearn subscribes add --group ai

# Or inline
neurolearn subscribes add https://www.youtube.com/@anthropic-ai --group ai
neurolearn subscribes add https://www.youtube.com/@lexfridman --group philosophy

# List
neurolearn subscribes list
neurolearn subscribes list --group ai

# Edit subscribes.toml manually (cross-OS $EDITOR)
neurolearn subscribes edit

# Remove
neurolearn subscribes remove @anthropic-ai

# Update — incremental (stateful per channel)
neurolearn subscribes update --prompt "What was discussed"

# Update — force window
neurolearn subscribes update --days 7 --group ai \
  --filter "only about new models" --prompt "Compare approaches"

# Generate scheduler snippet (does not auto-install)
neurolearn subscribes schedule install --every 1h --prompt "your usual prompt"
```

The `subscribes` store lives at `~/.neurolearn/subscribes.toml` and is safe to
hand-edit; CLI mutations preserve your comments via `tomlkit`.

### YouTube content modes (Shorts handling) — v0.17+

By default, `subscribes update` fetches full uploads from the channel's
`/videos` tab. **The `/videos` tab excludes Shorts** (and livestreams),
so channels that publish nothing but Shorts (or paused full uploads)
look silent. v0.17 adds a per-channel `mode` field that tells
`subscribes update` which content streams to pull.

> **v0.20:** the YouTube video source switched from the RSS feed to the
> `/videos` tab. RSS mixed in livestreams/premieres (and was empty for
> some channels), so it could surface a stream as "the latest video".
> The `--no-rss` flag is now a deprecated no-op.

```bash
# Set the mode when adding a channel (YouTube only)
neurolearn subscribes add https://www.youtube.com/@somechannel --mode shorts-only

# Change the mode of an existing subscription
neurolearn subscribes set-mode @somechannel shorts-and-videos
neurolearn subscribes set-mode @somechannel videos-only   # back to pre-v0.17 behavior

# Per-call override (mutex group; wins over stored mode for this run only)
neurolearn subscribes update --shorts-only --days 7
neurolearn subscribes update --include-shorts --days 7
neurolearn subscribes update --no-shorts --days 7

# Cap how many Shorts per channel per update (default 5; 0 = no cap)
neurolearn subscribes update --shorts-cap 10 --days 7
```

The four modes:

| Mode | Sources | When to use |
|---|---|---|
| `auto` *(default)* | `/videos` first; falls back to `/shorts` only when `/videos` has nothing in the window | Most channels — captures Shorts only when there's nothing else fresh |
| `videos-only` | `/videos` only, never `/shorts` | A channel you don't want Shorts from |
| `shorts-only` | `/shorts` only, `/videos` never fetched | Channels that publish nothing but Shorts |
| `shorts-and-videos` | Both streams every run, deduped by `video_id`, sorted newest-first | Channels that mix both and you want to see everything |

**Behavior change:** every subscription created before v0.17 (no `mode` in
toml) loads as `auto`, which means they **will start pulling Shorts** as
a fallback when the `/videos` tab is empty. To preserve the old behavior
for a specific channel:

```bash
neurolearn subscribes set-mode <handle> videos-only
```

The cap (`--shorts-cap N` flag or `subscribes.shorts_max_per_update` in
`config.toml`) is per-channel-per-update and applies to Shorts only —
full videos remain uncapped. When the cap fires, `subscribes update`
prints a stderr warning naming the channel and the found-vs-taken
numbers, so you never silently miss content.

Mode is YouTube-only — IG/TT channels ignore it. `subscribes list`
shows the column populated for YouTube rows and `—` for the others.

### Instagram & TikTok subscribes

Both platforms need cookies (no anonymous access for profile listing):

```bash
# Export cookies.txt from your browser via the "Get cookies.txt LOCALLY" extension
neurolearn subscribes cookies set instagram /path/to/ig-cookies.txt
neurolearn subscribes cookies set tiktok    /path/to/tt-cookies.txt

# Add channels
neurolearn subscribes add https://www.instagram.com/natgeo/   --group walk-ig
neurolearn subscribes add https://www.tiktok.com/@anthropic    --group dev

# Update only one platform at a time
neurolearn subscribes update --platform instagram --days 7 \
  --backend whisper-local --yes --no-analyze
```

**Instagram fallback.** yt-dlp's IG profile extractor is periodically broken
upstream; we automatically fall back to `instaloader` — install with
`uv sync --extra instagram`. You'll see a one-time per-process warning when
the fallback activates. It's intended for occasional fetches.

**Cookies are strict file-only.** We deliberately do NOT support
`--cookies-from-browser`. See [cookies-walkthrough.md](cookies-walkthrough.md).

---

## report

Take any batch produced by `transcribe` / `batch` (with or without visual
moments) and render a structured PDF: title, executive summary, table of
contents, sectioned content, inline timestamps, embedded keyframes.

```bash
# Install the optional report extra once
uv sync --extra report
# macOS only: brew install pango cairo   # WeasyPrint native deps

# Render from the most-recent batch, ask language interactively
neurolearn report --latest

# Specific batch, force tutorial layout, English
neurolearn report ~/.neurolearn/out/<batch_dir>/ \
  --report-type tutorial --report-language en --yes

# Narrow scope with a user filter — keeps only matching sections
neurolearn report --latest \
  --prompt "Only sections about authentication and error handling."

# Text-only (no screenshots), keep the intermediate HTML for inspection
neurolearn report --latest --no-screenshots --keep-html

# Use a local LLM instead of Gemini
neurolearn report --latest --backend ollama --ollama-model qwen3:8b
```

**Three built-in layouts** — auto-picked by re-running the v0.10.1 type detector
on the transcript, or pinned with `--report-type`:

- `tutorial` — step-by-step format, imperative section titles, code blocks verbatim
- `vlog` — highlights-only: surfaces moments where the creator shows information (prices, products, on-screen graphics). Skips pure narration.
- `generic` — section-by-section outline by topic shifts

### Custom prompts

Override the built-in per-type templates the same way vision prompts do in
v0.10.1:

```toml
# ~/.neurolearn/report_prompts.toml
[global]
prefix = "Always reply in concise English. Use [HH:MM:SS] for timestamps."

[prompts.tutorial]
prompt = "Step-by-step layout, but always end with a 'Common pitfalls' section."
append_global = true

# Brand-new custom type
[prompts.cooking-recipe]
prompt = "Extract ingredients, steps, timings. Keep measurements verbatim."
append_global = false
```

Then `neurolearn report --latest --report-type cooking-recipe`.

Long videos (>~15k transcript tokens) automatically switch to a hierarchical
chunk-then-assemble pass — per-chunk outlines feed a final assembly call for a
top-level title + executive summary.

---

## history

```bash
neurolearn history list
neurolearn history list --type research --last 5
neurolearn history show <run-id>
```

---

## triggers

Triggers control where visual analysis fires inside a video. A trigger is a
phrase (or list of phrases) that, when spoken near a section of the transcript,
flags that section as visually interesting.

```bash
# Create a user triggers.toml
neurolearn triggers init

# Add phrases (separator: ;)
neurolearn triggers add --universal "look here; for example; demo"

# Per-language strict (exact match)
neurolearn triggers add --strict --lang ru "баг; PR"

# Bump the weight of an important phrase
neurolearn triggers weight set --universal "function" 1.5

# Check which triggers fire on a specific phrase
neurolearn triggers test "look at this code right here"
```

---

## config

```bash
neurolearn config show
neurolearn config set backend groq
neurolearn config set whisper-model turbo
neurolearn config set language ru
neurolearn config set-key gemini       # interactive key entry
neurolearn config set-key groq --from-file ~/key.txt   # for Claude Code chat (key never enters chat)
neurolearn config test groq            # verify the key works
neurolearn config wizard               # re-run the setup wizard
neurolearn config complete-onboarding  # mark setup done (skips re-running wizard)
```

API keys are masked everywhere they're printed: `sk-***...XYZ`.

---

## schedule

Generate (but never auto-install) a scheduler snippet for cron / launchd /
systemd / Task Scheduler:

```bash
neurolearn subscribes schedule install --every 1h --prompt "Daily watchlist"
# → prints the snippet + install instructions for your platform
```
