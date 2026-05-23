# Backends

neurolearn ships 8 interchangeable transcription backends behind a single
`Transcriber` Protocol. Pick the one that fits your hardware, privacy
requirements, and budget.

## Overview

| Backend | Speed (1 h of video) | Quality | Cost | API key | Sends data over the network |
|---|---|---|---|---|---|
| `subtitles` | 2–10 s | Mediocre (YouTube ASR) | Free | No | No (only a YouTube request) |
| `whisper-local` | 30 s – 45 min (GPU-dependent) | Excellent | Free | No | No (fully offline) |
| `gemini` | 30–120 s | Excellent | Free (flash) / paid (pro) | `GEMINI_API_KEY` | Yes, Google |
| `groq` | 5–20 s | Excellent | Free tier, then paid | `GROQ_API_KEY` | Yes, Groq |
| `openai` | 30–60 s | Excellent | ~$0.006/min of audio | `OPENAI_API_KEY` | Yes, OpenAI |
| `deepgram` | 15–60 s | Excellent + precise timestamps | $200 free start | `DEEPGRAM_API_KEY` | Yes, Deepgram |
| `assemblyai` | 30–90 s | Excellent | Free tier | `ASSEMBLYAI_API_KEY` | Yes, AssemblyAI |
| `custom` | Depends on provider | Depends | Depends | Configurable | Yes, your provider |

## Smart cascade

`--backend smart` (default) is composition, not a backend:

1. URL is YouTube → try `subtitles`. Success → return.
2. No subtitles / not YouTube / `--no-fast-path` → fall through to `fallback_backend` (default since v0.11: **`groq`**).
3. If `gemini_url_fastpath=true` AND `gemini_model` is whitelisted (`gemini-3.5-flash` family), there's an opt-in Gemini URL middle step before the download+Groq path — saves the audio download for YouTube videos. Off by default.

The logic lives at the top level; backends don't know about each other.

## Groq audio size handling (v0.14.1)

Groq's free tier caps audio uploads at 25 MB. When a video would exceed
that limit neurolearn automatically:

1. **Recompresses to Opus 24 kbps mono at 16 kHz** — Whisper uses 16 kHz
   mono internally anyway, so this is lossless for ASR. ~11 MB per hour.
2. If even the recompressed file is over the limit, **splits into the
   minimum number of chunks** that fit. Cuts land on silence intervals
   detected via `ffmpeg silencedetect` (no mid-word cuts in practice).
3. **Reassembles** timestamps — each chunk's segments are offset by its
   start time so the end-to-end timeline matches the original video.

Effective single-call capacity per tier:

| Tier | Wire limit | Usable limit | Max audio in one upload |
|---|---|---|---|
| free | 25 MB | ~24 MB | ~2h15m of audio |
| paid / paid-tier2 / paid-tier3 | 100 MB | ~98 MB | ~9 hours of audio |

Above those, the chunker kicks in transparently. You never have to think
about it.

## Groq audio hallucination handling (v0.15.1)

