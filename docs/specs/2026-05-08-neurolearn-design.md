# Design doc: neurolearn

**Date:** 2026-05-08
**Status:** Draft for review
**Author:** brainstorm with the user (Claude Code)

---

## 1. Goal

Build a reusable `neurolearn` skill that:

1. Accepts a YouTube video URL (or another supported platform) or a path to a local media file.
2. Transcribes the content via one of six interchangeable engines (backends).
3. Saves the result to `.txt` (with and without timestamps) and `.srt`.
4. Triggers from Claude Code in natural language in any language (Russian, English, Ukrainian, Kazakh, etc.) — the user just says "transcribe this" and pastes the link.
5. Also provides a `/transcribe` slash command and works as a standalone CLI without Claude.
6. **Ships in three ways** so any user can install quickly — as a Claude Code plugin, as a personal skill in `~/.claude/skills/`, or as a uv tool from Git/PyPI.

**Main principle:** zero friction for the end user. One-command install, sensible defaults, clear errors, no manual CUDA/cuDNN dance.

---

## 2. Audience and non-functional requirements

### Audience

- **Regular users** — want to drop a link and get text back. No Python/CUDA knowledge.
- **Technical users** — want to pick the model, the engine, fine-tune. They understand the difference between float16 and int8.
- **Developers** — may want to fork and extend (a new backend, diarization, etc.).

### Privacy (important)

- **Default mode = offline.** The `whisper-local` backend sends nothing over the network after the model is installed.
- **Cloud backends** (gemini, groq, openai, custom) send audio to the provider's servers. The README and wizard warn about this explicitly.
- API keys **never** end up in git, in logs, or in chat with Claude. Storage — env vars or `~/.neurolearn/.env` with `0600` permissions.

---

## 3. Distribution and installation

A single GitHub repository powers three install variants. All three must work out of the box.

### Method A — Claude Code Plugin (recommended for most users)

```bash
git clone https://github.com/<user>/neurolearn ~/.claude/plugins/neurolearn
```

Claude picks up the skill and the slash command automatically. The wizard runs on first use.

### Method B — Personal skill folder

```bash
git clone https://github.com/<user>/neurolearn /tmp/yt-transcribe
cp -r /tmp/yt-transcribe/skills/neurolearn ~/.claude/skills/
cd ~/.claude/skills/neurolearn && uv sync
```

No plugin wrapping. Works as a skill only (no slash command).

### Method C — CLI only, no Claude

```bash
uv tool install git+https://github.com/<user>/neurolearn
```

A `neurolearn` command appears in the terminal. Usable in scripts, other IDEs, without Claude at all.

### Dependency loader: `uv`

We use `uv` (Astral) instead of `pip`:
- Single-file binary, available on every platform.
- 10–50× faster than `pip`.
- Installs the right Python version itself if it is missing.
- Solves the "user has no Python at all" case.

`install.ps1` and `install.sh` are thin wrappers that: (a) install `uv` if it is missing, (b) run `uv sync` inside the repo. This is a **backup path** for users who don't even have `uv`.

---

## 4. Architecture and file layout

```
neurolearn/
├── .claude-plugin/
│   └── plugin.json                       # Claude Code plugin metadata
├── skills/
│   └── neurolearn/
│       ├── SKILL.md                      # Triggers + usage rules
│       ├── transcribe.py                 # CLI entry point
│       ├── wizard.py                     # First-run setup wizard
│       ├── config.py                     # config.toml + .env loader/writer
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── base.py                   # Abstract Transcriber
│       │   ├── subtitles.py              # youtube-transcript-api
│       │   ├── whisper_local.py          # faster-whisper / mlx-whisper
│       │   ├── gemini.py                 # google-genai SDK
│       │   ├── groq.py                   # OpenAI-compat
│       │   ├── openai_api.py             # OpenAI Whisper API
│       │   ├── deepgram.py                # Deepgram Nova-3
│       │   ├── assemblyai.py              # AssemblyAI
│       │   └── custom.py                 # Generic OpenAI-compat
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── platform_detect.py        # auto-detect OS/GPU/VRAM
│       │   ├── downloader.py             # yt-dlp wrapper + cookies + retries
│       │   └── output_writer.py          # .txt + .srt
│       └── tests/
│           ├── test_platform_detect.py
│           ├── test_output_writer.py
│           └── test_backends.py          # smoke tests with mocks
├── commands/
│   └── transcribe.md                     # /transcribe slash command
├── pyproject.toml                        # uv tool install + entry_point
├── requirements-mac.txt                  # dep snapshot for Apple Silicon
├── requirements-nvidia.txt               # dep snapshot for Win/Linux + NVIDIA
├── install.ps1                           # bootstrap for Windows (if no uv)
├── install.sh                            # bootstrap for Mac/Linux
├── README.md                             # Two-layered documentation
├── LICENSE
└── docs/
    ├── specs/
    │   └── 2026-05-08-neurolearn-design.md
    └── plans/
        └── (implementation plan added later)
```

