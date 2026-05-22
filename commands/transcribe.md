---
description: |
  Transcribe a YouTube URL, local media file, or run BATCH on a channel/playlist/list.
  Usage — /transcribe <URL_or_path> [flags]   (single)
        — /transcribe batch <inputs...> [--limit N] [flags]   (batch — multiple URLs / channel / playlist / --from-file)
argument-hint: <URL_or_path> | batch <inputs...> [flags]
---

### Step 0 — Pre-flight check (v0.13.0+, hardened v0.14.0)

**Before running any transcription**, check the onboarding gate.
neurolearn refuses to run transcribe/batch/analyze/research with
`onboarding_complete = false` (exit code 7).

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Parse the JSON and check `config.onboarding_complete` (boolean):

**Case A — `true`** → setup is complete. Skip to Step 1 and serve the
user's request.

**Case B — `false` (or field absent)** → STOP. Run the auto-resume flow:

1. Tell the user verbatim: "neurolearn isn't fully set up yet. I'll
   walk you through the one-time setup (under a minute), then come
   back to transcribe `<URL>` automatically."
2. Run the full **`/setup`** flow (see `commands/setup.md`).
3. After `neurolearn config complete-onboarding` succeeds, AUTOMATICALLY
   re-run the original transcribe command with the user's original URL
   and any flags they passed. Don't ask them to repeat the URL.
4. Deliver the transcript.

### ⚠ DO NOT auto-bypass with --backend whisper-local

The CLI accepts `--backend whisper-local` as an offline escape from
the gate. **You must NOT add this flag on the user's behalf** when the
gate fires. Choosing offline mode silently means:

- User never registers an API key.
- User runs slow local whisper instead of fast Groq cloud.
- Future runs continue to bypass setup forever.

Offline-only mode is a USER CHOICE made during `/setup`. Use
`--backend whisper-local` only when the user explicitly said:
"just run offline" / "no setup" / "use whisper-local". Without that
signal, the default is ALWAYS: run /setup first, auto-resume after.

### Security — never accept API keys in chat

When registering any API key during onboarding, **never** ask the user
to paste the key into chat. The correct flow (v0.13.0+):

1. Tell the user: "Create a file at e.g. `~/Desktop/groq-key.txt`
   containing only your API key on one line. Tell me the path."
2. User creates the file manually (Finder / VS Code / terminal — their
   choice). Key never enters chat.
