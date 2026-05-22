# Troubleshooting

## "Sign in to confirm you're not a bot" (yt-dlp 403)

YouTube periodically updates its anti-bot defences, breaking yt-dlp for 1–3
months at a time. **This is not a bug in this tool.** Fix:

1. **Pull the latest yt-dlp:**
   ```bash
   neurolearn update-deps
   ```
2. **Register a cookies file:**
   - Install the "Get cookies.txt LOCALLY" extension in any browser (Chrome / Firefox / Edge / Brave — same Netscape format).
   - Open `youtube.com` (logged in) → click the extension → Export.
   - Then:
     ```bash
     neurolearn config set-cookies ~/Downloads/youtube_cookies.txt
     ```
   After that `transcribe` / `batch` pick up the cookies automatically. You can
   also pass them per-call: `neurolearn transcribe <URL> --cookies-file ~/path/file.txt`.
3. **Still broken?** Open an issue — fixes usually land within a few days.

For step-by-step screenshots see [cookies-walkthrough.md](cookies-walkthrough.md).

### Why not `--cookies-from-browser`?

That yt-dlp flag pulls **every** cookie for every domain from your browser
store into process memory (domain filtering only happens when HTTP requests
are sent). It violates the principle of least privilege. neurolearn supports
ONLY an explicit Netscape `cookies.txt` file.

### Context

YouTube tightens its protection regularly. You may also need the PO Token
plugin (`bgutil-ytdlp-pot-provider`) — watch the
[yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases).

## Missing API key

```
Error: GEMINI_API_KEY not set. Run: neurolearn config set-key gemini
```

Run `neurolearn config set-key <backend>` — it prompts for the key
interactively and stores it in `~/.neurolearn/.env` with mode `0600`.

When running from Claude Code chat, use the file-based form so the key never
enters the conversation:

```bash
neurolearn config set-key groq --from-file /path/to/your/groq-key.txt
```

## Onboarding gate fired (exit code 7)

```
⚠ Setup required (one-time, under a minute).
Run: /setup    (or: neurolearn config wizard)
```

This is the expected behavior on a fresh install. Run the wizard. If you've
configured neurolearn by hand already and just want to clear the gate:

```bash
neurolearn config complete-onboarding
```

The escape valves that don't trigger the gate are `--backend whisper-local` and
`--backend subtitles` — but those are user choices for offline transcription,
not a workaround. Use them only if you actually want fully-offline operation.

## `distil` model on Mac

```
Error (exit code 4): Model 'distil' is not available on Apple Silicon (mlx-whisper).
Use: turbo, large, medium, or small.
```

`distil-large-v3` is implemented only in `faster-whisper` (Windows/Linux). On
Mac use `turbo` — comparable speed.

## Missing `ffmpeg`

```
Error: ffmpeg not found. Install: brew install ffmpeg (Mac) / choco install ffmpeg (Windows)
```

`ffmpeg` is required to extract audio from video before transcription and to
run the Opus recompression + chunking that lets Groq handle videos longer than
2h15m on free tier. Install it from the [INSTALL.md](INSTALL.md#system-requirements)
system requirements.

## CUDA not found / GPU crashes

Switch to CPU mode:

```bash
neurolearn transcribe <URL> --device cpu --compute-type int8
```

Or switch to a different backend: `subtitles` / `gemini` / `groq`.

The full cuBLAS/cuDNN auto-fallback path (v0.10.9+) tries to recover from these
crashes automatically and switches to CPU if NVIDIA libraries are missing, but
verbose mode (`--verbose`) will surface the underlying error.

## No subtitles on `subtitles` backend

For a video without subtitles (auto or manual) in the requested language the
skill returns an error. In smart mode it falls back to `groq` automatically
(v0.11+); pre-v0.11 default was `whisper-local`.

## Audio file too large for Groq

Since v0.14.1 this is handled automatically — neurolearn recompresses to Opus
24 kbps mono and, if the file is still over the tier's upload limit, splits
into the minimum number of silence-aligned chunks. You should never see this
error in normal use.

If you do hit a "still too large" error after recompression, it usually means
ffmpeg isn't on `PATH`. See [Missing `ffmpeg`](#missing-ffmpeg) above.

## Gemini Files API limits

Gemini Files API accepts files up to ~2 GB and videos up to ~1 hour reliably.
For videos > 1 hour use `whisper-local` or `assemblyai`, or use Groq (which
auto-chunks).

## Long videos look like they "hang"

The progress UI shows the active stage, but yt-dlp + ffmpeg + a 2-hour Groq
upload can take 5-15 minutes total for a multi-hour video. Use `--verbose` to
see the raw output if you want to confirm it's still working.

The chunker also logs its progress to stderr — you'll see lines like
`[neurolearn] Uploading chunk 2/3 (20.8 MB, offset 7110.7s)…` even in non-TTY
contexts (Claude Code subprocess, CI, piped run).
