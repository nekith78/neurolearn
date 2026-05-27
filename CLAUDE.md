# CLAUDE.md

Instructions for Claude Code (and any other AI agent) working in this
repository.

## Repository state

`neurolearn` is a mature CLI tool: v0.13.0+, ~1184 unit tests
passing, in active use. Shipped commands: `transcribe`, `batch`,
`analyze`, `research`, `subscribes` (YouTube / Instagram / TikTok),
`report` (PDF generation, v0.10.2), `history`, `doctor` (v0.11.0),
`config` group (`show` / `set` / `get` / `set-key` / `complete-onboarding`
/ `wizard` / `test`), `schedule`, `webui` (hidden).

Current architectural headlines:

- **v0.11.0**: default audio = `smart` cascade with Groq as primary
  fallback; `gemini-2.5-flash` audio path BLOCKED (verified +63%
  timestamp drift bug).
- **v0.12.0**: default vision = Groq Llama-4-Scout, with Gemini
  fallback. Anthropic API removed entirely from the codebase.
  Per-model prompts in `vision/data/prompts_default.toml`.
- **v0.12.1**: `$CLAUDE_PLUGIN_ROOT` auto-detection enables
  extract-only vision mode (manifest.json + Claude-in-chat reads frames).
- **v0.13.0**: forced onboarding gate (`Config.onboarding_complete`).
  Work-commands exit 7 until `/setup` or `config wizard` completes.
  Secure key handoff via `config set-key <backend> --from-file <path>`.

The source of truth for behavior is the code. Design documents in
`docs/specs/` and plan documents in `docs/plans/` capture the original
intent at each version boundary but diverge from runtime reality in
places (v0.8 in particular added security migrations, interactive
prompts, and smart-backend fixes that postdate the v0.7 spec).

Start any work by reading recent commits:

```bash
git log --oneline -15
```

Then read the relevant code path, not the spec.

## How to continue work

Standard execution mode is **subagent-driven**: dispatch one fresh
subagent per task, review between tasks. Before starting:

1. `git status` and `git log --oneline -5` — understand where things stand.
2. `uv run pytest -q` — confirm the baseline is green.
3. For first-time setup on a fresh machine, see [`HANDOFF.md`](HANDOFF.md).

## Common commands

```bash
uv sync                            # install base deps
uv sync --extra dev                # + pytest, coverage
uv sync --extra instagram          # + instaloader fallback
uv sync --extra diarization        # + pyannote
uv sync --extra webui              # + gradio
uv sync --extra ocr                # + pytesseract, easyocr
uv sync --extra report             # + weasyprint, jinja2, markdown (PDF reports)

uv run pytest                      # full suite (~25s, ~1184 tests)
uv run pytest tests/test_X.py -v   # one file
uv run pytest -k keyword -v        # filter by keyword
RUN_E2E_SMOKE=1 uv run pytest -v   # enable network-touching e2e

uv run neurolearn --help   # see all commands
```

## Architecture invariants

These are load-bearing — breaking them silently breaks the tool.

**Naming.** The Claude Code plugin / CLI binary is `neurolearn`
(kebab-case). The Python package is `skills/neurolearn/`
(snake_case). Both forms appear in the codebase and docs — use them
by context. **`yt-tr` is not a valid alias** and never was; if you
see it in any doc, fix it to `neurolearn`.

**Cookies are strict file-only (v0.8 security migration).** All paths
that previously accepted `--cookies-from-browser` now require an
explicit Netscape `cookies.txt` file. Rationale: browser-cookie
access reads the entire cookie store into process memory — even on
macOS where Keychain prompts, an "Always Allow" grant silently leaks
all cookies. This is non-negotiable.

- `transcribe` / `batch` — flag is `--cookies-file <path>`
- `subscribes` (IG / TikTok) — register once via
  `subscribes cookies set <platform> <path>`; stored at
  `~/.neurolearn/<platform>-cookies.txt` with mode 0600.

**Backend abstraction.** `backends/base.py` defines `Transcriber`
(Protocol) and `TranscriptionResult` (dataclass). All 8 backends
(`subtitles`, `whisper-local`, `gemini`, `groq`, `openai`, `deepgram`,
`assemblyai`, `custom`) are interchangeable implementations. Tests run
against the interface; SDKs are mocked. To add a backend:
implement `Transcriber` + register in `backends/factory.py::build_backend`.

