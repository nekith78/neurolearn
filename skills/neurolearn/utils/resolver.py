"""Convert any user input (URL / channel / playlist / file / local path)
into a flat list of ResolvedTarget. Does NOT download media."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, parse_qs, urlsplit

import click

from skills.neurolearn import youtube_api
from skills.neurolearn.youtube_fallback import fallback_notice_for_run


# Probe yt-dlp metadata in parallel for batched URLs. yt-dlp init is
# ~1-2s per process; on `batch --from-file urls.txt` with 10 URLs that
# can save 10-20s of sequential probe overhead. Cap conservatively to
# avoid hitting per-IP rate limits or saturating the network.
_MAX_PROBE_WORKERS = 4

from skills.neurolearn.utils.downloader import (
    ChannelEntry,
    expand_channel_or_playlist,
    extract_youtube_video_id,
    is_url,
    is_youtube_url,
    normalize_youtube_channel_url,
    probe_input,
)


_YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com"}


Source = Literal["inline", "file", "channel", "playlist", "single", "search"]


@dataclass
class ResolvedTarget:
    url: str
    title: str | None
    upload_date: date | None
    duration_sec: int | None
    channel: str | None
    source: Source
    video_id: str | None       # for dedup; None for non-YouTube sources
    # Optional: which language search produced this target (multi-lang research).
    # Set by research.pipeline when converting SearchCandidate → ResolvedTarget;
    # None for everything else. Lands in manifest.json for downstream filtering.
    source_language: str | None = None
    is_short: bool | None = None  # Known for typed YouTube upload playlists.
    statistics: dict[str, int | None] | None = None


@dataclass
class ResolverFilters:
    limit: int = 10
    since: date | None = None
    until: date | None = None
    min_duration_sec: int | None = None
    max_duration_sec: int | None = None
    include_shorts: bool = True
    # v0.3 #4: search-by-tags. When set, resolve() runs a YouTube search
    # via yt-dlp `ytsearchN:query` instead of (or in addition to) `inputs`.
    search_query: str | None = None


class CLIInputError(Exception):
    """Hard input error: empty input, missing --from-file, etc. → CLI exit 2."""


class UnresolvableInput(Exception):
    """yt-dlp couldn't resolve one of the inline URLs (private/removed/blocked).
    Kept for backward-compat reference; no longer raised by resolve()."""


@dataclass
class ResolveFailure:
    """A per-URL probe failure — spec extension §5 collect-and-continue."""
    url: str
    error: str      # str(exception) or human description
    source: Source  # "inline" or "file"


def parse_from_file(path: Path) -> list[str]:
    """Parse `--from-file` urls.txt: 1 URL per line, # = comment, blanks ignored.
    Trailing inline comments after URL also stripped."""
    if not path.exists():
        raise CLIInputError(f"File not found: {path}")
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # strip trailing inline comments: split on " #"
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        if line:
            urls.append(line)
    return urls


def _channel_entry_to_target(e: ChannelEntry, source: Source, *, is_short: bool | None = None) -> ResolvedTarget:
    return ResolvedTarget(
        url=e.url,
        title=e.title,
        upload_date=e.upload_date,
        duration_sec=e.duration_sec,
        channel=e.channel,
        source=source,
        video_id=e.video_id, is_short=is_short,
    )


def _video_info_to_target(info: dict, url: str, source: Source) -> ResolvedTarget:
    from skills.neurolearn.utils.downloader import parse_yt_date
    return ResolvedTarget(
        url=url,
        title=info.get("title"),
        upload_date=parse_yt_date(info.get("upload_date")),
        duration_sec=int(info["duration"]) if info.get("duration") else None,
        channel=info.get("channel") or info.get("uploader"),
        source=source,
        video_id=info.get("id") or (extract_youtube_video_id(url) if is_youtube_url(url) else None),
    )


def _single_youtube_video_id(url: str) -> str | None:
    """The id of a single-video link; a link that also names a playlist is a playlist."""
    if not is_url(url) or parse_qs(urlsplit(url).query).get("list"):
        return None
    return extract_youtube_video_id(url)


def _youtube_single_videos(urls: list[str], fallback) -> dict[str, youtube_api.VideoDetails]:
    """Look up every single-video link in one batched request.

    Links missing from the result (no key, failed lookup, private or
    deleted video, a stream with no duration yet) are left to the yt-dlp
    probe.
    """
    ids = {url: video_id for url in urls if (video_id := _single_youtube_video_id(url))}
    if not ids:
        return {}
    try:
        details = youtube_api.fetch_video_details(ids.values())
    except youtube_api.NotConfigured:
        return {}  # Single links never needed a key; stay silent without one.
    except youtube_api.YouTubeApiError as exc:
        fallback.report(exc)
        return {}
    return {url: details[video_id] for url, video_id in ids.items()
            if video_id in details and details[video_id].duration_sec}


def _video_details_to_target(detail: youtube_api.VideoDetails, url: str, source: Source) -> ResolvedTarget:
    return ResolvedTarget(
        url=url, title=detail.title,
        upload_date=detail.published_at.date() if detail.published_at else None,
        duration_sec=detail.duration_sec, channel=detail.channel_title, source=source,
        video_id=detail.video_id, statistics=detail.statistics,
    )


def _local_to_target(path_str: str) -> ResolvedTarget:
    return ResolvedTarget(
        url=path_str, title=None, upload_date=None, duration_sec=None,
        channel=None, source="single", video_id=None,
    )


def _youtube_channel_tab(parsed: SplitResult) -> youtube_api.PublicationType | None:
    if parsed.hostname not in _YOUTUBE_HOSTS:
        return None
    parts = parsed.path.strip("/").split("/")
    if ((len(parts) == 2 and parts[0].startswith("@"))
            or (len(parts) == 3 and parts[0] in {"channel", "user", "c"})):
        if parts[-1] in ("videos", "shorts", "streams"):
            return parts[-1]
    return None


def _youtube_collection_targets(url: str, filters: ResolverFilters) -> list[ResolvedTarget] | None:
    """Expand a recognized YouTube collection, leaving other URL shapes to yt-dlp."""
    if not is_url(url):
        return None
    parsed = urlsplit(url)
    if parsed.hostname not in _YOUTUBE_HOSTS:
        return None
    parts = parsed.path.strip("/").split("/")
    tab: youtube_api.PublicationType | None = None
    playlist_ids = parse_qs(parsed.query).get("list")
    # With a date window, --limit counts uploads inside it, so the listing
    # is read past ineligible uploads instead of being cut to the limit.
    windowed = bool(filters.since or filters.until) and filters.limit > 0
    fetch_limit = None if windowed else filters.limit
    if parts in (["playlist"], ["watch"]) and playlist_ids:
        rows = youtube_api.iter_playlist_videos(playlist_ids[0], limit=fetch_limit)
    else:
        tab = _youtube_channel_tab(parsed)
        if tab is None:
            return None
        channel = youtube_api.resolve_channel(url)
        if channel is None:
            return None
        rows = youtube_api.iter_channel_uploads(channel.channel_id, tab, limit=fetch_limit)

    selected = []
    for row in rows:
        upload_date = row.published_at.date()
        if filters.since and upload_date < filters.since:
            if tab is not None:  # Only channel uploads are guaranteed newest first.
                break
            continue
        if filters.until and upload_date > filters.until:
            continue
        selected.append(row)
        if windowed and len(selected) >= filters.limit:
            break
    if tab == "shorts" and not filters.include_shorts:
        return []
    details = youtube_api.fetch_video_details(row.video_id for row in selected)
    targets = []
    for row in selected:
        detail = details.get(row.video_id)
        is_short = tab == "shorts" if tab is not None else None
        if tab is None and not filters.include_shorts:
            owner = row.channel_id or (detail.channel_id if detail else None)
            if not owner:
                raise youtube_api.TransientFailure("Missing playlist video's channel id")
            is_short = youtube_api.is_channel_short(owner, row.video_id)
        video_url = (f"https://www.youtube.com/shorts/{row.video_id}" if is_short
                     else f"https://www.youtube.com/watch?v={row.video_id}")
        targets.append(ResolvedTarget(
            url=video_url, title=row.title, upload_date=row.published_at.date(),
            duration_sec=detail.duration_sec if detail else None, channel=row.channel_title,
            source="playlist" if tab is None else "channel", video_id=row.video_id, is_short=is_short,
            statistics=detail.statistics if detail else None,
        ))
    return targets


def resolve(
    inputs: list[str],
    from_file: Path | None,
    filters: ResolverFilters,
) -> tuple[list[ResolvedTarget], list[ResolveFailure]]:
    """Expand user input into a flat list of ResolvedTarget. No media download.

    Returns: (targets, failures).
    - `targets`: successfully resolved videos (after dedup + per-source limit).
    - `failures`: probe failures per spec extension §5 — caller handles them
      (single-mode aborts; batch-mode logs them as BatchFailure(stage="resolve")
      and continues with successful targets).
    """
    raw: list[tuple[str, Source]] = []
    for u in inputs:
        raw.append((u, "inline"))
    if from_file is not None:
        for u in parse_from_file(from_file):
            raw.append((u, "file"))
    if not raw and not filters.search_query:
        raise CLIInputError(
            "No inputs given. Pass URL(s), --from-file PATH, or --search QUERY."
        )

    targets: list[ResolvedTarget] = []
    failures: list[ResolveFailure] = []
    seen_video_ids: set[str] = set()

    # Parallelize the network probes for `raw` URLs. We only parallelize
    # the I/O-bound metadata fetch; downstream processing (kind dispatch,
    # dedup, playlist expansion) stays single-threaded so the seen_video_ids
    # set needs no lock and result ordering is identical to the serial version.
    # A bare YouTube channel URL is probed (and later expanded) as the
    # channel's Ordinary Videos; `url` stays the user's input for reporting.
    fallback = fallback_notice_for_run()
    single_videos = _youtube_single_videos([url for url, _ in raw], fallback)

    def _safe_probe(item: tuple[str, Source]) -> tuple[str, Source, tuple | Exception]:
        url, src = item
        if url in single_videos:
            return url, src, ("api", [_video_details_to_target(single_videos[url], url, src)])
        try:
            normalized = normalize_youtube_channel_url(url)
            try:
                api_targets = _youtube_collection_targets(normalized, filters)
            except youtube_api.YouTubeApiError as exc:
                fallback.report(exc)
            else:
                if api_targets is not None:
                    return normalized, src, ("api", api_targets)
            return normalized, src, probe_input(normalized)
        except Exception as e:    # noqa: BLE001 — re-raised below per-url
            return url, src, e

    if raw:
        workers = min(_MAX_PROBE_WORKERS, len(raw))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            probed = list(ex.map(_safe_probe, raw))
    else:
        probed = []

    missing_youtube_dates = False
    for url, src, result in probed:
        if isinstance(result, Exception):
            failures.append(ResolveFailure(url=url, error=str(result), source=src))
            continue
        kind, info = result

        if kind == "local":
            t = _local_to_target(info["path"])
            targets.append(t)
            continue

        if kind == "video":
            t = _video_info_to_target(info, url, source=src)
            if t.video_id and t.video_id in seen_video_ids:
                continue   # dedup: keep first occurrence
            if t.video_id:
                seen_video_ids.add(t.video_id)
            targets.append(t)
            continue

        # kind == "playlist" → expand and apply limit per source
        if kind == "api":
            expanded = info
        else:
            entries = expand_channel_or_playlist(
                url, limit=filters.limit,
            )
            tab = _youtube_channel_tab(urlsplit(url))
            is_short = (tab == "shorts") if tab is not None else None
            expanded = [_channel_entry_to_target(e, source="channel", is_short=is_short) for e in entries]
            if ((filters.since or filters.until) and urlsplit(url).hostname in _YOUTUBE_HOSTS
                    and any(t.upload_date is None for t in expanded)):
                missing_youtube_dates = True
        for t in expanded:
            if t.video_id and t.video_id in seen_video_ids:
                continue
            if t.video_id:
                seen_video_ids.add(t.video_id)
            targets.append(t)

    if missing_youtube_dates:
        click.echo("Some YouTube entries have no publish date. The date filter could not "
                   "be applied to those entries.", err=True)

    # v0.3 #4: search-by-tags via yt-dlp ytsearchN:query
    if filters.search_query:
        from skills.neurolearn.utils.downloader import search_videos
        try:
            entries = search_videos(filters.search_query, limit=filters.limit)
            for e in entries:
                t = _channel_entry_to_target(e, source="search")
                if t.video_id and t.video_id in seen_video_ids:
                    continue
                if t.video_id:
                    seen_video_ids.add(t.video_id)
                targets.append(t)
        except Exception as e:
            failures.append(ResolveFailure(
                url=f"ytsearch:{filters.search_query}",
                error=str(e),
                source="search",
            ))

    # v0.3: apply post-resolution filters (since/until/duration/shorts).
    # `limit` is handled per-source in expand_* (yt-dlp playlistend); the
    # filters below run on already-probed metadata and are best-effort:
    # if a target has no upload_date / duration_sec, those filters skip it.
    targets = _apply_filters(targets, filters)

    return targets, failures


def _apply_filters(
    targets: list[ResolvedTarget],
    filters: ResolverFilters,
) -> list[ResolvedTarget]:
    """Drop targets that fail since/until/duration/shorts filters.

    Targets with missing metadata (e.g. local files have no upload_date)
    pass all date/duration checks — the filters only exclude when we
    have positive evidence of mismatch.
    """
    out: list[ResolvedTarget] = []
    for t in targets:
        if filters.since is not None and t.upload_date is not None:
            if t.upload_date < filters.since:
                continue
        if filters.until is not None and t.upload_date is not None:
            if t.upload_date > filters.until:
                continue
        if filters.min_duration_sec is not None and t.duration_sec is not None:
            if t.duration_sec < filters.min_duration_sec:
                continue
        if filters.max_duration_sec is not None and t.duration_sec is not None:
            if t.duration_sec > filters.max_duration_sec:
                continue
        if not filters.include_shorts:
            # Keep the historic duration heuristic only when type is unknown.
            if t.is_short or (t.is_short is None and t.duration_sec is not None and t.duration_sec <= 60):
                continue
        out.append(t)
    return out
