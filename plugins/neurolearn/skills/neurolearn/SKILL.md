---
name: "neurolearn"
description: "Transcribe or analyze a YouTube, Instagram, TikTok, or local video; research video topics; follow channels; extract frames; or build NeuroLearn reports from Codex."
---

# NeuroLearn for Codex

Use the NeuroLearn project shipped beside this adapter without relying on a
global installation or Claude-specific environment variables.

## Command launcher

Resolve this skill's directory from its loaded `SKILL.md`, then use the
available Python launcher: `python3` on macOS/Linux, or `python`/`py -3` on
Windows (verify with `which`/`where`). Run:

```bash
python3 <this-skill-directory>/scripts/run_neurolearn.py <subcommand> [flags]
```

The launcher finds the project root (including the personal
`~/youtube-transcribe` checkout when running from Codex's isolated plugin
cache) and executes `uv run --project <root> neurolearn ...` with an argument
list, not a shell string. If the checkout lives elsewhere, set
`NEUROLEARN_PROJECT_DIR` to it.

## Workflow

1. Before the first transcribe, batch, analyze, or research action in a task,
   run `doctor --json` through the launcher, except when the user explicitly
   chose `whisper-local`, `subtitles`, or asked to skip setup for an offline run.
2. If `config.onboarding_complete` is false and no explicit exception above
   applies, invoke the
   `neurolearn-setup` skill, finish setup, then automatically resume the
   original request with the same inputs.
3. For a normal YouTube transcript, use `transcribe <URL>`; the configured
   `smart` backend tries subtitles first and then the configured fallbacks.
4. Report the resulting batch path and read the generated transcript from
   disk when the user asks for content, analysis, or a summary.
5. For visuals, the agent reads extracted frames itself. Use NeuroLearn only
   for deterministic extraction/cropping/rendering steps.

For the full CLI decision tables and feature mechanics, read the canonical
`skills/neurolearn/SKILL.md` and `docs/agent-reference.md` relative to the
actual source checkout found by the launcher (or `NEUROLEARN_PROJECT_DIR`),
including when this adapter is loaded from an isolated plugin cache. If that
checkout cannot be identified, stop the dependent operation and resolve its
location first. Apply these Codex
substitutions while reading them:

- replace `${CLAUDE_PLUGIN_ROOT}` commands with the launcher above;
- replace Claude `/setup` with the `neurolearn-setup` skill;
- treat references to the host agent as Codex;
- keep all backend, quota, security, output, and agent-driven-vision rules.

## Security and boundaries

- Never place API keys in chat or command arguments; use `config set-key
  <backend> --from-file <path>`.
- Do not bypass incomplete onboarding with a backend choice unless the user
  explicitly chose offline/local or subtitles mode.
- Do not modify NeuroLearn core logic merely to make the Codex adapter work.