**`smart` is composition, not a backend.** When `default_backend ==
"smart"`, the v0.12+ flow is: try `subtitles` if the URL is YouTube and
`fast_path_enabled`, otherwise (or on subtitles failure / low quality)
download audio and fall back to `cfg.fallback_backend` (default
**`groq`** since v0.11.0). The smart composer is in
`backends/factory.run_smart`; it's responsible for downloading audio
when the input is a URL because non-subtitles backends call
`Path(audio).exists()` and reject URLs.

v0.12.0+ Gemini URL middle-step is OPT-IN via `gemini_url_fastpath = true`
AND `gemini_model` in the timestamp-safe whitelist (`gemini-3.5-flash`,
`gemini-3-flash-lite`, `gemini-3.1-flash-lite`). Default is `false` —
plain smart cascade does not call Gemini.

**Anthropic API is NOT a backend.** Per memory rule
`feedback_no_anthropic_api`: neurolearn never calls `anthropic` SDK.
Claude integration happens through Claude Code chat (user's Pro/Max
subscription) — we hand over raw data, Claude does analysis. The 8
backends are: `subtitles`, `whisper-local`, `gemini`, `groq`, `openai`,
`deepgram`, `assemblyai`, `custom`. No `claude` choice anywhere.

**Onboarding gate (v0.13.0+).** `Config.onboarding_complete: bool = False`
is the gatekeeper. While `false`, `transcribe`/`batch`/`analyze`/`research`
exit with code **7** and a message pointing at `/setup` or `config
wizard`. Only escapes: `--backend whisper-local` or `--backend subtitles`
(offline; auto-bypass via `allow_offline=True` in
`_require_onboarding_complete`). Flipped to `true` by either the TTY
wizard at end of `run_wizard()`, or explicitly via
`neurolearn config complete-onboarding`. Doctor's JSON exposes the flag
at `config.onboarding_complete` (v0.13.1+) so Claude can read and branch.

**Secure key handoff (v0.13.0+).** Through Claude Code chat, use ONLY
`neurolearn config set-key <backend> --from-file <path>`. The user
manually creates a file with the key on one line and tells Claude the
PATH; the key never enters chat history. The positional form
(`set-key groq <KEY>`) is reserved for users typing in their own
terminal. Per memory rule (the failure mode that motivated v0.13.0):
chat-paste leaves the key in conversation logs.

**Vision pipeline (v0.12+).** Default vision backend is **Groq**
(`vision/groq_vision.GroqVisionBackend`, Llama-4-Scout); Gemini is the
fallback. Inside Claude Code (`$CLAUDE_PLUGIN_ROOT` env var set),
`--with-visuals` auto-enables extract-only mode: ffmpeg pulls keyframes,
`pipeline_v02._write_keyframes_manifest` writes
`<batch>/keyframes/manifest.json`, no external vision API call. Claude
reads frames with native vision in the chat.

**Whisper-local: two physical implementations.** On macOS arm64 we use
`mlx-whisper`; everywhere else `faster-whisper`. The choice is
automatic via `utils/platform_detect.py`. PEP 508 markers gate the
installs:

- `mlx-whisper`: `sys_platform == 'darwin' and platform_machine == 'arm64'`
- `faster-whisper`: `sys_platform != 'darwin' or platform_machine != 'arm64'`

Never `import` either unconditionally — both modules will be absent
on the wrong platform.

**Config and secrets.**
- `~/.neurolearn/config.toml` — settings (TOML, `tomli` to
  read, `tomli-w` to write, `tomlkit` for comment-preserving edits).
- `~/.neurolearn/.env` — API keys, mode 0600 on Unix.
- Load order: process env > `.env` > error with instructions.
- API keys are masked when printed (`sk-***...XYZ`). Never log full keys.

## Cross-OS specifics

The skill is cross-platform: macOS arm64 (mlx-whisper), Windows / Linux
/ Intel-Mac (faster-whisper). Always check that new code works on both
sides. The `.gitattributes` file pins EOL: `*.py *.md *.toml` → LF,
`*.ps1 *.bat *.cmd` → CRLF. Don't override.

`uv.lock` and `.python-version` are deliberately NOT committed — each
platform resolves its own versions.

When suggesting commands to the user, prefer cross-platform forms.
If a feature is OS-specific, say so explicitly.

## Tests

Three levels:

1. **Unit (default)** — fast, mock SDKs and `subprocess`. Should be
   green on any OS without API keys or network. Run by `uv run pytest`.
2. **E2E smoke (opt-in)** — `RUN_E2E_SMOKE=1` flag enables tests that
   hit real YouTube. Don't enable in CI without secrets.
