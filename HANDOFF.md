# Handoff guide — picking up work on a new machine

This document captures the current project state and how to resume.
Read it whenever you switch machines or come back after a break.

---

## Current state (2026-05-22)

- **Version:** `v0.13.0+` — shipped: `transcribe`, `batch`, `analyze`,
  `research`, `subscribes` (YouTube + Instagram + TikTok), `history`,
  `report` (PDF), `doctor`, `config` (with `get` / `set` / `set-key` /
  `complete-onboarding` / `wizard`), `schedule`, `webui` (hidden).
  Visual mode (Groq Llama-4-Scout primary, Gemini fallback, plus
  Claude-Code-native extract-only mode via `$CLAUDE_PLUGIN_ROOT`),
  ASR correction, speaker diarization.
- **Tests:** ~1184 passing, 3 skipped.
- **What's documented:**
  - [`README.md`](README.md) — user-facing overview, install,
    quick start, every command with examples.
  - [`CHANGELOG.md`](CHANGELOG.md) — per-version history (read v0.11.0+
    for the Groq/Anthropic-removal/onboarding-gate changes).
  - [`docs/agent-reference.md`](docs/agent-reference.md) — full CLI
    surface, file map, exit codes, invariants for AI agents driving
    the tool.
  - [`CLAUDE.md`](CLAUDE.md) — project-level instructions for Claude
    Code sessions opening this repo.
  - [`commands/setup.md`](commands/setup.md) — `/setup` slash command,
    multi-step forced flow Claude walks the user through on first install.
  - [`commands/transcribe.md`](commands/transcribe.md) — `/transcribe`
    slash command, Step 0 pre-flight gate + secure key handling.

Run `git log --oneline -10` after cloning to see recent work.

---

## First-time setup on macOS Apple Silicon

### Pre-requisites — install once

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh   # reopen terminal afterwards
uv --version   # should print 0.4+
```

### Critical warnings

1. **Python MUST be arm64 native.**
   ```bash
   python3 -c "import platform; print(platform.machine())"
   ```
   Must print `arm64`. If it prints `x86_64`, you're under Rosetta —
   `mlx-whisper` will not work. Fix: `brew install python@3.12` and
   remove any Anaconda Python from your PATH.

2. **macOS 13.5+ required** for `mlx-whisper` wheels.

3. **First Whisper-large run downloads ~600 MB** into
   `~/.cache/huggingface/`. Make sure you have disk space.

### Install the project

```bash
git clone https://github.com/nekith78/neurolearn.git
cd neurolearn      # repo dir name — keep as-is; `cd youtube-transcribe`
                   # works too if you cloned with a custom name