### Backend abstraction principle

`backends/base.py` defines the interface:

```python
class Transcriber(Protocol):
    name: str
    supports_url: bool          # can it handle a URL directly (subtitles can, the rest go through downloader)
    supports_local_file: bool

    def is_configured(self) -> tuple[bool, str | None]:
        """Check that the backend is ready. Returns (ok, reason_if_not_ok)."""

    def transcribe(self, audio_path: Path | str, *, language: str, **opts) -> TranscriptionResult:
        ...

@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]   # for .srt and .txt with timestamps
    language_detected: str | None
    backend_name: str
    duration_seconds: float
```

Each backend — one file, one implementation of the interface. Tests are written against the interface.

---

## 5. Backends (detailed)

### 5.1 `subtitles` — youtube-transcript-api

**When:** YouTube link with auto subtitles.
**Speed:** 2–5 seconds for any video length.
**Quality:** medium (whatever YouTube auto-recognised).
**Dependencies:** `youtube-transcript-api`.
**API key:** not needed.
**Behaviour:**
- If the video has no subtitles in the requested language — tries auto-translation; if that also fails — returns "couldn't do it", the skill switches to the fallback backend (when smart mode is on).
- `.srt` timestamps come from the subtitles (they are already split into segments).

### 5.2 `whisper-local` — local Whisper (default)

**When:** default. Works offline.
**Dependencies:**
- On macOS Apple Silicon: `mlx-whisper`.
- On Windows/Linux + NVIDIA: `faster-whisper`.
- On CPU-only: `faster-whisper` with `device="cpu"` and `compute_type="int8"`.

The implementation choice is made by `platform_detect.py` automatically, without user input.

**Models** (via `--model`):

| Parameter | Description | When to use |
|---|---|---|
| `turbo` (default) | large-v3-turbo | Most tasks: podcasts, lectures, interviews |
| `large` | large-v3 | Maximum accuracy, legal/medical recordings |
| `medium` | medium | Balance on weak hardware (8 GB RAM/VRAM) |
| `small` | small | Quick rough draft |
| `distil` | distil-large-v3 (faster-whisper only) | Fastest full-quality, optimised for English |

**Per-platform model mapping:**

```python
MODEL_MAP = {
    "turbo":  {"mlx": "mlx-community/whisper-large-v3-turbo", "faster": "large-v3-turbo"},
    "large":  {"mlx": "mlx-community/whisper-large-v3-mlx",   "faster": "large-v3"},
    "medium": {"mlx": "mlx-community/whisper-medium-mlx",     "faster": "medium"},
    "small":  {"mlx": "mlx-community/whisper-small-mlx",      "faster": "small"},
    "distil": {"mlx": None,                                   "faster": "distil-large-v3"},
}
```

When an incompatible pair is chosen (e.g. `--model distil` on Mac) — clear error, no stack trace.

**Default `compute_type`:** `auto`. Logic:
- `mlx-whisper` — the parameter is ignored (it has its own mode).
- `faster-whisper` + CUDA + VRAM ≥ 6 GB → `float16`.
- `faster-whisper` + CUDA + VRAM < 6 GB → `int8_float16`.
- `faster-whisper` + CPU → `int8`.

The user can override via `--compute-type`.

### 5.3 `gemini` — Google AI Studio

**When:** you want quality but local Whisper is too slow.
**Speed:** 30–120 seconds per hour of video (depends on upload size).
**Dependencies:** `google-genai` SDK.
**API key:** `GEMINI_API_KEY` or via the wizard. Get one at: https://aistudio.google.com/apikey
**Models:**
- `gemini-2.5-flash` (default) — free, fast, accurate.
- `gemini-2.5-pro` — more accurate, slower, tighter limits.

