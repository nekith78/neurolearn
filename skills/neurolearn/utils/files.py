"""Filesystem operations shared by configuration and comment outputs."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def is_regular_file(path: Path) -> bool:
    """Check the directory entry itself, without following a final symlink."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def read_regular_text(path: Path) -> str:
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise OSError("Expected a regular file.")

    def opener(name: str, flags: int) -> int:
        return os.open(name, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))

    with open(path, encoding="utf-8", opener=opener) as stream:
        # Windows has no O_NOFOLLOW. Check the opened file before reading on every OS.
        if not os.path.samestat(expected, os.fstat(stream.fileno())):
            raise OSError("File changed while opening.")
        return stream.read()


def atomic_write_text(path: Path, content: str) -> None:
    """Replace an entry with a fully written private UTF-8 file."""
    temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                       delete=False, newline="\n")
    try:
        with temp:
            temp.write(content)
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)