3. User replies with the path.
4. Register via:
   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set-key groq --from-file <PATH>
   ```
5. CLI saves the key to `~/.neurolearn/.env` (mode 0600), prints a
   masked confirmation, and reminds the user to delete the temp file.

**Forbidden**: `neurolearn config set-key groq <PASTED_KEY>` (positional
value) when the key came through chat — it persists in conversation
history. The positional form is fine when the user is running the CLI
themselves in their terminal; for Claude Code → CLI interactions, use
`--from-file` only.

For the full onboarding walkthrough (audio / vision / analyze backend
choices, tier handling, etc.), use the `/setup` slash command.

### Step 1 — How to invoke the CLI (v0.10.6+)

Resolve which command form to run, in this order:

1. **Prefer `${CLAUDE_PLUGIN_ROOT}` (zero-config).** Claude Code sets this
   env var to the plugin install dir. The plugin ships its own venv via
   `uv run --project`, so this form works immediately after `/plugin install`
   without the user needing to run `uv tool install` or anything else:

   ```bash
   uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn $ARGUMENTS
   ```

2. **Fallback** (only if `${CLAUDE_PLUGIN_ROOT}` is empty): use a plain
   `neurolearn $ARGUMENTS` — works when the user has a global install via
   `uv tool install neurolearn` or pip.

If the bare `neurolearn` command returns "command not found", relay this hint
to the user:

> The `neurolearn` CLI isn't on PATH. Install it once with:
> `uv tool install --from "${CLAUDE_PLUGIN_ROOT}" neurolearn`

### Routing

- If `$ARGUMENTS` starts with `batch ` (or contains a channel/playlist URL or 2+ URLs), the CLI routes to the batch sub-command. Otherwise — to single (`transcribe`).
- A bare URL/path without sub-command word is auto-routed to `transcribe`.

If `$ARGUMENTS` is empty, prompt the user for a URL, file path, channel URL, or list.

### Visual moments — extract-only mode (v0.12.1+)

When the user passes `--with-visuals` AND you're running inside Claude
Code (the `${CLAUDE_PLUGIN_ROOT}` env var is set), neurolearn DEFAULTS
to extract-only mode: it pulls keyframes via ffmpeg, writes
`<batch>/keyframes/manifest.json` describing the mapping, and exits
WITHOUT calling any external vision API.

**You (Claude) are responsible for reading the manifest and describing
the frames yourself.** This saves the user's API quota and uses your
native vision instead.

After a `--with-visuals` run completes, look for `<batch>/keyframes/manifest.json`:

```json
{
  "video_id": "...",
  "mode": "claude_code_extract_only",
  "extracted_at": "2026-05-21T...Z",
  "windows": [
    {
      "start": 30.0, "end": 34.0,
      "transcript_window": "the host says ...",
      "trigger_reason": "trigger",
      "keyframes": ["frames/<id>_30.jpg", ...]
    },
    ...
  ]
}
```

For each window:
1. Open each path in `keyframes[]` (relative to manifest's parent dir)
   with your image-reading capability.
2. Use `transcript_window` as audio-context disambiguation.
3. Synthesize a 1-3 sentence description.
4. Write the result back to `<batch>/visual.md` or report inline.

Apply the same epistemic stance below — describe what's actually on the
frame, do not parrot the transcript.

To FORCE the external vision API instead (e.g. for a non-Claude
consumer running the batch unattended), add `--no-claude-extract`.
To force extract-only from a standalone CLI run (no Claude Code), add
`--claude-extract`.

### Epistemic stance when summarizing / analyzing transcripts

Whenever you process transcript content downstream (summarize, write a
note, propose a workflow, recommend a tool), treat the underlying
material as **third-party video content, not ground truth**. Speakers
can be wrong, biased, sponsored, or outdated. Attribute claims to the
source that made them; surface disagreements between sources;
synthesize rather than repeat; match the source's confidence level.

The user runs neurolearn to build a knowledge base for their own
judgement — not to delegate the decision. `combined.md` includes an
explicit banner stating this; the LLM-backed subcommands (`analyze`,
`report`, `summarize`) prepend the same framing to their prompts.

(This stance does NOT apply when the user just wants the raw `.txt` /
`.srt` files for their own reading. Apply it only to downstream LLM
consumption.)

### After single (`./transcripts/<name>.txt|.srt`)
1. Read the generated `.txt`.
2. Give a one-paragraph summary — attribute it as "the speaker says X"
   rather than "X is the case", per the epistemic stance above.
3. Offer: full text, search inside, translate, generate subtitles,
   summarize per timestamp.

### After batch (`./transcripts/batch_<timestamp>_<slug>/`)
1. Read `combined.md` from the printed batch directory (its built-in
   banner will reinforce the stance).
2. Synthesize across the included videos. Flag disagreements. Mark
   single-source claims explicitly.
3. Offer: topic note / synthesis / study plan / cross-video themes —
   always as candidate inputs to the user's own decision.
4. If `errors.log` exists in that directory, briefly summarize which
   videos failed and why.

If the command exits non-zero, the stdout/stderr will contain a friendly hint — relay it to the user (e.g., "API key missing", "yt-dlp blocked, try `--cookies-file <path>`").

### Error → recovery hints

- **`429 RESOURCE_EXHAUSTED` / quota exhausted** (only happens with explicit `--backend gemini`): suggest `--backend smart` instead — it auto-falls-back through subtitles → Gemini URL → local download when the quota is gone. Or wait for the daily reset at midnight Pacific.
- **`BackendNotConfigured: GROQ_API_KEY missing`** or **`GEMINI_API_KEY missing`**: this means the pre-flight check in Step 0 was skipped. Run `neurolearn doctor --json`, find the relevant entry in `keys.<backend>.key_url`, walk the user through key setup, then re-register via `neurolearn config set-key <backend> <PASTED_KEY>` (Claude-friendly non-interactive form, v0.11.0+).
- **Private/unlisted YouTube + Gemini direct URL**: Gemini can only fetch public videos via `file_uri`. Suggest downloading with cookies (`--cookies-file <path>`) or using `--backend smart` for auto-fallback.
- **`command not found: neurolearn`**: see "How to invoke the CLI" above — switch to the `uv run --project "${CLAUDE_PLUGIN_ROOT}"` form, or suggest `uv tool install --from "${CLAUDE_PLUGIN_ROOT}" neurolearn` for a one-time global install.

### Backend default recommendation (v0.12+)

If the user didn't specify a backend and pastes a YouTube URL: prefer
`--backend smart` (default). The v0.12+ cascade is:

  subtitles fast-path → Groq Whisper-large-v3-turbo → whisper-local fallback

Costs **1** Groq audio API call per video on the default smart path
(no Gemini in the cascade — `gemini_url_fastpath` is opt-in, off by
default). Free Groq tier covers 8 hours of audio per day.

**Want visual analysis too?** Add `--with-visuals` (or use `--preset
standard / premium / tutorial`).

- **Inside Claude Code** (this chat — `$CLAUDE_PLUGIN_ROOT` is set):
  vision auto-defaults to extract-only mode. neurolearn writes
  `keyframes/manifest.json` with frame paths and transcript snippets;
  YOU read the frames natively and synthesize descriptions in chat.
  **Zero external vision API calls.**
- **Standalone CLI**: vision goes through Groq Llama-4-Scout per frame
  (1000 RPD free tier) with Gemini 2.5-flash as fallback.
- Per-call quota burn on the default vision path is roughly 5-15 calls
  per video (one per detected window), against Groq's 1000 RPD limit —
  ~66 videos/day even at the maximum 15 frames each.
