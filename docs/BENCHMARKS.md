# Benchmarks

One-run wall-clock measurements of every major neurolearn feature
against fixed reference videos, normalized to per-hour-of-audio rates.
Useful when picking a backend for your audio length.

**Hardware:** macOS Apple Silicon (M-series)
**Network:** residential
**Date:** 2026-05-24, neurolearn v0.15.1 (+ v0.15.2 vision fix)
**Primary test video:** ["Context Management in Claude Code"](https://www.youtube.com/watch?v=eW3oTyfeWZ0) (3:30, 210 s)
**Vision test video:** ["Что такое Python..."](https://www.youtube.com/watch?v=MunPNYumw6M) (5:04, 305 s) — picked because the primary video has no detectable visual moments

## Transcribe — one video

How long to turn a video URL into a `.txt` + `.srt`, and how that scales per hour of audio.

| Backend | Wall time | Per hour of audio | Speed ratio | API key |
|---|---:|---:|---:|---|
| **groq** (whisper-large-v3-turbo) | **11.1 s** | **3.2 min** | **18.9× realtime** | required |
| whisper-local (turbo, mlx) | 20.2 s | 5.8 min | 10.4× realtime | none |
| gemini (3.5-flash) | 21.5 s | 6.2 min | 9.7× realtime | required |

`subtitles` backend was IP-blocked on this video even with cookies registered (see [Known limitations](#known-limitations) below) — not included in the table.

## Transcribe + vision pipeline

`--with-visuals` adds keyframe extraction + (optionally) per-moment vision-LLM annotation. Inside Claude Code, the default is **extract-only** mode: ffmpeg pulls frames, neurolearn writes a `keyframes/manifest.json`, and Claude reads the frames natively in chat. No external vision API call. Outside Claude Code, `--vision-backend groq` is the default — Llama-4-Scout annotates each detected moment.

| Mode | Backend | Wall time | Per hour of audio | Speed ratio | Visual moments |
|---|---|---:|---:|---:|---:|
| `--with-visuals` (Claude-extract) | groq audio + Claude frame reads | 32.4 s¹ | 9.3 min | 6.5× realtime | 0 (no triggers in primary video) |
| `--with-visuals --no-claude-extract` (real vision LLM) | groq audio + Groq Llama-4-Scout vision | 35.5 s² | 7.0 min | 8.6× realtime | 2 moments detected |

¹ On primary test video (3:30). ² On vision test video (5:04) with `--preset standard --detect-method llm_full_pass`.

## Downstream features

Per-video / per-batch, not per-hour (depends on transcript + visual moment count, not audio length).

| Feature | Wall time | Notes |
|---|---:|---|
| `analyze` | 1.6 s | Groq Llama-3.3-70b, single-shot prompt over 1 transcript |
| `report` (PDF, no screenshots) | 1.6 s | Jinja2 + WeasyPrint, 1-page PDF from a 5-min batch |
| `report` (PDF, with screenshots) | 1.6 s | Same time — embedded JPGs are pre-rendered keyframes, no re-encoding |
| `research --limit 2 --no-analyze` | 45.7 s | YouTube search + 2 parallel transcribes via groq |
| `batch --with-visuals --vision-backend groq` | 34.8 s | 1 video + 5 keyframes extracted + 2 vision moments annotated |

## Reading the numbers

- **Speed ratio** = audio duration / wall time. "18.9× realtime" means 1 hour of audio transcribes in 3.2 minutes.
- **Per hour of audio** = linear extrapolation. Network bandwidth dominates cloud backends; CPU/GPU dominates whisper-local. Hardware variance is mostly on whisper-local.
- **First-run cost** for whisper-local includes model load (~5 s on Apple Silicon). Subsequent runs in the same process drop ~5 s. We report the cold-start number — what most users actually see.
- **Vision-LLM mode** is per-detected-moment, not per-frame. A 5-min video that detects 2 moments costs roughly the same as one that detects 1; what scales is the count of triggered moments, not the video length.

## Known limitations surfaced by the benchmark

This benchmark also doubled as a regression check. Five real findings.

### 1. `subtitles` backend can IP-block even with cookies registered

The subtitles backend uses `youtube-transcript-api`, which talks to a different YouTube endpoint than yt-dlp. On some videos / IPs that endpoint blocks anonymous requests with `IpBlocked` even when our cookies file is registered for yt-dlp. **Workaround:** smart cascade auto-falls-back to `groq` — users on `--backend smart` (the default) never see this. Explicit `--backend subtitles` users may need to retry or switch.

### 2. `research` defaults transcribe to gemini, which hits 20-RPD free-tier fast

A `research --limit 2` run on gemini exhausted the daily free quota on the first call, leaving the entire batch as `failed`. **Workaround today:** pass `--backend groq` explicitly (Groq's free tier is 14 400 req/day = 720× more headroom). The transcribe row above uses `--backend groq` after observing this.

**Action item for the project:** flip the `research` transcribe default from `gemini` to `groq`, or at least to `smart`. Tracked for v0.15.2.

### 3. `transcribe --with-visuals --no-claude-extract` crashed on `GroqTokenUsage.cached_tokens` (FIXED here)

When forcing the real Groq vision LLM path (outside Claude Code env), the vision pipeline crashed with `AttributeError: 'GroqTokenUsage' object has no attribute 'cached_tokens'`. The pipeline assumed all vision backends expose a cached-tokens counter; Groq doesn't (it has no prompt cache). **Fix:** `getattr(usage, "cached_tokens", 0)` in `pipeline_v02.py`. Committed alongside this benchmark.

### 4. `report` requires a batch directory with `manifest.json`

Single-video `transcribe` output dirs don't have `manifest.json` — they're per-video, not per-batch. So `report <single_video_dir>` exits with code 3. **Workaround:** use `batch <URL>` (with a single URL) which produces a batch dir, then `report <batch_dir>`. Could be smoother — `report` could synthesize a single-video manifest on the fly. Worth a small UX improvement.

### 5. PDF report sometimes renders "0 sections" when the transcript is short

A 5-min video produces a transcript too short for the outliner LLM to find sectional structure, so the PDF comes out title-only (~10 KB). Real-content batches (longer videos, multi-video batches) produce useful PDFs. This isn't a bug per se — it's the outliner correctly saying "not enough material to subdivide" — but the user-facing message could be clearer.

## How to reproduce

```bash
uv run python qa-out/v0.15.2-benchmarks/run_benchmarks.py
```

Each feature's stdout + stderr is captured in `<feature_dir>/run.log` for debugging.

Full machine-readable results live in `qa-out/v0.15.2-benchmarks/raw_results.json`.
