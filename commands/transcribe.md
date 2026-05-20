---
description: |
  Transcribe a YouTube URL, local media file, or run BATCH on a channel/playlist/list.
  Usage — /transcribe <URL_or_path> [flags]   (single)
        — /transcribe batch <inputs...> [--limit N] [flags]   (batch — multiple URLs / channel / playlist / --from-file)
argument-hint: <URL_or_path> | batch <inputs...> [flags]
---

### How to invoke the CLI (v0.10.6+)

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
- **`BackendNotConfigured: GEMINI_API_KEY missing`**: suggest `neurolearn config set-key gemini` or switch to `--backend whisper-local`.
- **Private/unlisted YouTube + Gemini direct URL**: Gemini can only fetch public videos via `file_uri`. Suggest downloading with cookies (`--cookies-file <path>`) or using `--backend smart` for auto-fallback.
- **`command not found: neurolearn`**: see "How to invoke the CLI" above — switch to the `uv run --project "${CLAUDE_PLUGIN_ROOT}"` form, or suggest `uv tool install --from "${CLAUDE_PLUGIN_ROOT}" neurolearn` for a one-time global install.

### Backend default recommendation

If the user didn't specify a backend and pastes a YouTube URL: prefer `--backend smart` (default). It cascades subtitles → Gemini direct URL → download+fallback, costs **1** Gemini API call per video (no vision in v0.10.6+ smart preset), and gracefully handles quota / private / network failures.

**Want visual analysis too?** Add `--with-visuals` (or use `--preset standard / premium / tutorial`). This adds ~1 + N Gemini calls per video, where N is the number of keyframe windows (≈4–6 per minute) — heavy on the free tier (20 calls/day cap).
