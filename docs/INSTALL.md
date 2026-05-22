# Install

## System requirements

- **Python 3.11 or newer**
- **`ffmpeg`** — required for audio extraction
  - macOS: `brew install ffmpeg`
  - Ubuntu / Debian: `apt install ffmpeg`
  - Windows: `choco install ffmpeg` (or `winget install ffmpeg`)
- **macOS 13.5+** for the Apple Silicon path (mlx-whisper)

You'll also need `uv` (recommended) or `pip`. Install `uv`:

```bash
# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

## Install paths

### A — Claude Code plugin via marketplace (recommended)

Inside Claude Code:

```
/plugin marketplace add nekith78/neurolearn
```

```
/plugin install neurolearn@neurolearn
```

Then in your shell:

```bash
uv sync
```

```bash
neurolearn config wizard
```

To upgrade: `/plugin update neurolearn` inside Claude Code, then `uv sync` again.

### B — Claude Code plugin via manual clone

```bash
git clone https://github.com/nekith78/neurolearn ~/.claude/plugins/neurolearn
cd ~/.claude/plugins/neurolearn
uv sync
```

Then `neurolearn config wizard`. Reload Claude Code if needed.

### C — Personal skill folder

```bash
git clone https://github.com/nekith78/neurolearn /tmp/yt-transcribe
cp -r /tmp/yt-transcribe/skills/neurolearn ~/.claude/skills/
cd ~/.claude/skills/neurolearn && uv sync
```

### D — Standalone CLI (no Claude needed)

```bash
uv tool install git+https://github.com/nekith78/neurolearn
```

Or with pip in your own virtualenv:

```bash
pip install git+https://github.com/nekith78/neurolearn
```

## Optional extras

```bash
uv sync --extra instagram       # instaloader fallback for IG profile listing
uv sync --extra diarization     # pyannote.audio for speaker labels (HF token + model license required)
uv sync --extra webui           # Gradio web UI (experimental, hidden)
uv sync --extra ocr             # OCR on keyframes (pytesseract + easyocr)
uv sync --extra report          # PDF generation (weasyprint + jinja2 + markdown)
uv sync --extra dev             # pytest, coverage
```

## First-run setup

```bash
neurolearn config wizard
```

The 3-stage wizard asks for:

1. **Audio backend** — Groq Whisper (recommended, free tier 25 MB caps handled automatically) / local Whisper / Gemini / subtitles
2. **Visual backend** — Groq Llama-4-Scout (default) / Gemini / off
3. **Analyze backend** — same backends, used for `--then-analyze` runs

You'll be asked for API keys for whichever cloud backends you pick. Keys are
stored at `~/.neurolearn/.env` with mode `0600` (Unix).

If you've already set things up by hand and want to skip the wizard while still
unlocking the work commands:

```bash
neurolearn config complete-onboarding
```

## HF_TOKEN warning on first run

You may see:

```
Warning: You are sending unauthenticated requests to the HF Hub.
Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```

`sentence-transformers` (used for trigger-phrase detection) downloads its model
from Hugging Face on first run. Anonymous downloads work fine but with rate
limits. The warning is harmless — it does not stop transcription. Two ways to
silence it:

1. **Ignore** — the model is cached after first run; the warning never affects output.
2. **Register a free token** — make an account at [huggingface.co](https://huggingface.co), Settings → Access Tokens → New token (read-only), then add to `~/.neurolearn/.env`:
   ```
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxx
   ```
