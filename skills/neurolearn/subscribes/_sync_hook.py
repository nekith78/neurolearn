"""Optional local state hook around subscribes read/write — INERT by default.

Ships with neurolearn but does NOTHING for anyone unless BOTH:
  (1) the NEUROLEARN_SYNC environment variable is set, AND
  (2) a `~/.neurolearn/sync.py` module is present on the machine.

neurolearn itself ships no behavior here — it is only a load point for an optional,
user-provided companion (e.g. a personal script that keeps one's own subscribes/triggers
consistent across their own machines). With neither the env var nor the file present it
returns before touching the filesystem, so it is a genuine no-op for every other user and
can never affect a subscribes command.
"""
from __future__ import annotations

import os
from pathlib import Path

_companion = None
_loaded = False


def _safe_perms(p: Path) -> bool:
    """Refuse to execute a companion that anyone but its owner can write. A group/other-writable
    (or non-owned) `~/.neurolearn/sync.py` could be a stray or planted file, which would turn a
    file-write into code execution — so only an owner-only file is trusted. On Windows POSIX
    mode bits don't apply (NTFS ACLs govern), so the check is skipped there — mirrors the
    platform split already used for the 0600 `.env` write.
    """
    try:
        if os.name == "nt":
            return True
        st = p.stat()
        if st.st_uid != os.getuid():
            return False
        return not (st.st_mode & 0o022)   # reject group-write / other-write
    except OSError:
        return False


def _load():
    global _companion, _loaded
    if _loaded:
        return _companion
    _loaded = True
    try:
        hook = Path.home() / ".neurolearn" / "sync.py"
        if hook.exists() and _safe_perms(hook):
            import importlib.util
            spec = importlib.util.spec_from_file_location("_neurolearn_sync_companion", hook)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _companion = mod
    except Exception:
        _companion = None
    return _companion


def maybe_sync(event: str, path=None) -> None:
    """Best-effort call into the optional companion, if installed. Never raises."""
    if not os.environ.get("NEUROLEARN_SYNC"):
        return
    try:
        mod = _load()
        if mod is None:
            return
        fn = getattr(mod, event, None)
        if fn is not None:
            fn(path)
    except Exception:
        pass  # a sync error must never break a subscribes command
