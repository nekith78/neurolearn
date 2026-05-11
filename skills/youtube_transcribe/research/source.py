"""Multi-language YouTube search via yt-dlp `ytsearchN:query`.

Issues one yt-dlp search per language, dedups results by video_id,
preserves first-occurrence order. No full extract — flat metadata only
(title, channel, duration, upload_date).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from skills.youtube_transcribe.utils.downloader import (
    parse_yt_date,
    _yt_url_from_id,
)


@dataclass
class SearchCandidate:
    """One video from YouTube search results."""
    video_id: str
    url: str
    title: str | None
    channel: str | None
    duration_sec: int | None
    upload_date: date | None
    source_language: str  # which language produced this result


def search_multi_language(
    queries: dict[str, str],
    *,
    limit: int,
) -> list[SearchCandidate]:
    """Issue one yt-dlp search per (lang, query) pair, dedup by video_id.

    Returns candidates in first-occurrence order. Limit applies per language
    (so up to `limit * len(queries)` videos before dedup).
    """
    seen: set[str] = set()
    out: list[SearchCandidate] = []
    for lang, query in queries.items():
        if not query or not query.strip():
            continue
        info = _extract_flat(f"ytsearch{limit}:{query.strip()}")
        entries = (info or {}).get("entries") or []
        for e in entries[:limit]:
            if not e:
                continue
            vid = e.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(SearchCandidate(
                video_id=vid,
                url=e.get("url") or _yt_url_from_id(vid),
                title=e.get("title"),
                channel=e.get("channel") or e.get("uploader"),
                duration_sec=int(e["duration"]) if e.get("duration") else None,
                upload_date=parse_yt_date(e.get("upload_date")),
                source_language=lang,
            ))
    return out


def _extract_flat(url: str) -> dict:
    """Thin yt-dlp wrapper — isolated so tests can mock it."""
    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "skip_download": True,
        "geo_bypass": True,
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)
