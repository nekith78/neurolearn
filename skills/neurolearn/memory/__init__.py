"""Memory files — v0.16.0.

Curated knowledge bases that grow over time as you transcribe more
content. Each memory file is a plain Markdown file with a YAML
frontmatter (so it renders directly in Obsidian / Notion / GitHub).

The user-facing flow:
    1. `memory create <name> [--description "..."]`
    2. Transcribe / batch / subscribes / research with `--learn-into <name>`
    3. Tool extracts candidate-new facts vs. existing memory, asks the
       user to approve each, appends approved facts.

Storage: `~/.neurolearn/memories/<name>.md` by default, or
`cfg.memories_dir` if set (e.g. an Obsidian vault).
"""
