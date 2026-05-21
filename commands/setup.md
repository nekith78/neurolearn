---
description: |
  Configure neurolearn for first use — walk the user through getting an API key
  and setting up a fast transcription backend. Recommended after `/plugin install`
  before the first `/transcribe` request.
argument-hint: (no arguments — interactive walkthrough)
---

### What this command does

Walks the user through neurolearn's first-time setup so the plugin works fast
and reliably. The headline goal is configuring **one fast cloud audio backend**
(default: Groq Whisper-large-v3-turbo on free tier) so transcription runs in
~12s instead of 100s+ on local whisper.

This command is the dedicated onboarding flow. It is invoked when:
- The user just installed the plugin and asks to set it up.
- A previous `/transcribe` flagged that no API key is configured.
- The user explicitly types `/setup`.

### How to run it

Step 1 — Probe the current state:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Parse the JSON. The fields you need:

- `keys.groq.configured`, `keys.gemini.configured` (booleans)
- `ready.has_fast_audio` (boolean)
- `ready.recommended_setup[]` (list of action items)

Step 2 — Branch based on state:

**Branch A: `ready.has_fast_audio == true`**

Tell the user: "neurolearn is already set up. Configured keys: [list them with
the masked values from `keys.<backend>.masked`]. You're good to transcribe."

If `keys.groq.configured == false` but another fast backend is set, offer:
"You're set up with [X], but Groq is faster and has the most generous free
tier (8h/day, ~12s per video). Want to add a Groq key as a primary?" — if
yes, fall into Branch B for Groq.

**Branch B: `ready.has_fast_audio == false`**

Recommend Groq. Say verbatim or equivalent:

> neurolearn is installed but no fast cloud audio backend is configured.
> I recommend Groq — it's free for 8 hours of audio per day, transcribes a
> 17-minute video in ~12 seconds, and has accurate timestamps. Want me to
> walk you through setting it up?

If yes, the steps to relay to the user are:

1. Open https://console.groq.com/keys in your browser.
2. Sign in (Google login works).
3. Click **Create API Key**, name it `neurolearn`.
4. Copy the key value — starts with `gsk_`.
5. Paste it in this chat, in a normal message.

When the user pastes the key, you register it for them. The key looks like
`gsk_abcd1234...` — strip whitespace, never echo it back in full.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set-key groq <THE_PASTED_KEY>
```

Then set the audio default to Groq via smart cascade. Run BOTH:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set backend smart
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set fallback groq
```

(`fallback groq` alone only kicks in when `backend = smart` — which is
the v0.11+ default, but explicit is safer if the user had an older
config.)

Also enable Groq for vision and analyze (one Groq key covers all three):

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set vision-backend groq
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set analyze-backend groq
```

Step 3 — Verify:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn doctor --json
```

Confirm:
- `ready.has_fast_audio == true`
- `ready.has_fast_vision == true` (auto-true with Groq key)
- `ready.has_analyze_backend == true` (auto-true with Groq key)
- `keys.groq.configured == true`

Tell the user: "Setup complete. You can paste a YouTube URL anytime and I'll
transcribe it. Vision (`--with-visuals`) and analyze are also unlocked
because Groq covers all three stages."

### Branch C — has_fast_audio but missing vision or analyze

If `ready.has_fast_audio == true` BUT one of:
- `ready.has_fast_vision == false`
- `ready.has_analyze_backend == false`

…then the user has a fast audio key but vision/analyze stages will
either skip or fall back to slower paths. Offer to enable them.

Iterate `ready.recommended_setup[]` from `doctor --json` — v0.12.2 adds
entries like `enable-vision` and `upgrade-stale-gemini-audio-model`.
For each entry, relay its `why` to the user and (with consent) run the
exact `command` field.

### Tier hint (paid users)

If the user mentions they're on a paid Gemini or Groq tier (e.g. "I
have Gemini Tier 1"), set that in their config to unlock larger RPD
caps + paid-only model overrides:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set gemini-tier paid
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set groq-tier paid
```

For paid Gemini, also enable the URL fast-path (zero-download audio
for YouTube, only safe with gemini-3.5-flash):

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" neurolearn config set gemini-url-fastpath true
```

Do NOT run `neurolearn config wizard` from chat — it's a TTY-only
interactive flow and will exit 2 in a non-TTY context (v0.12.2+).

### Optional: also configure Gemini

If the user mentions wanting analyze / research / report features that use
an LLM, also offer to set up a Gemini key. Same flow as Groq but URL is
`https://aistudio.google.com/apikey` and the command is
`neurolearn config set-key gemini <KEY>`.

Gemini is NOT recommended for audio transcription — it has a known
timestamp-drift bug on `gemini-2.5-flash` (v0.10.9 finding: stretches
timestamps by +63%, breaking .srt files for navigation). Keep it for
LLM-only features.

### Security notes when handling the user's key

- **Never echo the key back in full.** Always mask after `set-key`: the CLI
  already prints `gsk_***...XXXX`. Don't paste the raw key in your reply.
- **Never write the key to any file other than via `neurolearn config set-key`.**
  That command stores it in `~/.neurolearn/.env` with mode 0600 on Unix.
- **If the user typoed the URL or visited a phishing-looking site**, stop and
  tell them to go to the verified URL above. The real Groq console URL is
  `console.groq.com` (no hyphen, no extra subdomains).

### If something goes wrong

- `set-key` exits non-zero → relay stderr to the user and ask them to re-paste.
- `doctor --json` doesn't show the key as configured even after `set-key` →
  the user's `~/.neurolearn/.env` may have a stale value. Suggest:
  `cat ~/.neurolearn/.env` to inspect, then re-run `set-key` to overwrite.
- The user pastes a key starting with `sk-` (OpenAI) or `AIza` (Gemini)
  instead of `gsk_` (Groq) — recognize the prefix, ask if they meant the
  other provider, and run the appropriate `set-key` if so.