**Notes:**
- Gemini natively understands video — you can send the whole mp4 (for short files) or extract audio and send mp3 (for long ones, to avoid limits).
- We use the Files API for files > 20 MB.
- Prompt: `Transcribe this audio. Output JSON: {"language": "...", "segments": [{"start": ..., "end": ..., "text": "..."}, ...]}. Use precise timestamps.`

### 5.4 `groq` — Groq Whisper API

**When:** when the fastest cloud option is needed.
**Speed:** 5–20 seconds per hour of audio (Groq runs Whisper on dedicated LPU chips).
**Dependencies:** `groq` SDK or `openai` SDK with the Groq base_url.
**API key:** `GROQ_API_KEY`. Get one at: https://console.groq.com/keys
**Models:** `whisper-large-v3` (more accurate), `whisper-large-v3-turbo` (faster, default).

### 5.5 `openai` — OpenAI Whisper API

**When:** the user already has an OpenAI key.
**Speed:** 30–60 seconds per hour.
**Cost:** ~$0.006/minute of audio.
**Dependencies:** `openai` SDK.
**API key:** `OPENAI_API_KEY`.
**Models:** `whisper-1`.

### 5.6 `deepgram` — Deepgram Nova-3

**When:** alternative to the Whisper API. Native word-level timestamps, fast processing.
**Speed:** 15–60 seconds per hour of audio.
**Dependencies:** `deepgram-sdk` Python package.
**API key:** `DEEPGRAM_API_KEY`. Get one at: https://console.deepgram.com/ ($200 starter credit for new accounts).
**Models:** `nova-3` (default, accurate), `nova-2` (stable), `enhanced` (faster).

**Notes:**
- Natively returns word-level timestamps — excellent timing quality for `.srt`.
- The `diarize=True` parameter is available in the API but is not used in v1 (out of scope).
- We convert the Deepgram response (`alternatives[0].words`) into our `Segment[]` by grouping into phrases.

### 5.7 `assemblyai` — AssemblyAI

**When:** alternative with built-in diarization (for a future v2) and solid quality on long interviews.
**Speed:** 30–90 seconds per hour (async queue — submit and wait, the SDK polls for you).
**Dependencies:** `assemblyai` Python package.
**API key:** `ASSEMBLYAI_API_KEY`. Get one at: https://www.assemblyai.com/dashboard/signup (free tier).
**Models:** `best` (default, accurate), `nano` (faster, slightly less accurate).

**Notes:**
- Uploads audio to their CDN, queues it, waits for completion — all transparent via the SDK.
- Returns `utterances` (phrases with timings) — we put them straight into our `Segment[]`.
- Diarization (`speaker_labels=True`) is supported, but not enabled in v1.

### 5.8 `custom` — OpenAI-compatible API

**When:** for power users. Supports Deepgram-OpenAI-bridge, local LiteLLM, vLLM, etc.
**Configuration:**
- `base_url` — URL endpoint
- `api_key` — secret (via env or .env)
- `model` — model name
- Optional: extra parameters via `extra_options`

**Uses** the OpenAI SDK with a custom `base_url`. The user is responsible for compatibility.

### 5.9 Smart mode (not a separate backend, but a composition)

When `default_backend = "smart"`:
1. If the URL is YouTube → try `subtitles`.
2. If it worked — return the result.
3. If it didn't (no subtitles, not YouTube, `--no-fast-path` set) → use `fallback_backend` (default `whisper-local`).

---

## 6. First-run wizard

Runs on the first invocation of the skill (when `~/.neurolearn/config.toml` is missing) **or** via `neurolearn config wizard`.

### Behaviour

1. Greeting, explanation of what this is and what the options are.
2. Hardware auto-detection: OS, NVIDIA GPU presence, VRAM amount, Apple Silicon presence.
3. Recommendation of the most suitable option based on hardware:
   - Strong hardware (RTX 30/40/50, M1+) → recommend `whisper-local`.
   - Weak hardware → recommend `gemini` or `subtitles`.
4. Backend choice menu (see below).
5. If a cloud backend is picked — request an API key with a link where to get it, validate it with a 5-second test request.
6. If `smart` is picked — fallback backend chosen via a separate question.
7. Save to `~/.neurolearn/config.toml`. Keys go into `~/.neurolearn/.env`.

