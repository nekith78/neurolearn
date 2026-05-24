# Scenario tests (regression replay)

Standalone Python scripts that artificially create bug-triggering
conditions and verify the corresponding fix takes effect on the real
CLI / module entry-points. **Not** discovered by pytest (filename
starts with `run_`, not `test_`) — they're invoked directly when you
want to replay a fix or check a regression.

## When to add a scenario

When a bug + fix lands that has any of:

- A configuration mutation that triggered it (e.g. legacy slot, wrong
  default value) — unit tests won't replay realistic config drift.
- A subprocess / CLI surface that mocks can't fully exercise.
- An env-var-driven branch (`CLAUDE_PLUGIN_ROOT`, `TTY`, etc.).
- A cross-module interaction (config → cookies → subtitles → cascade).

## How to run

```bash
uv run python tests/scenarios/run_v015_fixes.py
```

Each scenario logs to stderr; a Markdown report is regenerated in
`qa-out/v0.15.4-scenario-tests/REPORT.md` every run (qa-out is
gitignored — the report is for local inspection, not for commit).

## Current scenarios

| Script | Covers |
|---|---|
| `run_v015_fixes.py` | All 11 fix scenarios from v0.15.1 - v0.15.4 |

## Convention

- Filename: `run_<release>_<topic>.py` so pytest skips them.
- One self-contained file per release / topic.
- Build the bug condition synthetically (no real API calls where avoidable).
- Capture outcome, write Markdown report.
- Exit code 0 if all pass, 1 otherwise — usable in CI later if we want.
