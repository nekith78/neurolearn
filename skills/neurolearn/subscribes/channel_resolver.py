"""Resolve a channel URL (YouTube / Instagram / TikTok) to a stable identifier.

One-time call on `subscribes add` — result is cached in subscribes.toml so
subsequent operations (RSS / yt-dlp scrape) work directly without re-resolving.

`channel_id` semantics by platform:
  - YouTube: stable `UC...` from yt-dlp metadata (won't change on handle rename)
  - Instagram: the username (URL path segment) — there is no stable internal
    id available without an authenticated API
  - TikTok: the @handle — same constraint as Instagram
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Profile-style URL detectors (NOT post/video URLs).
# YouTube has many channel URL shapes: /@handle, /c/Name, /channel/UC..., /user/...
_YT_CHANNEL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?youtube\.com/"
    r"(?:@[\w\-.]+|c/[\w\-.]+|channel/[\w\-]+|user/[\w\-]+)/?",
    re.IGNORECASE,
)
# Instagram profile: instagram.com/<username>/ — must NOT match /p/, /reel/, /tv/.
_IG_PROFILE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?instagram\.com/"
    r"(?!p/|reel/|reels/|tv/|stories/|explore/)([\w\-.]+)/?",
    re.IGNORECASE,
)
# TikTok profile: tiktok.com/@<username> — must NOT match /video/.
_TT_PROFILE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?tiktok\.com/(@[\w\-.]+)/?$",
    re.IGNORECASE,
)

# v0.16.0: video / post URL detectors. When the user passes one of these
# to `subscribes add`, we resolve the underlying channel via yt-dlp
# instead of refusing. Lets you grab a channel just by pasting any
# random video from it.
_YT_VIDEO_RE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)",
    re.IGNORECASE,
)
_IG_POST_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/",
    re.IGNORECASE,
)
_TT_VIDEO_RE = re.compile(
    r"^(?:https?://)?(?:www\.|vm\.|vt\.)?tiktok\.com/(?:@[\w\-.]+/video/|\w+/?)",
    re.IGNORECASE,
)


def _looks_like_video_url(url: str) -> bool:
    """True when URL is a single video / post URL (not a channel page)."""
    return bool(
        _YT_VIDEO_RE.match(url)
        or _IG_POST_RE.match(url)
        or _TT_VIDEO_RE.match(url)
    )


@dataclass
class ResolvedChannel:
    url: str          # canonical, trailing-slash stripped
    handle: str | None  # @handle if present in URL
    channel_id: str   # UC... for YouTube; username for IG; @handle for TikTok
    title: str | None
    platform: str = "youtube"


def detect_platform(url: str) -> str | None:
    """Return 'youtube' / 'instagram' / 'tiktok' or None if URL not a known channel."""
    if _YT_CHANNEL_RE.match(url):
        return "youtube"
    if _TT_PROFILE_RE.match(url):
        return "tiktok"
    # Instagram regex is the loosest (matches any username), test last so the
    # other two get priority on ambiguous inputs.
    if _IG_PROFILE_RE.match(url):
        return "instagram"
    return None


def resolve_channel(url: str) -> ResolvedChannel:
    """Route to the platform-specific resolver. Raises ValueError if unrecognized.

    v0.16.0: when `url` is a single video / post URL (not a channel
    URL), we ask yt-dlp for the underlying channel URL once and then
    recurse with the resolved channel URL. So users can paste any
    YouTube video (`youtube.com/watch?v=...` / `youtu.be/...` /
    `youtube.com/shorts/...`), IG post / reel, or TikTok video and
    we'll grab the channel from it instead of refusing.
    """
    platform = detect_platform(url)
    if platform is None and _looks_like_video_url(url):
        channel_url = _channel_url_from_video(url)
        if not channel_url:
            raise ValueError(
                f"Could not extract a channel from this video URL: {url}\n"
                f"Try pasting the channel URL directly (e.g. youtube.com/@handle)."
            )
        platform = detect_platform(channel_url)
        if platform is None:
            raise ValueError(
                f"yt-dlp returned a channel URL we couldn't classify: {channel_url}"
            )
        url = channel_url  # recurse via the channel URL we just discovered
    if platform is None:
        raise ValueError(
            f"URL doesn't look like a YouTube / Instagram / TikTok profile, "
            f"channel, or video: {url}"
        )
    if platform == "youtube":
        return _resolve_youtube(url)
    if platform == "instagram":
        return _resolve_instagram(url)
    if platform == "tiktok":
        return _resolve_tiktok(url)
    raise ValueError(f"unsupported platform: {platform}")  # unreachable


def _channel_url_from_video(video_url: str) -> str | None:
    """Use yt-dlp to look up which channel owns a given video URL.
    Returns the canonical channel URL or None when nothing was found.

    yt-dlp's flat extractor sets several channel-pointer fields with
    different reliability across platforms:
      - YouTube: `channel_url` (always present) or `uploader_url`
      - Instagram: `channel_url` or `uploader_url` (= profile URL)
      - TikTok: `uploader_url` (`@handle` form)
    """
    info = _extract_flat(video_url)
    for key in ("channel_url", "uploader_url", "channel"):
        val = info.get(key)
        if val and isinstance(val, str) and val.startswith("http"):
            return val.rstrip("/")
    # TikTok sometimes only gives `uploader` (handle without URL) — build it
    uploader = info.get("uploader") or info.get("channel")
    if uploader and "tiktok" in video_url.lower():
        u = uploader if uploader.startswith("@") else f"@{uploader}"
        return f"https://www.tiktok.com/{u}"
    return None


def _resolve_youtube(url: str) -> ResolvedChannel:
    canonical = url.rstrip("/")
    handle = _extract_handle(canonical)
    info = _extract_flat(canonical)
    channel_id = info.get("channel_id")
    # Some channel pages (observed on shorts-heavy channels whose root tab
    # doesn't populate the usual fields) return the UC... id only in the
    # top-level `id` field, leaving `channel_id` null. On a channel-tab
    # extract `id` IS the canonical channel id, so fall back to it when it
    # has the UC... shape. Without this, such channels can't be added by
    # their /shorts or /watch URL even though the id is right there.
    if not channel_id:
        fallback = info.get("id")
        if isinstance(fallback, str) and fallback.startswith("UC"):
            channel_id = fallback
    if not channel_id:
        raise ValueError(f"could not resolve channel_id for {url}")
    return ResolvedChannel(
        url=canonical,
        handle=handle,
        channel_id=channel_id,
        title=info.get("channel") or info.get("uploader"),
        platform="youtube",
    )


def _resolve_instagram(url: str) -> ResolvedChannel:
    """Instagram has no stable internal id reachable without auth — use the
    username as the identifier. Username changes are the user's problem
    (we error out during `update` and tell them to remove + re-add).
    """
    canonical = url.rstrip("/")
    m = _IG_PROFILE_RE.match(canonical)
    if not m:
        raise ValueError(f"not an Instagram profile URL: {url}")
    username = m.group(1)
    return ResolvedChannel(
        url=canonical,
        handle=f"@{username}",
        channel_id=username,
        title=None,  # would need auth to fetch profile title
        platform="instagram",
    )


def _resolve_tiktok(url: str) -> ResolvedChannel:
    """TikTok @handle is the identifier — no separate internal id is
    reachable without scraping the profile page (which we defer to
    `subscribes update`)."""
    canonical = url.rstrip("/")
    m = _TT_PROFILE_RE.match(canonical)
    if not m:
        raise ValueError(f"not a TikTok profile URL: {url}")
    handle = m.group(1)  # includes the leading @
    return ResolvedChannel(
        url=canonical,
        handle=handle,
        channel_id=handle,
        title=None,
        platform="tiktok",
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