### Sample menu (textual)

```
🎬 neurolearn — first setup

Detected: Windows + NVIDIA RTX 4090 (24 GB)
Recommendation: whisper-local (fully offline, best quality)

Which engine should be the default?

  1) ⭐ whisper-local (recommended for your hardware)
     Local Whisper. Offline, private, best quality.

  2) smart
     Tries YouTube subtitles first (instant); otherwise — chosen fallback.

  3) subtitles
     YouTube subtitles only. Instant, medium quality, YouTube only.

  4) gemini (Google AI Studio)
     Cloud. Free tier. Needs a key.
     Get one: https://aistudio.google.com/apikey

  5) groq
     Cloud. Fastest. Free tier. Needs a key.
     Get one: https://console.groq.com/keys

  6) openai
     Cloud. Paid (~$0.006/min). Needs a key.

  7) deepgram
     Cloud. $200 starter credit. Accurate Nova-3 model. Needs a key.
     Get one: https://console.deepgram.com/

  8) assemblyai
     Cloud. Free tier. Good for long interviews. Needs a key.
     Get one: https://www.assemblyai.com/dashboard/signup

  9) custom
     OpenAI-compatible API. For power users.

> 1
✅ Saved. Default engine: whisper-local

Change the choice: neurolearn config wizard
Use a different engine once: neurolearn <URL> --backend gemini
```

---

## 7. Switching engines in chat (3 levels)

Documented both in SKILL.md (so Claude applies it) and in the README (so the user knows).

### Level 1 — per-call

Claude sees an explicit engine mention in the message and adds `--backend X` to a single invocation.

| User phrase | Command |
|---|---|
| "transcribe this through gemini: <URL>" | `neurolearn <URL> --backend gemini` |
| "run via groq" | `... --backend groq` |
| "locally with whisper large" | `... --backend whisper-local --model large` |
| "grab YouTube subtitles" | `... --backend subtitles` |
| "gemini, but pro instead of flash" | `... --backend gemini --gemini-model gemini-2.5-pro` |

### Level 2 — session-scoped

The user says "use groq for the rest of this conversation" — Claude remembers within the session and adds the flag to all subsequent invocations. This is Claude's behaviour as an agent; SKILL.md explicitly instructs it to do so.

### Level 3 — persistent

Changes the default via CLI:

```bash
neurolearn config show
neurolearn config set backend groq
neurolearn config set whisper-model turbo
neurolearn config set language ru
neurolearn config set-key gemini       # interactive key entry
neurolearn config test groq            # check that the key works
neurolearn config wizard               # rerun the wizard
```

Works from chat too: "switch the default to groq" → Claude runs `neurolearn config set backend groq`.

---

## 8. CLI parameters

```
neurolearn <URL_or_path_to_file> [options]

Engine selection:
  --backend {smart,subtitles,whisper-local,gemini,groq,openai,deepgram,assemblyai,custom}
                                         Which engine to use (default: from config)
  --whisper-model {turbo,large,medium,small,distil}
                                         Model for whisper-local (default: turbo)
  --gemini-model NAME                    Gemini model (default: gemini-2.5-flash)
  --groq-model NAME                      Groq model (default: whisper-large-v3-turbo)
  --deepgram-model NAME                  Deepgram model (default: nova-3)
  --assemblyai-model NAME                AssemblyAI model (default: best)

Output:
  --output-dir DIR                       Where to save (default: ./transcripts)
  --timestamps / --no-timestamps         Include timestamps in .txt (default: true)
  --srt / --no-srt                       Produce .srt (default: true)
  --language LANG                        Language (ru, en, kk, uk, …) (default: auto)

Whisper-specific:
  --device {auto,cuda,cpu,mps}           Device (default: auto)
  --compute-type {auto,float16,int8_float16,int8}
                                         (default: auto)
  --beam-size N                          (default: 5)
  --vad / --no-vad                       Voice activity detection (default: true)

Download:
  --keep-audio                           Keep the downloaded mp3
  --cookies-from-browser {chrome,firefox,edge,safari}
                                         Use cookies to bypass YouTube blocks

Misc:
  --no-fast-path                         Disable the subtitles fast path in smart mode
  --verbose                              Verbose output
  --version
  --help

Sub-commands:
  config show
  config set <key> <value>
  config set-key <backend>
  config test <backend>
  config wizard
```

