#!/usr/bin/env python3
"""Pre-push guard: the version string must match across all manifest files.

The version lives in 6 spots (2 in pyproject, 1 in __init__, 1 in
plugin.json, 2 in marketplace.json). They must always agree — a mismatch
means a release where the Claude Code plugin auto-update (which reads
`version` from marketplace.json) disagrees with the package version, and
users silently don't get the update. This happened twice before the
bump-my-version tooling landed; this script is the belt-and-suspenders
guard for the case where someone edits a version by hand and forgets one.

Pure stdlib + regex (no tomllib) so it runs on any python3 ≥ 3.6 without
the project venv — a git hook can't assume `uv` is on PATH.

Exit 0 when all found versions agree (or none found). Exit 1 on mismatch,
printing every spot and its value.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def collect_versions() -> dict[str, str]:
    """Map a human label → version string for every place we pin it."""
    found: dict[str, str] = {}

    pyproject = _read("pyproject.toml")
    # `[project] version` — line starts with `version = ` (multiline ^).
    # `current_version` won't match: it starts with `current_`, not `version`.
    m = re.search(r'(?m)^version = "([^"]+)"', pyproject)
    if m:
        found["pyproject [project].version"] = m.group(1)
    m = re.search(r'(?m)^current_version = "([^"]+)"', pyproject)
    if m:
        found["pyproject [tool.bumpversion].current_version"] = m.group(1)

    m = re.search(
        r'__version__ = "([^"]+)"', _read("skills/neurolearn/__init__.py")
    )
    if m:
        found["skills/neurolearn/__init__.py __version__"] = m.group(1)

    m = re.search(r'"version": "([^"]+)"', _read(".claude-plugin/plugin.json"))
    if m:
        found[".claude-plugin/plugin.json"] = m.group(1)

    # marketplace.json has two "version" fields (top-level + nested plugin).
    mk = re.findall(r'"version": "([^"]+)"', _read(".claude-plugin/marketplace.json"))
    for i, v in enumerate(mk, start=1):
        found[f".claude-plugin/marketplace.json #{i}"] = v

    return found


def main() -> int:
    try:
        found = collect_versions()
    except FileNotFoundError as e:
        # A manifest is missing — don't block the push over an unexpected
        # repo layout; just note it. (Hook is a safety net, not a gate that
        # should ever wedge an otherwise-valid push.)
        print(f"[version-sync] skipped: {e}", file=sys.stderr)
        return 0

    distinct = set(found.values())
    if len(distinct) <= 1:
        return 0  # all agree (or nothing found)

    print(
        "✗ version mismatch across manifest files — push blocked:",
        file=sys.stderr,
    )
    for label, v in found.items():
        print(f"    {v:<12}  ←  {label}", file=sys.stderr)
    print(
        "\nFix with the tooling (updates all spots + commits + tags):\n"
        "    uv run bump-my-version bump patch|minor|major\n"
        "or align the files by hand if this is a partial edit.\n"
        "Bypass (only if you really know why): git push --no-verify",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
