# Architecture

For developers and contributors. Routine users don't need this page.

## Project layout

```
neurolearn/
├── .claude-plugin/
│   └── plugin.json                       # Claude Code plugin metadata
├── skills/
│   └── neurolearn/                       # Python package (snake_case)
│       ├── SKILL.md                      # Triggers + rules for Claude
│       ├── transcribe.py                 # CLI entry point
│       ├── wizard.py                     # First-run setup wizard
│       ├── config.py                     # config.toml + .env
│       ├── backends/
│       │   ├── base.py                   # Transcriber Protocol + TranscriptionResult
│       │   ├── factory.py                # build_backend + run_smart composition
│       │   ├── subtitles.py
│       │   ├── whisper_local.py          # faster-whisper / mlx-whisper
│       │   ├── gemini.py
│       │   ├── groq.py
│       │   ├── openai_api.py
│       │   ├── deepgram.py
│       │   ├── assemblyai.py
│       │   └── custom.py
│       ├── utils/
│       │   ├── audio_chunker.py          # v0.14.1: silence-aligned chunking
│       │   ├── platform_detect.py        # OS/GPU/VRAM auto-detection
│       │   ├── downloader.py             # yt-dlp wrapper
│       │   └── output_writer.py          # .txt + .srt
│       ├── vision/                       # vision pipeline (v0.10+)
│       ├── analyze/                      # free-form LLM over transcripts (v0.6+)
│       ├── research/                     # discover videos by topic (v0.7+)
│       ├── subscribes/                   # channel watch + RSS (v0.7+)
│       └── report/                       # PDF generation (v0.10.2+)
├── commands/
│   ├── transcribe.md                     # /transcribe slash command
│   └── setup.md                          # /setup slash command
├── tests/
└── pyproject.toml
```

## Transcriber Protocol

`backends/base.py` defines the contract every backend implements:

```python
class Transcriber(Protocol):
    name: str
    supports_url: bool          # subtitles — yes, others go through the downloader
    supports_local_file: bool

    def is_configured(self) -> tuple[bool, str | None]:
        """Is the backend ready? Returns (ok, reason_if_not)."""

    def transcribe(
        self, audio_path: Path | str, *, language: str, **opts
    ) -> TranscriptionResult:
        ...

@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]        # for .srt and timestamped .txt
    language_detected: str | None
    backend_name: str
    duration_seconds: float
```

All 8 backends are interchangeable implementations. Tests run against the
interface; external SDKs are mocked.

## Smart mode — composition, not a backend

When `default_backend == "smart"` (v0.11+), `backends/factory.run_smart`
orchestrates:

1. URL is YouTube? → try `subtitles`.
2. Success → return the result.
3. No subtitles / not YouTube / `--no-fast-path` → use `fallback_backend`
   (default since v0.11: **`groq`**; pre-v0.11 default was `whisper-local`).
4. If `gemini_url_fastpath=true` AND `gemini_model` is whitelisted
   (`gemini-3.5-flash` family), there's an opt-in Gemini URL middle step
   before the download+Groq path — saves the audio download for YouTube
   videos. Off by default.

The logic lives at the top level; backends don't know about each other.

## Whisper-local — two implementations, one interface

`utils/platform_detect.py` inspects the environment and returns `label` /
`backend_impl` / `device` / `vram`. `whisper_local.py` uses the result to pick:

- macOS arm64 → `mlx-whisper`
- Windows / Linux + NVIDIA → `faster-whisper` (float16 or int8_float16 depending on VRAM)
- CPU only → `faster-whisper` with `device="cpu"`, `compute_type="int8"`

The two implementations differ in install: `mlx-whisper` is gated by a PEP 508
marker so it only installs on Apple Silicon, `faster-whisper` is gated to
everywhere else. Importing either unconditionally will fail on the other
platform.

## Groq size handling (v0.14.1)

`backends/groq.py` + `utils/audio_chunker.py` handle Groq's 25 MB free-tier
upload limit transparently:

1. `GroqBackend._prepare_uploads(audio)` returns `list[(path, start_offset_sec)]`:
   - File already under the tier limit → `[(audio, 0.0)]`, no temp file.
   - Over limit → recompress to Opus 24 kbps mono at 16 kHz. Lossless for ASR.
   - Recompressed still over limit → call into the chunker.
2. `audio_chunker.prepare_chunks(opus_audio, limit)`:
   - Compute minimum N chunks that fit the limit.
   - `ffmpeg silencedetect` to find silent intervals (< -30 dB, ≥ 0.4 s).
   - For each ideal cut point, snap to nearest silence in a progressively
     widening window (5% → 50% of segment width).
   - Split with `ffmpeg -c copy` (stream copy — no re-encode, preserves the
     size budget).
3. `GroqBackend.transcribe` uploads each chunk separately. Each chunk's
   segments are offset by its start time before merging. End-to-end timeline
   matches the source.
4. Tier-aware limits: `cfg.groq_tier` ∈ `{"free", "paid", "paid-tier2",
   "paid-tier3"}`. Unknown tier strings fall back to free, so typos can't
   silently enable a 100 MB upload that 413s on the wire.

## Config and secrets

- `~/.neurolearn/config.toml` — settings (TOML; `tomli` to read, `tomlkit`
  for comment-preserving edits).
- `~/.neurolearn/.env` — API keys, mode `0600` on Unix.
- Load priority: process env > `.env` > error with instructions.
- Keys are masked everywhere they're printed (`sk-***...XYZ`). Never log full keys.

## Onboarding gate (v0.13.0+)

`Config.onboarding_complete: bool = False` is the gatekeeper. While `false`,
`transcribe` / `batch` / `analyze` / `research` exit with code 7 and point at
`/setup` or `config wizard`. Only escape valves: `--backend whisper-local` or
`--backend subtitles` (fully offline; auto-bypass via `allow_offline=True` in
`_require_onboarding_complete`).

Flipped to `true` by either the TTY wizard at end of `run_wizard()`, or
explicitly via `neurolearn config complete-onboarding`. Doctor's JSON exposes
the flag at `config.onboarding_complete`.

## Cross-OS specifics

- macOS arm64 → mlx-whisper; everywhere else → faster-whisper. Choice automatic.
- `.gitattributes` pins EOL: `*.py *.md *.toml` → LF, `*.ps1 *.bat *.cmd` → CRLF.
- `uv.lock` and `.python-version` are deliberately NOT committed — each platform resolves its own versions.

## Adding a new backend

1. Create `skills/neurolearn/backends/my_provider.py`.
2. Implement the `Transcriber` Protocol (see `backends/base.py`).
3. Register it in `backends/factory.py::build_backend`:
   ```python
   if name == "my-provider":
       return MyProviderBackend(model=cfg.my_provider_model)
   ```
4. Add to the `--backend` choices in `transcribe.py` and `batch.py`.
5. Write a unit test with a mocked SDK in `tests/test_backend_my_provider.py`.

That's it. The rest of the code (smart mode, output writer, config, CLI)
doesn't change.

## Tests

Three levels:

1. **Unit (default)** — fast, mock SDKs and `subprocess`. Should be green on
   any OS without API keys or network. Run: `uv run pytest`.
2. **E2E smoke (opt-in)** — `RUN_E2E_SMOKE=1` flag enables tests that hit real
   YouTube. Don't enable in CI without secrets.
3. **Manual phase regression** — `bash scripts/qa.sh phase8a` etc. Wraps
   end-to-end flows into ~12-step assertion lists with user-state restore.

TDD style for new code: failing test → minimal impl → pass → commit.

## Documentation language

All project docs, code, CLI strings, and agent guides are **English only**.
User chat-language preferences live in user-side global rules — outside this
repo.

## Pre-push contract

Before `git push` to `main`:

1. `uv run pytest` green.
2. For security / IO-touching changes: invoke the global skill `git-cross-os`,
   which runs `code-reviewer` + `security-review` sub-agents before push.