---

## 9. Slash command `/transcribe`

`commands/transcribe.md` defines the command. A thin wrapper around `transcribe.py`:

```bash
/transcribe <URL_or_path> [any CLI flags]
```

Examples:
- `/transcribe https://youtu.be/XXX`
- `/transcribe video.mp4 --backend gemini`
- `/transcribe https://youtu.be/XXX --backend whisper-local --model large --language ru`

After it finishes, Claude reads the output automatically and offers analysis / translation / summary (as in the spec).

---

## 10. SKILL.md — triggers and anti-triggers

The skill fires on semantic matching of `description`. So the description has to:

1. Clearly state the goal.
2. Enumerate characteristic trigger phrases in several languages.
3. **Explicitly** list anti-triggers to avoid false positives.

### Positive triggers (sample phrasings in description)

- Direct: "transcribe", "get a transcript", "convert speech to text", and equivalents in other languages.
- Content questions: "what's in this video", "what are they saying".
- Subtitle requests: "make subtitles", ".srt".
- Download + transcribe: "download and transcribe".
- Local files: "transcribe meeting.mp4".
- A bare YouTube link as the only message content.
- Requests to summarise a linked video (the skill transcribes first, then Claude summarises).
- Requests for quotes, timestamps, or translation of a video.
- Engine switching: "via gemini", "locally with whisper", "use subtitles", "via groq".

### Anti-triggers

- A transcript is already in chat — the user asks about the text itself, the skill is not needed.
- Conceptual questions: "what is whisper", "how does transcription work".
- Recommendations for a video without a URL: "suggest a video about X".
- Creating / recording / shooting video.
- Questions about the skill itself: "how do I install", "show me transcribe.py".
- Non-video links in contexts where transcription was clearly not requested.

### Supported platforms (URL)

`yt-dlp` supports 1000+ sites: YouTube, Vimeo, Twitter/X, TikTok, Twitch VOD, SoundCloud, Bilibili, Rutube, etc. By default we try every URL through yt-dlp. If yt-dlp can't handle it — clear error.

---

## 11. YouTube/media downloader (utils/downloader.py)

`yt-dlp` is the main tool. Our wrapper adds:

1. **Auto-update of yt-dlp** on the first run of the day (`yt-dlp -U`). The last-update flag is cached in `~/.neurolearn/state.json`.
2. **Cookies support** via `--cookies-from-browser`, the flag is forwarded from the CLI.
3. **Geobypass** by default: `--geo-bypass`.
4. **Handling of common errors:**
   - 403 / "Sign in to confirm you're not a bot" → hint: "try `--cookies-from-browser chrome`".
   - 401 / age-restricted → hint: "you need cookies from a logged-in account".
   - Region block → hint: "try a VPN or another region".
5. **Optional pytube fallback** — if installed and yt-dlp fails, we try pytube. Pure safety net, not the main mechanism.
6. **Audio-only extraction:** `-x --audio-format mp3 --audio-quality 0`.
7. **Cleanup of the temp file** after transcription (unless `--keep-audio` is set).

---

## 12. Output writer (utils/output_writer.py)

### .txt with timestamps

```
[00:00:00.000 --> 00:00:05.240] Hi, in this video we'll cover…
[00:00:05.240 --> 00:00:09.800] the first thing to understand is…
```

### .txt without timestamps

Flowing text split into paragraphs by heuristic: a new paragraph after a > 2-second pause **or** after ~5 segments.

### .srt

Standard format, 1-based indexing, timestamps `HH:MM:SS,mmm`.

```
1
00:00:00,000 --> 00:00:05,240
Hi, in this video we'll cover…

2
00:00:05,240 --> 00:00:09,800
the first thing to understand is…
```

### File names

`<output-dir>/<sanitised video title>_<date>.txt` (and `.srt`). From special characters we keep only letters/digits/`-`/`_`.

---

## 13. Config and key storage

### `~/.neurolearn/config.toml`