Whisper has a well-documented failure mode: on silent or musical
intros/outros, the model fills the gap with text it has seen in
training data (Russian YouTube outros like "Продолжение следует...",
song lyrics from intros it recognises, theme-related word salad like
"Python Python" on a Python tutorial's intro music). The chunker
preserves end-to-end timestamps correctly, so any phantom text shows
up in the .srt at the wrong place.

We mitigate this in **three layers**, all transparent — no flags, no
config:

1. **Silence-edge trim (input-side).** Before sending each chunk to
   Groq, ffmpeg trims leading and trailing silence (> 1.5 s). The
   leading-trim amount is added back to every segment timestamp on
   reassembly so the final timeline still matches the original audio.
   Whisper sees only audio that contains speech, so it has no silent
   gap to invent text on.
2. **Word-variety + density filter (output-side).** Segments with
   `chars_per_second < 2` AND `≤ 2 distinct word stems` are dropped
   as silence-fill artifacts. Real speech with mistimed bounds
   (e.g. a song lyric stretched across an instrumental intro) is
   preserved because it has 5+ distinct stems despite the low cps.
3. **Blocklist.** Whole-segment-match against documented Whisper
   fillers: `Продолжение следует`, `Subscribe to my channel`,
   `(music)`, `(applause)`, etc.

Validated across 5 content formats (music / tech-talk / interview /
news / tutorial) in EN+RU: **0 false positives**, catches all
invented phantoms. We don't depend on Groq's `verbose_json`
confidence fields (`no_speech_prob`, `avg_logprob`, etc.) — empirical
probing showed those aren't discriminative on Groq's deployment.

If you DO need to debug what was dropped, look for the
`[neurolearn] Dropped N hallucinated segment(s)` line in stderr.

## Hardware guide

Pick a backend based on your hardware:

| Hardware | Recommended backend | One hour of video = | Notes |
|---|---|---|---|
| Anything (YouTube subtitles available) | `subtitles` | 2–10 s | Mediocre quality, instant |
| RTX 4090/4080/5090 (16+ GB VRAM) | `whisper-local turbo` | 30–60 s | float16, ideal |
| RTX 4070/3080/4060 Ti (12 GB VRAM) | `whisper-local turbo` | 1–2 min | float16 |
| RTX 3060/4060 (8–12 GB VRAM) | `whisper-local turbo` | 2–4 min | float16 |
| RTX 2060 / GTX 1660 Ti (6 GB VRAM) | `whisper-local turbo` | 5–10 min | int8_float16 |
| GTX 1060/1050 Ti (3–6 GB VRAM) | `whisper-local medium` | 15–30 min | Borderline |
| M3 Max / M4 Pro | `whisper-local turbo` | 30–45 s | mlx-whisper |
| M2 Pro / M3 / M4 | `whisper-local turbo` | 1–2 min | mlx-whisper |
| M1 / M2 base (8 GB) | `whisper-local turbo` | 2–4 min | mlx-whisper |
| CPU only, Ryzen 7 / i7 | `whisper-local small` | 30–45 min | Very slow |
| Weak hardware / no dedicated GPU | `gemini` or `groq` | 30–120 s | Cloud, needs internet + key |

**Quick advice:**

- ✅ Ideal: NVIDIA RTX 30/40/50-series (≥6 GB VRAM) or Apple Silicon M1+.
- 🟡 Fine for short videos: GTX 16-series, older RTX 20-series.
- 🔴 Better to use `subtitles` or `gemini`/`groq`: integrated graphics, laptops without a dedicated GPU.
- ⛔ Avoid `whisper-local`: machines with <8 GB RAM. Use cloud backends.

## Whisper model comparison

| Parameter | `turbo` (default) | `large` | `medium` | `small` | `distil` |
|---|---|---|---|---|---|
| Base model | large-v3-turbo | large-v3 | medium | small | distil-large-v3 |
| VRAM (float16) | ~6 GB | ~10 GB | ~5 GB | ~2 GB | ~6 GB |
| Accuracy | Excellent | Maximum | Good | Mediocre | Excellent (EN) |
| Speed | Fast | Slow | Medium | Very fast | Fastest |
| When to use | Most tasks | Legal / medical recordings | Weak hardware | Drafts | faster-whisper only, EN |
| macOS (mlx) | Yes | Yes | Yes | Yes | No |

## Privacy

| Backend | Does audio leave the machine? |
|---|---|
| `whisper-local` | Never |
| `subtitles` | No — but YouTube sees the request |
| `gemini` | Yes, Google |
| `groq` | Yes, Groq |
| `openai` | Yes, OpenAI |
| `deepgram` | Yes, Deepgram |
| `assemblyai` | Yes, AssemblyAI |
| `custom` | Yes, your provider |

API keys are never printed in full to logs — they're masked as `sk-***...XYZ`.
`config show` masks them too. Keys live in `~/.neurolearn/.env` with mode `0600`
on Unix.
