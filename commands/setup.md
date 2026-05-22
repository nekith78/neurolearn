---
description: |
  Configure neurolearn before any transcription / analysis. v0.13.0:
  this is REQUIRED on first install — neurolearn now refuses to run
  transcribe / batch / analyze / research with `onboarding_complete=false`.
  Walks the user through every backend choice (audio / vision / analyze),
  collects API keys SECURELY via files on disk (NOT chat), and flips
  the gate to True at the end.
argument-hint: (no arguments — interactive walkthrough)
---

### Hard rule (v0.13.0+)

`neurolearn` REFUSES to run transcribe / batch / analyze / research while
`onboarding_complete = false` in `~/.neurolearn/config.toml`, with one
exception: `--backend whisper-local` (offline; no keys needed). The CLI
exits with code 7 and a message pointing here.

**Run this flow on first install BEFORE attempting any transcription.**
Do not auto-pick defaults and proceed; the user gets to choose.

### How to run it

Step 0 — Detect current state:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Parse the JSON. v0.13.1+ exposes the gate signal at
`config.onboarding_complete` (boolean):

- `true` → user has completed setup. Tell them "you're already set up,
  here's the current config" and stop. (`doctor --json` also has
  `config.default_backend`, `config.vision_backend`, etc. for the
  summary.)
- `false` (or field absent on older builds) → continue with this flow.

Alternative inspection — if you want only the gate flag:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config get onboarding-complete --json
```

returns `{"onboarding-complete": true}` or `{"onboarding-complete": false}`.

Step 1 — Pick working mode (CRITICAL — affects later steps):

Ask the user verbatim or equivalent:

> Before I configure neurolearn, two questions about how you want to use it:
>
> **(A) Are you running this through Claude Code (this chat) or
> standalone CLI?**
>   - **Claude Code**: I (Claude) can read transcripts + keyframes
>     directly from disk — no extra API quota burn for analyze/vision.
>     We only need an audio backend (Groq).
>   - **Standalone CLI**: neurolearn calls external APIs for analysis
>     and vision. We need keys for all 3 stages.
>
> **(B) Free-tier or paid-tier user?**
>   - **Free**: I'll recommend Groq (1 key, covers audio + vision +
>     analyze on the free tier with very generous quotas).
>   - **Paid**: you can unlock paid-tier models (gemini-3.5-pro,
>     llama-4-maverick, explicit caching).

Hold their answers in your context for the rest of the flow.

Step 2 — Audio backend:

Recommend `smart` cascade with Groq as the primary fallback. Show the
options:

```
  1) smart            (RECOMMENDED — subtitles → groq → whisper-local)
  2) groq directly    (fastest; same key as the rest)
  3) whisper-local    (offline; no API key)
  4) subtitles        (YouTube-only; instant; no API key)
  5) gemini           (use 3.5-flash; 2.5-flash has +63% timestamp bug)
```

Ask which one. Default to `1`. Whatever the user picks:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set backend <picked>
```

If picked `smart`, also set the fallback (default groq):

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set fallback groq
```

Step 3 — Vision backend (only if user wants `--with-visuals` ever):

Ask: "Do you plan to use visual moment extraction (`--with-visuals`)?"

If no → `config set vision-backend off`.

If yes:
- **Claude Code mode**: explain that we'll use **extract-only mode** —
  neurolearn writes a manifest of keyframes and Claude reads the
  images directly in chat (no API call). This is auto-enabled when
  `${CLAUDE_PLUGIN_ROOT}` is set, so just pick the BACKEND to use
  when running outside Claude Code:
  - `groq` (RECOMMENDED — Llama-4-Scout, 1000 RPD)
  - `gemini` (2.5-flash, 250 RPD; or 3.5-flash on paid)
- **Standalone mode**: same backends, no auto-extract-only.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set vision-backend <picked>
```

Step 4 — Analyze backend:

Ask: "Where should LLM-based analysis (research filter, --then-analyze,
`analyze` command) run?"

- **Claude Code mode**: recommend `skip` — Claude does it in chat from
  combined.md, zero API. (You can still pick a real backend if you want
  the CLI to write `analysis-*.md` files.)