```toml
default_backend = "whisper-local"
fallback_backend = "whisper-local"     # for smart mode

[whisper-local]
model = "turbo"
device = "auto"
compute_type = "auto"
beam_size = 5
vad = true

[gemini]
model = "gemini-2.5-flash"

[groq]
model = "whisper-large-v3-turbo"

[openai]
model = "whisper-1"

[deepgram]
model = "nova-3"

[assemblyai]
model = "best"

[custom]
base_url = ""
model = ""

[output]
language = "auto"
timestamps = true
srt = true
output_dir = "./transcripts"

[behavior]
keep_audio = false
yt_dlp_auto_update = true              # auto-update once a day
cookies_browser = ""                   # "" | "chrome" | "firefox" | "edge"
fast_path_enabled = true               # try subtitles in smart mode
```

### `~/.neurolearn/.env`

```
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=...
DEEPGRAM_API_KEY=...
ASSEMBLYAI_API_KEY=...
CUSTOM_API_KEY=...
```

- Permissions on Unix: `0600`. On Windows — standard user permissions.
- The file is explicitly listed in the skill's `.gitignore` (in case someone tries to commit it).
- The wizard and `config set-key` write here.

### Key loading priority

1. Process environment variables (e.g. `GEMINI_API_KEY=xxx neurolearn ...`).
2. `~/.neurolearn/.env`.
3. If neither — wizard or CLI prints a clear error with instructions.

### Security

- Keys are never printed in logs in full (`--verbose`); masked as `sk-***...XYZ`.
- Not passed to the Claude chat directly — Claude only sees the transcription result.
- If the user asks "show me my key" — we refuse and point them at `.env`.

---

## 14. Documentation (README.md)

Two-layered layout:

### Layer 1 — for the regular user (~50% of the file)

1. **Title and one-line description.**
2. **Demo GIF/screenshot** (later, optional).
3. **Installation** — three recipes (plugin / skill / uv tool), each with a single block of commands for Win/Mac/Linux.
4. **Quick start** — three examples: paste a link, local file, slash command.
5. **What hardware do I need** — table with honest numbers (see below).
6. **Engine management** — how to switch in chat (3 levels) and via the CLI.
7. **Common errors** — yt-dlp 403, no CUDA, key not working, etc.

### Layer 2 — for those who want to dig deeper (~50% of the file)

1. **Architecture** — diagram, what-goes-where-why, how the backends are structured.
2. **Comparison of Whisper models** — turbo / large / medium / small / distil, real WER, VRAM size.
3. **How the cloud backends work** — what is sent, how keys are protected, free tier limits.
4. **Smart mode internals** — engine selection algorithm.
5. **Fine-tuning** — `compute_type`, `beam_size`, `vad`, `--no-fast-path`.
6. **Extending** — how to add your own backend (implement the `Transcriber` interface).
7. **Roadmap** — diarization (`pyannote-audio`), chunking for videos > 2h, auto-summary via Claude/Gemini.

### "What hardware do I need" table

| Hardware | Suitable backend | One hour of video = | Note |
|---|---|---|---|
| Anything (YouTube subtitles available) | `subtitles` | 2–10 sec | Medium quality, instant |
| RTX 4090/4080/5090 (16+ GB) | whisper-local turbo | 30–60 sec | float16, ideal |
| RTX 4070/3080/4060 Ti (12 GB) | whisper-local turbo | 1–2 min | float16 |
| RTX 3060/4060 (8–12 GB) | whisper-local turbo | 2–4 min | float16 |
| RTX 2060 / GTX 1660 Ti (6 GB) | whisper-local turbo | 5–10 min | int8_float16 |
| GTX 1060/1050 Ti (3–6 GB) | whisper-local medium | 15–30 min | On the edge |
| M3 Max / M4 Pro | whisper-local turbo | 30–45 sec | mlx-whisper |
| M2 Pro / M3 / M4 | whisper-local turbo | 1–2 min | mlx-whisper |
| M1 / M2 base (8 GB) | whisper-local turbo | 2–4 min | mlx-whisper |
| CPU only, Ryzen 7 / i7 | whisper-local small | 30–45 min | Very slow |
| Weak hardware overall | `gemini` or `groq` | 30–120 sec | Cloud, needs internet + key |

**Hardware recommendation for the default mode (whisper-local):**
- ✅ Ideal: NVIDIA RTX 30/40/50-series (≥6 GB VRAM) or Apple Silicon M1+.
- 🟡 OK for short videos: GTX 16-series, older RTX 20.
- 🔴 Better to switch to `subtitles` or `gemini`/`groq`: integrated graphics, laptops without a discrete GPU.
- ⛔ Don't install whisper-local: machines with <8 GB RAM. Use cloud backends.

