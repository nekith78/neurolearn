#!/usr/bin/env python3
"""Portable Codex launcher for the NeuroLearn CLI inside a plugin install."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def find_plugin_root(start: Path, *, home: Path | None = None) -> Path:
    resolved = start.resolve()
    candidates = []
    configured = os.environ.get("NEUROLEARN_PROJECT_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([resolved.parent, *resolved.parents])
    candidates.append((home or Path.home()) / "youtube-transcribe")
    for candidate in candidates:
        metadata = candidate / "pyproject.toml"
        if metadata.is_file():
            project = tomllib.loads(metadata.read_text(encoding="utf-8"))
            if project.get("project", {}).get("name") == "neurolearn":
                return candidate
    raise RuntimeError(
        "Could not find NeuroLearn project (pyproject.toml missing). "
        "Set NEUROLEARN_PROJECT_DIR to the local source checkout."
    )


def main(argv: list[str] | None = None) -> int:
    if shutil.which("uv") is None:
        print("NeuroLearn requires uv, but uv is not installed or not on PATH.", file=sys.stderr)
        return 127
    root = find_plugin_root(Path(__file__))
    args = list(sys.argv[1:] if argv is None else argv)
    completed = subprocess.run(
        ["uv", "run", "--project", str(root), "neurolearn", *args],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
