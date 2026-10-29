"""Construction boundary for embedded yt-dlp clients."""
from __future__ import annotations

from threading import Lock

_CONSTRUCTION_LOCK = Lock()


def create_ytdlp(options: dict):
    """Serialize plugin initialization, leaving metadata/network work parallel.

    yt-dlp's first constructor loads process-global plugins without a lock.
    Concurrent initial constructors can register the same PO provider twice.
    """
    from yt_dlp import YoutubeDL

    with _CONSTRUCTION_LOCK:
        return YoutubeDL(options)