---

## 15. Testing

### Level 1 — unit tests with mocks

- `test_platform_detect.py` — mock `subprocess` and `platform`, verify the engine choice for every OS × GPU combo.
- `test_output_writer.py` — verify .txt format (with/without timestamps) and .srt.
- `test_config.py` — config.toml load/save, env var priority, key masking in logs.
- `test_backends.py` — each backend tested with the external call mocked, check that they correctly implement the interface.

### Level 2 — integration tests

- Smoke test on a short (≤60 sec) public YouTube video for every backend (whisper-local, subtitles; gemini/groq/openai — only when a key is configured in the CI environment).
- Fallback test: yt-dlp catches a specially crafted error → pytube is tried (or a clear error is returned).
- Cookies test: verify the `--cookies-from-browser` flag is forwarded into yt-dlp correctly (without a real call).

### Level 3 — manual final check

- `python transcribe.py --help` — shows every option.
- Run on a test 60-second Russian YouTube video → receive .txt and .srt.
- Run the same video with `--backend subtitles` → instant.
- Run the same video with `--backend gemini` (if a key is set) → comparable result.
- Wizard on a fresh machine (simulate by deleting `~/.neurolearn/`, then run).
- `neurolearn config set backend groq && neurolearn config show` — the change shows up.

---

## 16. What we do NOT do in v1 (out of scope)

- **Diarization** (speaker identification) — `pyannote-audio` is heavy and needs an HF token. Keep as an optional plugin in the roadmap.
- **Chunking for videos > 2 h** — not critical for most backends, but for robustness — a v2 task.
- **Post-processing via a local LLM** (correcting proper nouns, terms) — the user can ask Claude in chat after the transcription.
- **Auto-summary as part of the skill** — not needed; Claude in chat reads the output anyway and offers a summary itself.
- **Web UI** — this skill is pure CLI/chat.
- **Streaming** (live transcription) — that's a different use case altogether.
- **Non-OpenAI-compatible APIs** in the `custom` backend — the provider must speak the OpenAI dialect.

---

## 17. Open questions / risks

1. **mlx-whisper model versions.** Need to verify the current names in the `mlx-community` repo on huggingface — the paths in `MODEL_MAP` may change by implementation time.
2. **YouTube anti-bot updates.** YouTube updates its protection regularly. By release time we may need the PO Token plugin (`bgutil-ytdlp-pot-provider`). The README should mention this.
3. **Gemini Files API limits.** Confirm current file size limits (at the time of writing — 2 GB via Files API), duration (up to 1 hour — stable, longer — there are caveats).
4. **mlx-whisper is not tested at coding time** — the developer is on a Windows machine. Implementation by the official `mlx-whisper` documentation. Final debugging happens with the user on their Mac via git pull → run → feedback → fix. The README's "macOS" section is marked "manually tested on M-series by the owner"; the exact model/macOS version is filled in after the run.
5. **uv availability.** Some corporate Windows machines may forbid downloading binaries. The README needs a pip fallback instruction.

---

## 18. Final checklist (recap for convenience)

- ✅ Default backend: `whisper-local` (offline, private).
- ✅ 8 backends: subtitles, whisper-local, gemini, groq, openai, deepgram, assemblyai, custom + smart composition.
- ✅ First-run wizard with hardware autodetect.
- ✅ Engine switching in chat (per-call / session / persistent).
- ✅ `/transcribe` slash command.
- ✅ Extended multilingual triggers + explicit anti-triggers.
- ✅ yt-dlp safety net: cookies, auto-update, pytube fallback, clear errors.
- ✅ Two-layer README + honest hardware table.
- ✅ Three install methods: plugin / skill / uv tool.
- ✅ Secure key storage: env vars > .env (0600), not in git, masked in logs.
- ✅ Tests: unit + integration + manual final check.

---

## 19. Next steps

After this document is approved:

1. A **detailed implementation plan** is produced via the `superpowers:writing-plans` skill — step by step: what we do first, what next, how we verify each step.
2. Implementation against the plan with regular checkpoints.
3. Final run and validation against the list in section 15.
