"""Multi-language YouTube search with a yt-dlp preset-window fallback.

On fallback, when the caller passes a `days` hint, the search URL is built with YouTube's
`sp=...` query parameter — these are YouTube's own "uploaded within last
hour/day/week/month/year" filters. The server does the date filtering, so
results are pre-screened without us paying the full-extract cost.

Two modes:
  • exact preset match (days ∈ {1, 7, 30, 365}) → SP URL + flat extract.
    YouTube guarantees the window, dates aren't needed downstream.
  • non-exact (e.g. days=14, 90) → SP URL with the NEAREST preset UP
    + full extract so `upload_date` is populated → pipeline refines
    to the precise window client-side.

No `days` → plain `ytsearchN:` shortcut, flat extract (fast, no date info).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import quote_plus

import click

from skills.neurolearn import youtube_api
from skills.neurolearn.shared.date_filter import DateWindow, parse_window
from skills.neurolearn.youtube_fallback import fallback_notice_for_run
from skills.neurolearn.utils.downloader import (
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
    statistics: dict[str, int | None] | None = None

    @property
    def view_count(self) -> int | None:
        return self.statistics["view_count"] if self.statistics is not None else None


# Reverse-engineered from YouTube's search UI. Each entry: (days, sp_code).
# Ordered ascending — `_pick_sp_preset` picks the first one that fits.
# The `%3D%3D` is URL-encoded `==`; YouTube accepts both, we keep encoded
# form so the URL can be passed straight to yt-dlp without re-quoting.
_SP_PRESETS: list[tuple[int, str]] = [
    (1,   "EgIIAg%3D%3D"),  # last day
    (7,   "EgIIAw%3D%3D"),  # last week
    (30,  "EgIIBA%3D%3D"),  # last month
    (365, "EgIIBQ%3D%3D"),  # last year
]


def _pick_sp_preset(days: int) -> tuple[str, int] | None:
    """Pick the smallest SP preset ≥ days (round UP). None if days > 1y or ≤ 0."""
    if days <= 0:
        return None
    for preset_days, sp_code in _SP_PRESETS:
        if days <= preset_days:
            return sp_code, preset_days
    return None


def _build_search_url(query: str, sp_code: str | None) -> str:
    """Build YouTube results URL, optionally with the SP date filter."""
    q = quote_plus(query)
    if sp_code:
        return f"https://www.youtube.com/results?search_query={q}&sp={sp_code}"
    return f"https://www.youtube.com/results?search_query={q}"


def fill_missing_statistics(candidates: list[SearchCandidate]) -> None:
    """Enrich RSS or yt-dlp candidates using the quota independent of search."""
    missing = [c for c in candidates if c.statistics is None]
    if not missing:
        return
    try:
        details = youtube_api.fetch_video_details(c.video_id for c in missing)
    except youtube_api.NotConfigured:
        return
    except youtube_api.YouTubeApiError:
        click.echo("View counts are unavailable for some candidates.", err=True)
        return
    for c in missing:
        detail = details.get(c.video_id)
        if detail is not None:
            c.statistics = detail.statistics
            if detail.duration_sec is not None:
                c.duration_sec = detail.duration_sec


def search_multi_language(
    queries: dict[str, str], *, limit: int, days: int | None = None,
    window: DateWindow | None = None, sort_by_views: bool = False, require_view_counts: bool = False,
) -> list[SearchCandidate]:
    """Search each language and keep the first occurrence of each video."""
    if window is None and days and days > 0:
        window = parse_window(days=days, since=None, until=None, now=datetime.now(timezone.utc).date())
    candidates: dict[str, SearchCandidate] = {}
    remaining = iter(queries.items())
    for lang, query in remaining:
        if not query or not query.strip():
            continue
        try:
            videos = youtube_api.search_videos(
                query.strip(), language=lang, limit=limit, window=window,
                sort_by_views=sort_by_views,
            )
        except youtube_api.YouTubeApiError as error:
            fallback_notice_for_run().report(error)
            pending = {lang: query, **dict(remaining)}
            for candidate in _search_yt_dlp(pending, limit=limit, days=days):
                candidates.setdefault(candidate.video_id, candidate)
            if isinstance(error, youtube_api.QuotaExhausted) or (
                (require_view_counts or sort_by_views)
                and not isinstance(error, (youtube_api.NotConfigured, youtube_api.InvalidKey))
            ):
                # The search bucket can be spent while batched video details remain available.
                fill_missing_statistics(list(candidates.values()))
            break
        for video in videos:
            if video.video_id in candidates:
                continue
            candidates[video.video_id] = SearchCandidate(
                video_id=video.video_id, url=_yt_url_from_id(video.video_id),
                title=video.title, channel=video.channel_title,
                duration_sec=video.duration_sec,
                upload_date=video.published_at.date() if video.published_at else None,
                source_language=lang, statistics=video.statistics,
            )
    return list(candidates.values())


def _search_yt_dlp(
    queries: dict[str, str],
    *,
    limit: int,
    days: int | None = None,
) -> list[SearchCandidate]:
    """Issue one yt-dlp search per (lang, query) pair, dedup by video_id.

    `days` enables YouTube's built-in date filter (SP). When it matches an
    exact preset (1/7/30/365), flat extract is used — fast, no dates needed
    because YouTube guarantees the window. Otherwise we round UP to the
    nearest preset and pay for full extract so `upload_date` is populated
    for the caller to refine the window.

    Returns candidates in first-occurrence order. Limit applies per language
    (so up to `limit * len(queries)` videos before dedup).
    """
    sp_info: tuple[str, int] | None = None
    if days is not None and days > 0:
        sp_info = _pick_sp_preset(days)

    # Full extract only when we need precise upload_date for refinement —
    # i.e. the user's window is tighter than the SP preset granularity.
    need_full_extract = sp_info is not None and sp_info[1] != days

    seen: set[str] = set()
    out: list[SearchCandidate] = []
    for lang, query in queries.items():
        if not query or not query.strip():
            continue
        q = query.strip()
        if sp_info is not None:
            url = _build_search_url(q, sp_info[0])
        else:
            url = f"ytsearch{limit}:{q}"

        info = _extract(url, full=need_full_extract, limit=limit)
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


def _extract(url: str, *, full: bool = False, limit: int = 20) -> dict:
    """Thin yt-dlp wrapper — isolated so tests can mock it.

    `full=False` → `extract_flat=True` (fast, no upload_date).
    `full=True`  → `extract_flat=False` (slower; needed for date refinement).
    """
    from skills.neurolearn.utils.ytdlp import create_ytdlp
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": not full,
        "skip_download": True,
        "geo_bypass": True,
        "playlistend": limit,
    }
    with create_ytdlp(opts) as ydl:
        return ydl.extract_info(url, download=False)