- **Standalone**: recommend `groq` (14,400 RPD free vs Gemini's 20).
- Other choices: `gemini`, `ollama` (local, requires `ollama serve`).

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set analyze-backend <picked>
```

(If user picked `skip`, set `analyze-backend skip` or omit — the wizard
treats empty as "no auto-analyze, defer to chat".)

Step 5 — Tier (paid users only):

If the user said paid in Step 1B:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set gemini-tier paid
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set groq-tier paid
```

Optionally enable Gemini URL fast-path (paid Gemini + 3.5-flash only —
saves the 10-30s yt-dlp download on YouTube videos):

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set gemini-url-fastpath true
```

Step 6 — Collect API keys (SECURE — never paste keys in chat):

For each backend the user picked that needs a key (groq, gemini,
openai, deepgram, assemblyai):

**Tell the user verbatim:**

> Your API key should NEVER go into chat history. Please:
>
> 1. Open https://console.groq.com/keys  (URL for the relevant provider)
> 2. Click **Create API Key** → name it `neurolearn` → copy the value.
> 3. Create a text file on your computer at a path you choose, for
>    example: `~/Desktop/groq-key.txt` (any path works).
> 4. **Paste ONLY the key** into that file — just the key, on one line.
>    Save.
> 5. Tell me the path to the file.

When the user replies with the path:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set-key groq --from-file <PATH>
```

The CLI reads the key, saves it to `~/.neurolearn/.env` (mode 0600),
prints a masked confirmation, and reminds the user to delete the temp
file.

Confirm to the user: "I've registered the key. You can delete the file
now — the key is stored at `~/.neurolearn/.env` with mode 0600. The
key never went through chat."

**Do NOT use:** `config set-key groq <PASTED_KEY>` (positional) when
the key would have to come through chat. Positional / `--from-stdin`
is fine if the user is running the CLI themselves; only `--from-file`
is appropriate when Claude is the one issuing the command.

URLs for each provider:
- Groq:       https://console.groq.com/keys
- Gemini:     https://aistudio.google.com/apikey
- OpenAI:     https://platform.openai.com/api-keys
- Deepgram:   https://console.deepgram.com/
- AssemblyAI: https://www.assemblyai.com/dashboard/signup

Step 7 — Mark onboarding complete:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config complete-onboarding
```

This flips the gate to `True`. Without this, every subsequent
transcribe/batch will hit exit code 7.

Step 8 — Verify:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Confirm:
- `config.onboarding_complete == true`
- `ready.has_fast_audio == true` (if user picked Groq or another cloud
  audio backend)
- `keys.<picked-backend>.configured == true` for each
- `recommended_setup` is empty (or only contains nice-to-have items)

Tell the user verbatim:

> Setup complete. Configured:
>   - audio: <picked>
>   - vision: <picked> (extract-only via Claude Code chat for vision
>     descriptions)
>   - analyze: <picked> (or "Claude reads transcripts in chat" if skipped)
>
> You can paste a YouTube/TikTok/Instagram URL or local file path
> anytime. I'll transcribe it.

### Security checklist (re-iterate this when Claude is in plugin context)

- ❌ Never accept an API key pasted into chat. If the user pastes one
  directly anyway, IMMEDIATELY tell them to revoke that key (it's now
  in chat history). Then walk them through the file-based handoff for
  a fresh key.
- ✅ Use `--from-file <path>` for ALL key registrations through chat.
- ✅ Remind the user to delete the temp file after `set-key` succeeds.
- ❌ Never write the key to any file other than via `neurolearn config
  set-key`. That command stores it in `~/.neurolearn/.env` with mode
  0600 on Unix.
- ❌ Never invoke `neurolearn config wizard` from chat — it's a TTY-only
  interactive flow and will exit with code 2 in a non-TTY context.

### If the user is on Claude Desktop (not Code) and runs into the gate

`/plugin install` works in Claude Desktop too, but the env vars +
filesystem access work the same as Claude Code. The flow above applies
unchanged.

### Recovery from a half-finished setup

If the user aborted partway and `onboarding_complete = false` still:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Read `recommended_setup[]` — it lists exactly what's missing with the
fix command. Resume the flow from the relevant Step.

If they want to bail without finishing, the offline-backend escape
hatch works:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn transcribe <URL> --backend whisper-local
```

That bypasses the gate for one run (no API keys needed).