uv sync                          # base install
uv sync --extra dev              # + pytest, coverage
uv sync --extra instagram        # + instaloader (IG profile fallback)
uv sync --extra diarization      # + pyannote.audio (speaker labels)
uv sync --extra webui            # + gradio (experimental UI)
uv sync --extra ocr              # + pytesseract / easyocr
uv sync --extra report           # + weasyprint / jinja2 / markdown (PDF)
```

You can pass multiple `--extra` flags together.

### Activate the version-sync git hook (once per clone)

```bash
git config core.hooksPath .githooks
```

This wires up `.githooks/pre-push`, which blocks a push when the version
string is out of sync across `pyproject.toml`, `skills/neurolearn/__init__.py`,
and the two `.claude-plugin/*.json` manifests — the failure that twice
shipped a release Claude Code auto-update couldn't see. It's a safety net;
the normal path is `uv run bump-my-version bump <part>` (see CLAUDE.md
"Releasing"). The hook is skipped gracefully if no python is on PATH.

### Configure backends (TTY — your own terminal)

```bash
uv run neurolearn config wizard   # interactive 3-stage setup (audio +
                                  # vision + analyze, tier branching);
                                  # marks onboarding_complete=True at end
uv run neurolearn config show     # see current state + masked keys
uv run neurolearn doctor --json   # machine-readable status
```

Or set keys directly (non-interactive):

```bash
uv run neurolearn config set-key groq <KEY_VALUE>       # positional value
uv run neurolearn config set-key groq --from-env GROQ_API_KEY
uv run neurolearn config set-key groq --from-file ~/path/to/key.txt
# Supported backends: groq, gemini, openai, deepgram, assemblyai, custom.
# v0.12.0+: anthropic was REMOVED. Claude integration is via Claude Code
# chat, not via the API SDK.
```

After setting keys directly, mark onboarding done so transcribe / batch /
analyze / research stop refusing to run (v0.13.0 gate):

```bash
uv run neurolearn config complete-onboarding
```

Keys are stored in `~/.neurolearn/.env` with mode 0600.

### Configure backends (Claude Code — through this chat)

Run `/setup` after `/plugin install` — Claude walks the user through
the same multi-step flow, using `config set-key --from-file` for keys
(never paste keys in chat — they persist in conversation logs).
See [`commands/setup.md`](commands/setup.md) for the full procedure.

---

## First-time setup on Windows / Linux

Same as Mac except:

- `ffmpeg` install: `choco install ffmpeg` (Windows), `apt install ffmpeg` (Ubuntu).
- `mlx-whisper` is **not installed** on these platforms — PEP 508 markers
  route to `faster-whisper` instead (CPU or CUDA, depending on hardware).
- Windows: `irm https://astral.sh/uv/install.ps1 | iex` for uv.

---

## Cookies setup (Instagram / TikTok)

Both platforms need cookies for profile listing. Export from your
browser using the "Get cookies.txt LOCALLY" Chrome/Firefox extension,
then:

```bash
uv run neurolearn subscribes cookies set instagram /path/to/ig-cookies.txt
uv run neurolearn subscribes cookies set tiktok    /path/to/tt-cookies.txt
uv run neurolearn subscribes cookies show
```

The file is copied to `~/.neurolearn/<platform>-cookies.txt`
with mode 0600.

**Strict file-only.** We do NOT support `--cookies-from-browser` —
that flag reads the entire browser cookie store into process memory.
Export the specific cookies you want; never grant blanket access.

---

## Common dev tasks

```bash
uv run pytest                              # full test suite (~25s)
uv run pytest tests/test_factory.py -v     # one file
uv run pytest -k smart -v                  # by keyword
bash scripts/qa.sh phase8a                 # manual phase regression
RUN_E2E_SMOKE=1 uv run pytest -v           # include real-network e2e (rare)
```

```bash
uv run neurolearn --help           # see all commands
uv run neurolearn transcribe       # interactive prompt
uv run neurolearn batch            # interactive multi-URL prompt
uv run neurolearn research         # interactive query prompt
```

---

## Architecture invariants — don't break these

1. **Skill name `neurolearn` (kebab); Python package
   `neurolearn` (snake).** Both. Use by context.
2. **Cookies file-only**, never `cookies-from-browser`.
3. **`uv.lock` and `.python-version` are NOT committed** — each
   platform resolves its own.
4. **`mlx-whisper` gated by `sys_platform == 'darwin' and
   platform_machine == 'arm64'`.** `faster-whisper` is the symmetric
   marker. Never `import` them unconditionally.
5. **All user-facing CLI strings in English** (v0.8 migration).
   Comments/docstrings also English.
6. **`smart` backend downloads audio before falling back** (v0.8 fix).
   Non-subtitles backends can't accept URLs.

---

## Working with the spec/plan when something is unclear

Original design: `docs/specs/2026-05-08-neurolearn-design.md`
(v0.1 baseline). v0.2 through v0.8 added features per their own
spec/plan docs in the same directory.

For runtime behavior, prefer reading the code over the spec — v0.8
diverges from v0.1's design in several places (cookies-file-only,
interactive prompts, smart backend download).

---

## Pre-push contract

Before `git push origin main`:
- `uv run pytest` — must be green.
- For features that touch security/IO: invoke the global skill
  `git-cross-os` (it runs `code-reviewer` + `security-review`).
