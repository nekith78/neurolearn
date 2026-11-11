---
name: "neurolearn-setup"
description: "Run or re-run the NeuroLearn interactive configuration wizard from Codex, including when doctor reports onboarding incomplete."
---

# NeuroLearn setup for Codex

Run the project's existing wizard; do not recreate its configuration logic in
the skill.

1. Resolve the sibling `../neurolearn/scripts/run_neurolearn.py` launcher and
   use `python3` on macOS/Linux or the available `python`/`py -3` on Windows.
2. Run `python3 <launcher> doctor --json` and summarize the current setup.
3. Run `python3 <launcher> config wizard` in a real TTY and relay each prompt
   in Russian when user input is required. Preserve existing selections unless
   the user chooses a change.
4. Never ask the user to paste a secret into chat. If the wizard needs a new
   key, use a user-created file and `config set-key <backend> --from-file
   <path>` instead.
5. Run `doctor --json` again and require `config.onboarding_complete == true`
   before resuming the original task.

The wizard and `doctor` are the source of truth. Do not hardcode provider
availability or silently switch the user's configured backend.
