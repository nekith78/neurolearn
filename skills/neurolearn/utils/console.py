"""Cross-platform Rich Console factory.

Reason this exists: on Windows hosts where the active code page is not
UTF-8 (cp1251 on ru-RU locales is the canonical case), Python's stdout
defaults to that codepage. Rich's default Console picks
`LegacyWindowsTerm` and routes writes through `cp1251.encode()`. Any
non-ASCII glyph the CLI prints — `✓`, `✗`, `·`, `→`, box-drawing
characters — blows up with `UnicodeEncodeError: 'charmap' codec can't
encode character '\\u2713'`. The crash happens *after* the actual work
has been done and the transcripts have already been written, so the
user sees a traceback and assumes the tool failed, when in fact the
files are already on disk.

`make_console()` solves this once for every site in the package:

1. On Windows it reconfigures `sys.stdout` / `sys.stderr` to UTF-8 with
   `errors="replace"` (Python 3.7+). This is the safety net — any
   stray glyph in error text gets replaced by `?` instead of crashing.
2. It passes `legacy_windows=False` to Rich so Rich emits ANSI escape
   sequences (not the legacy Win32 API). Modern Windows (conhost
   since Win10 1607, Windows Terminal natively) handles ANSI fine.

The function is a drop-in replacement: every `Console()` call in the
codebase becomes `make_console()`. Tests can patch it module-by-module
exactly like the old direct constructor.
"""
from __future__ import annotations

import sys

from rich.console import Console


def make_console(**kwargs) -> Console:
    """Build a Rich Console that doesn't crash on cp1251 Windows hosts.

    Forwards any extra kwargs to `Console(...)` for callers that want
    record mode, custom width, etc.
    """
    if sys.platform == "win32":
        # Reconfigure stdio once. Idempotent — Python silently ignores a
        # second call with the same args. errors="replace" is the safety
        # net: any unencodable glyph becomes "?" instead of throwing.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                # AttributeError: stream is not a TextIOWrapper (rare —
                # redirected to a non-text stream). ValueError: already
                # configured with a non-default detached buffer. Both
                # mean "leave it alone".
                pass
        # legacy_windows=False forces ANSI mode. Without this, Rich
        # picks the LegacyWindowsTerm path which encodes through the
        # active code page.
        kwargs.setdefault("legacy_windows", False)
    return Console(**kwargs)
