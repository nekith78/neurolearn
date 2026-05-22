# Claude Code integration

neurolearn ships as a Claude Code plugin and a standalone CLI from the same
codebase. This page covers the Claude-Code-specific UX: slash commands,
chat-driven workflows, and how to switch backends without leaving the chat.

## Install as a plugin

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

The wizard walks through audio backend choice (Groq / Whisper / Gemini /
subtitles), visual backend, and analyze backend. It can also accept keys via
file paths so they never enter the chat (see [Secure key handoff](#secure-key-handoff) below).

To upgrade later: `/plugin update neurolearn` inside Claude Code, then
`uv sync` again.

## Slash command

```
/transcribe https://youtu.be/xyz
```

Paste any supported URL. The plugin picks up your default backend from
`~/.neurolearn/config.toml` and writes the transcript to `./transcripts/`.

## Chat patterns

The plugin lets Claude invoke neurolearn directly. Just paste the URL and tell
Claude what to do:

```
"Transcribe this: https://youtu.be/abc"

"Use gemini for this one: <URL>"

"Run through groq and write a short summary"

"Pull the latest 10 videos from @anthropicai via subtitles and write a topic summary"
```

Claude picks the right `neurolearn` subcommand, runs it, reads the output
(`combined.md` for batches, `.txt`/`.srt` for single videos), and continues the
conversation with the actual content.

The skill itself **does not** produce summaries — that's the LLM's job once the
transcript is ready.

## Switching backends in chat (3 levels)

### Level 1 — per-call

Claude sees an explicit backend mention and uses it for one request:

| Phrase in chat | What happens |
|---|---|
| "transcribe this via gemini: &lt;URL&gt;" | `--backend gemini` for this call |
| "run it through groq" | `--backend groq` |
| "local whisper large" | `--backend whisper-local --whisper-model large` |
| "pull the YouTube subtitles" | `--backend subtitles` |
| "gemini, but pro instead of flash" | `--backend gemini --gemini-model gemini-2.5-pro` |

### Level 2 — per-session

"Use groq for the rest of this conversation" — Claude remembers the choice for
the current session and adds the flag to every subsequent call.

### Level 3 — persistent

Change the default via CLI or from chat:

```bash
neurolearn config set backend groq
neurolearn config set whisper-model turbo
neurolearn config set language ru
```

From chat: "switch the default to groq" → Claude runs
`neurolearn config set backend groq`.

## Secure key handoff

API keys must never be pasted into the chat — chat logs are durable and you
should treat them as written-down-on-paper. For Claude-Code-driven setup, use
the file-handoff form:

1. **You** create a one-line text file with the key on your filesystem (any
   path you choose — Claude only needs to know the path).
2. Tell Claude the path: `the GROQ key is at ~/keys/groq.txt`
3. Claude runs:
   ```bash
   neurolearn config set-key groq --from-file ~/keys/groq.txt
   ```
4. neurolearn reads the file once, stores it at `~/.neurolearn/.env` with mode
   `0600`, then you can delete the temp file.

The positional form `set-key groq <KEY>` exists too but is reserved for the
case when **you** are typing in your own terminal. From chat, always use
`--from-file`.

## Onboarding gate

Until you complete `neurolearn config wizard` (or its non-interactive
equivalent `neurolearn config complete-onboarding`), the work commands —
`transcribe`, `batch`, `analyze`, `research` — exit with code 7 and print a
"please set up first" message.

The only commands that bypass the gate are `whisper-local` and `subtitles`,
which are fully offline and don't need an API key.

If you're driving Claude Code and hit exit code 7: run `/setup` (which kicks
off the wizard) and then re-invoke the original command. Do **not** add
`--backend whisper-local` as a workaround — offline mode is a user choice, not
a way to route around the gate. The gate exists so the user actually picks the
backend they want before transcribing 200 videos with the wrong one.

## Visual mode in Claude Code

When `$CLAUDE_PLUGIN_ROOT` is set (Claude Code session), the visual pipeline
auto-switches to extract-only mode:

1. ffmpeg extracts keyframes from the source video.
2. neurolearn writes `keyframes/manifest.json` listing each frame's timestamp
   and trigger phrase.
3. **Claude reads the frames natively in the chat** — no external vision API
   call, no quota burn.

This works for both `--with-visuals` on a single transcribe and the visual
moments emitted inside `combined.md` for batches.

If you do want Claude to use its API instead of reading frames, you can opt out
with `--no-claude-extract`.

## AI agent reference

If you're an LLM driving this skill (Claude Code, a custom agent, another
chat-based tool), start here:

- [`skills/neurolearn/SKILL.md`](../skills/neurolearn/SKILL.md) — when to invoke, which command to pick, the `--no-analyze` rule for chat-driven use.
- [`docs/agent-reference.md`](agent-reference.md) — full CLI surface, file/module map, exit codes, state semantics.
- [`docs/cookies-walkthrough.md`](cookies-walkthrough.md) — how to fix yt-dlp 403 errors via cookies.
