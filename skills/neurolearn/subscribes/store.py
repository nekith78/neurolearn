"""TOML-backed channel list for subscribes — preserves user comments
through CLI mutations via tomlkit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tomlkit

from skills.neurolearn.subscribes._sync_hook import maybe_sync


PLATFORMS = ("youtube", "instagram", "tiktok")

# v0.17: content-source modes for YouTube channels. Ignored for IG/TT
# (no separate /shorts tab there). See docs/specs/v0.17-subscribes-shorts.md.
MODES = ("auto", "videos-only", "shorts-only", "shorts-and-videos")
DEFAULT_MODE = "auto"


def _write_doc(path: Path, doc) -> None:
    """Single write chokepoint for subscribes.toml — every mutation routes through here, so
    the optional local sync hook fires exactly once per write (inert unless the user opted in).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    maybe_sync("on_write", path)


@dataclass
class Channel:
    """One subscribed channel across YouTube / Instagram / TikTok.

    `channel_id` is platform-dependent:
      - YouTube: stable `UC...` resolved once via yt-dlp
      - Instagram: the username (URL is sole stable identifier)
      - TikTok: the @handle (e.g. "@duolingo")
    """
    url: str
    handle: str | None
    channel_id: str | None
    group: str | None
    added: str  # YYYY-MM-DD
    last_seen_video_id: str | None = None
    last_seen_published: str | None = None  # ISO 8601
    # v0.8: which platform. Records loaded from a pre-v0.8 subscribes.toml
    # default to "youtube" for backward compat — see _from_dict.
    platform: str = "youtube"
    # v0.17: content-source mode for YouTube channels. Pre-v0.17 entries
    # without this field default to "auto", which falls back to /shorts
    # when RSS is empty in the requested window. Use `subscribes set-mode`
    # to override per channel.
    mode: str = DEFAULT_MODE


def load_subscribes(path: Path) -> list[Channel]:
    """Load channels from TOML. Returns empty list if file missing."""
    if not path.exists():
        return []
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    raw = doc.get("channels") or []
    return [_from_dict(dict(entry)) for entry in raw]


def save_subscribes(path: Path, channels: list[Channel]) -> None:
    """Write channels to TOML. Overwrites — does NOT preserve comments.

    Use add_channel/remove_channel for incremental edits that preserve comments.
    """
    doc = tomlkit.document()
    arr = tomlkit.aot()
    for c in channels:
        tbl = tomlkit.table()
        for k, v in _to_dict(c).items():
            if v is not None:
                tbl[k] = v
        arr.append(tbl)
    doc["channels"] = arr
    _write_doc(path, doc)


def add_channel(path: Path, channel: Channel) -> None:
    """Add or update a channel by channel_id (or url if id missing).

    Comment-preserving via tomlkit document mutation.
    """
    doc = (
        tomlkit.parse(path.read_text(encoding="utf-8"))
        if path.exists() else tomlkit.document()
    )
    arr = doc.get("channels")
    if arr is None:
        arr = tomlkit.aot()
        doc["channels"] = arr

    key = channel.channel_id or channel.url
    # In-place update if duplicate
    for entry in list(arr):
        existing_key = entry.get("channel_id") or entry.get("url")
        if existing_key == key:
            for k, v in _to_dict(channel).items():
                if v is not None:
                    entry[k] = v
            _write_doc(path, doc)
            return

    tbl = tomlkit.table()
    for k, v in _to_dict(channel).items():
        if v is not None:
            tbl[k] = v
    arr.append(tbl)
    _write_doc(path, doc)


def remove_channel(path: Path, identifier: str) -> bool:
    """Remove channel by handle, url, or channel_id. Returns True if removed."""
    if not path.exists():
        return False
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    arr = doc.get("channels") or []
    for i, entry in enumerate(list(arr)):
        if (entry.get("handle") == identifier or
            entry.get("url") == identifier or
            entry.get("channel_id") == identifier):
            del arr[i]
            _write_doc(path, doc)
            return True
    return False


def find_channel(path: Path, identifier: str) -> Channel | None:
    """Find by handle, url, or channel_id."""
    for c in load_subscribes(path):
        if identifier in (c.handle, c.url, c.channel_id):
            return c
    return None


def _to_dict(c: Channel) -> dict:
    d = {
        "url": c.url,
        "handle": c.handle,
        "channel_id": c.channel_id,
        "group": c.group,
        "added": c.added,
        "last_seen_video_id": c.last_seen_video_id,
        "last_seen_published": c.last_seen_published,
        "platform": c.platform,
    }
    # v0.17: only emit `mode` when non-default so existing files stay clean.
    if c.mode != DEFAULT_MODE:
        d["mode"] = c.mode
    return d


def _from_dict(d: dict) -> Channel:
    # Pre-v0.8 entries have no `platform` key — treat as YouTube (it was
    # the only supported platform back then).
    platform = d.get("platform") or "youtube"
    if platform not in PLATFORMS:
        raise ValueError(
            f"Unknown platform {platform!r}. Expected one of: "
            f"{', '.join(PLATFORMS)}"
        )
    # v0.17: pre-v0.17 entries have no `mode` key — treat as DEFAULT_MODE.
    mode = d.get("mode") or DEFAULT_MODE
    if mode not in MODES:
        raise ValueError(
            f"Unknown mode {mode!r}. Expected one of: {', '.join(MODES)}"
        )
    return Channel(
        url=d.get("url", ""),
        handle=d.get("handle"),
        channel_id=d.get("channel_id"),
        group=d.get("group"),
        added=d.get("added", ""),
        last_seen_video_id=d.get("last_seen_video_id"),
        last_seen_published=d.get("last_seen_published"),
        platform=platform,
        mode=mode,
    )


def update_channel_mode(path: Path, identifier: str, mode: str) -> bool:
    """Set `mode` for an existing channel by handle / url / channel_id.

    Comment-preserving via tomlkit document mutation (mirrors `add_channel`).
    Returns True when the channel was found and updated, False otherwise.
    Raises ValueError on an unknown `mode` value.
    """
    if mode not in MODES:
        raise ValueError(
            f"Unknown mode {mode!r}. Expected one of: {', '.join(MODES)}"
        )
    if not path.exists():
        return False
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    arr = doc.get("channels") or []
    for entry in arr:
        if (entry.get("handle") == identifier
                or entry.get("url") == identifier
                or entry.get("channel_id") == identifier):
            if mode == DEFAULT_MODE:
                # Match the _to_dict convention: don't persist the default.
                if "mode" in entry:
                    del entry["mode"]
            else:
                entry["mode"] = mode
            _write_doc(path, doc)
            return True
    return False