3. **Manual phase regression** — `bash scripts/qa.sh phase8a` etc.
   Wraps end-to-end flows (cookies workflow, subscribes update, etc.)
   into ~12-step assertion lists with user-state restore.

TDD style for new code: failing test → minimal impl → pass → commit.

## Documentation languages

Project docs, code, CLI strings, and agent guides are **English only**.
User chat-language preferences (e.g. Russian) live in the user's own
global rules — outside this repo.

If you find any user-facing string in Russian inside this repo,
migrate it to English. (v0.8 commit `5a1a71b` did the bulk of this;
new strings should land in English from the start.)

## Pre-push contract

Before `git push` to `main`:

1. `uv run pytest` green.
2. For security/IO-touching changes: invoke the global skill
   `git-cross-os`, which runs `code-reviewer` + `security-review`
   sub-agents before push.

## Releasing — version bumps (v0.17.2+)

**Agent responsibility — do this proactively, no reminder needed.**
In this repo the agent commits and pushes its own work. A version bump
is part of that flow: any change that should reach users MUST be
bumped, because Claude Code auto-update reads `version` from
`marketplace.json` on `main` — a functional change pushed without a
bump lands in `main` but never reaches anyone (the client sees "version
unchanged"). So before a release push:

- **Functional change** (feature, bugfix, CLI behavior, prompts) → run
  `bump-my-version` yourself, then push. Don't wait to be asked.
- **Purely internal change** (dev tooling, test edits, internal docs /
  refactor with no user-visible behavior change) → push without a bump.
- **Unsure which** → ask.

The version string lives in 5 places: `pyproject.toml`,
`skills/neurolearn/__init__.py`, and THREE fields across
`.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`
(top-level + nested plugin entry). The plugin manifests drive Claude
Code auto-update — forgetting them ships a release users can't see
(it happened twice before v0.17.2).

**NEVER hand-edit the version in any of those files.** Use
`bump-my-version` (config in `[tool.bumpversion]`, dev dependency):

```bash
uv run bump-my-version bump patch      # 0.17.1 → 0.17.2
uv run bump-my-version bump minor      # 0.17.1 → 0.18.0
uv run bump-my-version bump major      # 0.17.1 → 1.0.0
```

This updates all 5 places, then auto-commits and tags (`vX.Y.Z`).
It refuses to run on a dirty tree (`allow_dirty = false`) — stage or
clean stray `graphify-out/` / `AGENTS.*` edits first. The full release
flow:

1. Land the feature commits.
2. Update `CHANGELOG.md` with the new version section, commit it.
3. `uv run bump-my-version bump <part>` — bumps + commits + tags.
4. `git push && git push --tags`.
5. `gh release create vX.Y.Z …` (memory rule
   `feedback_create_github_releases`).

If a `search` pattern ever stops matching (e.g. JSON layout changes),
verify with `uv run bump-my-version bump patch --dry-run --verbose
--allow-dirty` before trusting it — the two identical `"version"`
fields in `marketplace.json` are anchored by their following line
(`"plugins": [` vs `"source": {`).

**Safety net:** a `pre-push` git hook (`.githooks/pre-push` →
`scripts/check_version_sync.py`) blocks any push where the version is
out of sync across the manifest files. Activate once per clone with
`git config core.hooksPath .githooks` (also in HANDOFF.md). It's
belt-and-suspenders for hand edits that bypass `bump-my-version`;
bypass in a real emergency with `git push --no-verify`.

## Report mode (v0.10.2)

`neurolearn report <batch_dir>` produces a structured PDF from any
transcribed batch. Architecture is parallel to vision prompts from
v0.10.1:

- `skills/neurolearn/report/prompts.py` — TOML loader with global
  prefix + per-type templates + user override
  (`~/.neurolearn/report_prompts.toml`).
- `skills/neurolearn/report/outliner.py` — single-call vs
  hierarchical routing; resilient JSON parsing.
- `skills/neurolearn/report/renderer.py` — Jinja2 HTML + WeasyPrint
  PDF + Pillow downscale (≤1000px, base64 data URIs).
- `skills/neurolearn/report/orchestrator.py` — manifest + SRT →
  outline → PDF glue.

Optional deps via `uv sync --extra report` (weasyprint + jinja2 +
markdown). On macOS the package primes `DYLD_FALLBACK_LIBRARY_PATH`
so `brew install pango cairo` libs are picked up automatically.

## Out of scope (currently — as of v0.13.0)

Chunking videos > 2h, PyPI publication, Web UI revival (Gradio tabs
re-do). These are tracked in README `## Roadmap`; add new requests
there before coding.
