"""Resolve a YouTube channel URL to a stable channel_id (UC...).

One-time call on `subscribes add` — result is cached in subscribes.toml
so subsequent operations (RSS, etc.) work directly with channel_id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ResolvedChannel:
    url: str          # canonical, trailing-slash stripped
    handle: str | None  # @handle if present in URL
    channel_id: str   # UC...
    title: str | None


def resolve_channel(url: str) -> ResolvedChannel:
    """Return ResolvedChannel for a YouTube channel URL.

    Raises ValueError if the URL doesn't resolve to a real channel.
    """
    canonical = url.rstrip("/")
    handle = _extract_handle(canonical)
    info = _extract_flat(canonical)
    channel_id = info.get("channel_id")
    if not channel_id:
        raise ValueError(f"could not resolve channel_id for {url}")
    return ResolvedChannel(
        url=canonical,
        handle=handle,
        channel_id=channel_id,
        title=info.get("channel") or info.get("uploader"),
    )


def _extract_handle(url: str) -> str | None:
    """Extract @handle from a YouTube URL, if present."""
    m = re.search(r"/(@[\w\-.]+)", url)
    return m.group(1) if m else None


def _extract_flat(url: str) -> dict:
    """yt-dlp wrapper — isolated for tests to mock."""
    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "skip_download": True,
        "playlist_items": "0",  # only metadata, don't enumerate uploads
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}
