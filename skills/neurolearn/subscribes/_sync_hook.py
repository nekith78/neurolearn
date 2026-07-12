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


def _load():
    global _companion, _loaded
    if _loaded:
        return _companion
    _loaded = True
    try:
        hook = Path.home() / ".neurolearn" / "sync.py"
        if hook.exists():
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
