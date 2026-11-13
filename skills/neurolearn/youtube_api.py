"""YouTube Data API v3 client.

One module owns all communication with the Data API. Layout:

- ``_http_get`` — the single HTTP transport function. Everything else goes
  through it; it is the seam unit tests replace.
- ``api_get`` — one authenticated call: resolves the key, sends it in the
  ``X-goog-api-key`` header (never in the URL), maps failures to typed
  outcomes and scrubs the key from every message.
- Task-shaped functions (``check_key`` today) built on ``api_get``.

Callers decide what to do (fall back, report, skip) from the exception
type, never from message strings.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlsplit

from skills.neurolearn import config as _config
from skills.neurolearn.shared.date_filter import DateWindow
from skills.neurolearn.youtube_quota import DailyQuota, QuotaStateError

API_BASE = "https://www.googleapis.com/youtube/v3"
KEY_BACKEND = "youtube"
DEFAULT_TIMEOUT = 15.0
DEFAULT_COMMENT_CAP = 100


class YouTubeApiError(Exception):
    """Base for every failure of the YouTube Data API client.

    Raised directly only for an error the client cannot classify (e.g. a
    malformed request). ``reason`` is Google's machine-readable reason
    (``quotaExceeded``, ``playlistNotFound``, ...) when one was returned.
    """

    def __init__(self, message: str = "", *, reason: str = "", status: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.status = status


class NotConfigured(YouTubeApiError):
    """No YouTube API key is stored. No request was made."""


class InvalidKey(YouTubeApiError):
    """The key was rejected: wrong, revoked, restricted, or API not enabled."""


class QuotaExhausted(YouTubeApiError):
    """The daily quota is spent."""


class NotFound(YouTubeApiError):
    """The requested video, playlist, channel or comment does not exist."""


class CommentsDisabled(YouTubeApiError):
    """The video has comments turned off."""


class TransientFailure(YouTubeApiError):
    """Network error, timeout, rate limit or server-side failure."""


_QUOTA_REASONS = frozenset({"quotaExceeded", "dailyLimitExceeded"})
_RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
_INVALID_KEY_REASONS = frozenset({"keyInvalid", "keyExpired", "API_KEY_INVALID"})


_client = None
_client_lock = threading.Lock()


def _shared_client():
    """One HTTP client per process, so requests in a run reuse a connection.

    The library closes an idle connection on its own (5 s by default) and
    the process exit closes the rest; nothing outlives the command.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import httpx

                _client = httpx.Client()
    return _client


def _http_get(
    url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
) -> tuple[int, Any]:
    """The single HTTP transport. Returns ``(status_code, body)``.

    ``body`` is the parsed JSON, or the raw text when the response is not
    JSON. Raises ``TransientFailure`` when no response was obtained.
    """
    import httpx

    client = _shared_client()
    try:
        try:
            resp = client.get(url, params=params, headers=headers, timeout=timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # Nothing was sent, so one more attempt cannot double a request.
            resp = client.get(url, params=params, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise TransientFailure(f"{type(e).__name__}: {e}") from None
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _error_details(body: Any) -> tuple[str, str]:
    """Pull ``(reason, message)`` out of a Data API error body."""
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return "", "Unexpected API error response."
    err = body["error"]
    reasons = [
        str(item["reason"])
        for entries in (err.get("errors"), err.get("details")) if isinstance(entries, list)
        for item in entries
        if isinstance(item, dict) and item.get("reason")
    ]
    # A rejected key arrives as a generic `badRequest` in `errors` with the
    # real cause (`API_KEY_INVALID`) only in `details` — prefer the latter.
    reason = next((r for r in reasons if r in _INVALID_KEY_REASONS), "")
    reason = reason or (reasons[0] if reasons else "")
    return reason, str(err.get("message") or "")


def _classify(status: int, reason: str) -> type[YouTubeApiError]:
    if reason in _INVALID_KEY_REASONS or status == 401:
        return InvalidKey
    if reason in _QUOTA_REASONS:
        return QuotaExhausted
    if reason in _RATE_LIMIT_REASONS or status == 429 or status >= 500:
        return TransientFailure
    if reason == "commentsDisabled":
        return CommentsDisabled
    if status == 404:
        return NotFound
    if status == 403:
        return InvalidKey
    return YouTubeApiError


def _stored_key() -> str | None:
    try:
        return _config.get_api_key(KEY_BACKEND, env_path=_config.ENV_PATH)
    except (OSError, UnicodeError):
        pass
    # Decoding errors retain raw file bytes on the original exception.
    raise TransientFailure("Could not read the YouTube API key store.")


def api_get(
    resource: str,
    params: dict[str, Any],
    *,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """GET one Data API resource (``videos``, ``channels``, ...) and return its body.

    ``api_key`` defaults to the stored key. Raises a ``YouTubeApiError``
    subclass on any failure; no raised message ever contains the key.
    """
    key = api_key or _stored_key()
    if not key:
        raise NotConfigured(
            "No YouTube API key configured. "
            "Run: neurolearn config set-key youtube --from-file <path>"
        )
    if not re.fullmatch(r"[!-~]+", key):
        raise InvalidKey("The YouTube API key contains an invalid character.")
    path = _config.CONFIG_PATH
    bucket = "search" if resource == "search" else "general"
    try:
        quota = DailyQuota(path.parent, _config.load_config(path, migrate=False))
        day = quota.charge(bucket)
    except (QuotaStateError, ValueError, OSError) as exc:
        raise TransientFailure(_scrub(str(exc), key)) from None
    if day is None:
        raise QuotaExhausted(f"Local daily YouTube {bucket} quota exhausted.")
    failure: TransientFailure | None = None
    try:
        status, body = _http_get(
            f"{API_BASE}/{resource}", params, {"X-goog-api-key": key}, timeout
        )
    except TransientFailure as e:
        failure = e
    if failure is not None:
        # Raised outside the except block so the unscrubbed original is not
        # kept alive as __context__ of the error callers see.
        raise TransientFailure(
            _scrub(str(failure), key), reason=_scrub(failure.reason, key), status=failure.status
        )

    if status == 200 and isinstance(body, dict):
        return body

    if not isinstance(body, dict):
        raise TransientFailure(
            f"HTTP {status}: unexpected non-JSON response.", status=status,
        )
    reason, message = _error_details(body)
    outcome = _classify(status, reason)
    if outcome is QuotaExhausted:
        try:
            quota.mark_exhausted(day, bucket)
        except QuotaStateError as exc:
            message += f" ({exc})"
    raise outcome(
        _scrub(f"HTTP {status} {reason}: {message}".strip(), key),
        reason=_scrub(reason, key),
        status=status,
    )


def check_key(api_key: str | None = None) -> None:
    """Validate the key with one cheap request (1 quota unit).

    Returns ``None`` when the key works. Raises ``NotConfigured``,
    ``InvalidKey``, ``QuotaExhausted`` (key accepted, quota spent) or
    ``TransientFailure``.
    """
    api_get("i18nLanguages", {"part": "id"}, api_key=api_key)


@dataclass(frozen=True)
class YouTubeChannel:
    channel_id: str
    title: str | None
    handle: str | None


def resolve_channel(source: str) -> YouTubeChannel | None:
    """Look up a YouTube channel. Return None for inputs the API cannot resolve."""
    if source.startswith("@"):
        source = f"https://www.youtube.com/{source}"
    try:
        url = urlsplit(source if "://" in source else f"https://{source}")
    except ValueError:
        return None
    if url.scheme not in ("https", "http"):
        return None
    parts = url.path.strip("/").split("/")
    first = unquote(parts[0])
    resource = "channels"
    if url.hostname in ("youtu.be", "www.youtu.be"):
        resource, lookup = "videos", {"id": first}
    elif url.hostname not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        return None
    elif first == "watch" and "v" in (query := parse_qs(url.query)):
        resource, lookup = "videos", {"id": query["v"][0]}
    elif len(parts) >= 2 and first in ("shorts", "embed", "live"):
        resource, lookup = "videos", {"id": parts[1]}
    elif first.startswith("@") and len(first) > 1:
        lookup = {"forHandle": first}
    elif len(parts) >= 2 and first in ("channel", "user"):
        lookup = {"id" if first == "channel" else "forUsername": unquote(parts[1])}
    else:
        # Legacy /c/ names have no exact channels.list filter.
        return None
    fields = ("items(snippet(channelId,channelTitle))" if resource == "videos"
              else "items(id,snippet(title,customUrl))")
    body = api_get(resource, {"part": "snippet", "fields": fields, **lookup})
    items = body.get("items")
    if items == []:
        raise NotFound(f"Channel not found: {source}")
    if not isinstance(items, list) or not isinstance(items[0], dict):
        raise TransientFailure(f"Unexpected {resource}.list response")
    item = items[0]
    snippet = item.get("snippet")
    if not isinstance(snippet, dict):
        raise TransientFailure(f"Missing snippet in {resource}.list response")
    if resource == "videos":
        channel_id, title, handle = snippet.get("channelId"), snippet.get("channelTitle"), None
    else:
        channel_id, title = item.get("id"), snippet.get("title")
        custom_url = snippet.get("customUrl")
        handle = (custom_url if isinstance(custom_url, str) and custom_url.startswith("@")
                  else lookup.get("forHandle"))
    if not isinstance(channel_id, str) or not channel_id:
        raise TransientFailure(f"Missing channel id in {resource}.list response")
    return YouTubeChannel(channel_id, title, handle)


def _comment_pages(resource: str, params: dict, cap: int | None, *, single_page: bool = False) -> list[dict]:
    items = []
    seen_tokens = set()
    while cap is None or len(items) < cap:
        remaining = 100 if cap is None else min(100, cap - len(items))
        body = api_get(resource, {**params, "maxResults": remaining, "textFormat": "plainText"})
        if not isinstance(body.get("items"), list):
            raise TransientFailure(f"Unexpected {resource}.list response")
        items.extend(body["items"][:remaining])
        token = body.get("nextPageToken")
        if single_page or not token or (cap is not None and len(items) >= cap):
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise TransientFailure(f"Invalid pagination token in {resource}.list response")
        seen_tokens.add(token)
        params["pageToken"] = token
    return items


def list_comment_threads(video_id: str, *, cap: int | None = None, order: str = "relevance") -> list[dict]:
    """Get a capped sample of threads, including their free inline replies."""
    return _comment_pages("commentThreads", {
        "part": "snippet,replies", "videoId": video_id, "order": order,
    }, DEFAULT_COMMENT_CAP if cap is None else cap, single_page=cap is None)


def list_comment_replies(parent_id: str) -> list[dict]:
    """Fetch the complete public reply list for one top-level comment."""
    return _comment_pages("comments", {"part": "snippet", "parentId": parent_id}, cap=None)


@dataclass(frozen=True)
class VideoDetails:
    """Metadata returned for a public video. Unavailable counts stay absent."""

    video_id: str
    title: str | None
    channel_id: str | None
    published_at: datetime | None
    duration_sec: int | None
    is_live_stream: bool
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    channel_title: str | None = None

    @property
    def statistics(self) -> dict[str, int | None]:
        return {
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
        }


_DURATION = re.compile(
    r"P(?:(?P<days>[0-9]+)D)?(?:T(?=[0-9])(?:(?P<hours>[0-9]+)H)?"
    r"(?:(?P<minutes>[0-9]+)M)?(?:(?P<seconds>[0-9]+)S)?)?"
)


def parse_iso8601_duration(text: str | None) -> int | None:
    """Parse the day/hour/minute/second ISO 8601 durations used by YouTube."""
    match = _DURATION.fullmatch(text or "")
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (int(value or 0) for value in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _parse_video_details(item: dict) -> VideoDetails:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})

    def count(key: str) -> int | None:
        value = statistics.get(key)
        return int(value) if value is not None else None

    published = snippet.get("publishedAt")
    return VideoDetails(
        video_id=item["id"],
        title=snippet.get("title"),
        channel_id=snippet.get("channelId"),
        channel_title=snippet.get("channelTitle"),
        published_at=datetime.fromisoformat(published) if published else None,
        duration_sec=parse_iso8601_duration(item.get("contentDetails", {}).get("duration")),
        is_live_stream=(
            "liveStreamingDetails" in item
            or snippet.get("liveBroadcastContent") in ("live", "upcoming")
        ),
        view_count=count("viewCount"),
        like_count=count("likeCount"),
        comment_count=count("commentCount"),
    )


def fetch_video_details(
    video_ids: Iterable[str], *, api_key: str | None = None,
) -> dict[str, VideoDetails]:
    """Return details by ID, omitting videos YouTube does not return.

    One videos.list request accepts up to 50 unique IDs.
    """
    ids = list(dict.fromkeys(video_ids))
    details = {}
    for start in range(0, len(ids), 50):
        body = api_get("videos", {
            "part": "snippet,contentDetails,statistics,liveStreamingDetails",
            "id": ",".join(ids[start:start + 50]),
            "fields": ("items(id,snippet(title,channelId,channelTitle,publishedAt,liveBroadcastContent),"
                       "contentDetails(duration),statistics(viewCount,likeCount,commentCount),"
                       "liveStreamingDetails)"),
        }, api_key=api_key)
        try:
            for item in body["items"]:
                video = _parse_video_details(item)
                details[video.video_id] = video
        except (KeyError, AttributeError, TypeError, ValueError):
            raise TransientFailure("Unexpected videos.list response") from None
    return details


def search_videos(
    query: str, *, language: str, limit: int, window: DateWindow | None,
    sort_by_views: bool = False,
) -> list[VideoDetails]:
    """Search up to `limit` videos, then hydrate their IDs in batched details calls."""
    if limit <= 0:
        return []
    params = {
        "part": "snippet", "type": "video", "q": query,
        "order": "viewCount" if sort_by_views else "relevance",
        "relevanceLanguage": language,
        "fields": "nextPageToken,items(id/videoId)",
    }
    if window:
        params["publishedAfter"] = f"{window.start.isoformat()}T00:00:00Z"
        params["publishedBefore"] = f"{window.end.isoformat()}T23:59:59.999999Z"
    # One search call per page of 50; a limit within one page costs one call.
    ids: list[str] = []
    seen_tokens: set[str] = set()
    while len(ids) < limit:
        # Later pages ask for a full page: results repeat across pages, and a
        # short request would need one more call to replace the repeats.
        body = api_get("search", {**params, "maxResults": 50 if ids else min(limit, 50)})
        try:
            if not isinstance(body["items"], list):
                raise TypeError
            page = [item["id"]["videoId"] for item in body["items"]]
            if not all(isinstance(vid, str) and vid for vid in page):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise TransientFailure("Unexpected search.list response") from None
        fresh = [vid for vid in dict.fromkeys(page) if vid not in ids]
        ids.extend(fresh)
        token = body.get("nextPageToken")
        # A page with nothing new ends the search: never spend calls on repeats.
        # A limit within one page stays one call even when that page is short.
        if limit <= 50 or len(ids) >= limit or not fresh or not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise TransientFailure("Invalid search.list page token")
        seen_tokens.add(token)
        params["pageToken"] = token
    ids = ids[:limit]
    details = fetch_video_details(ids)
    return [details[vid] for vid in ids if vid in details]


PublicationType = Literal["all", "videos", "shorts", "streams"]
_UPLOAD_PREFIX = {"all": "UU", "videos": "UULF", "shorts": "UUSH", "streams": "UULV"}


@dataclass(frozen=True)
class PlaylistVideo:
    video_id: str
    title: str | None
    published_at: datetime
    channel_id: str | None
    channel_title: str | None


def iter_playlist_videos(
    playlist_id: str, *, limit: int | None = None,
) -> Iterator[PlaylistVideo]:
    """Read a playlist in its own order, using the video's original publish time."""
    params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "fields": ("nextPageToken,items(contentDetails(videoId,videoPublishedAt),"
                   "snippet(title,videoOwnerChannelId,videoOwnerChannelTitle))"),
    }
    seen_tokens: set[str] = set()
    remaining = limit
    while remaining is None or remaining > 0:
        page = api_get("playlistItems", {
            **params, "maxResults": 50 if remaining is None else min(50, remaining),
        })
        try:
            items = page["items"]
            if not isinstance(items, list):
                raise ValueError
            for item in items:
                content, snippet = item["contentDetails"], item["snippet"]
                published = content.get("videoPublishedAt")
                # Deleted/private placeholders have no public video or publish date.
                if not published and not snippet.get("videoOwnerChannelId"):
                    continue
                yield PlaylistVideo(
                    content["videoId"], snippet.get("title"), datetime.fromisoformat(published),
                    snippet.get("videoOwnerChannelId"), snippet.get("videoOwnerChannelTitle"),
                )
                if remaining is not None:
                    remaining -= 1
                    if remaining == 0:
                        return
        except (AttributeError, KeyError, TypeError, ValueError):
            raise TransientFailure("Unexpected playlistItems.list response") from None
        token = page.get("nextPageToken")
        if not token:
            return
        if not isinstance(token, str) or token in seen_tokens:
            raise TransientFailure("Invalid playlistItems.list page token")
        seen_tokens.add(token)
        params["pageToken"] = token


def _uploads_playlist_id(channel_id: str, publication_type: PublicationType) -> str:
    if not channel_id.startswith("UC"):
        raise TransientFailure("Invalid uploads channel id")
    return _UPLOAD_PREFIX[publication_type] + channel_id[2:]


def is_channel_short(channel_id: str, video_id: str) -> bool:
    """Check membership directly when an arbitrary playlist mixes formats."""
    try:
        page = api_get("playlistItems", {
            "part": "id", "fields": "items(id)", "videoId": video_id,
            "playlistId": _uploads_playlist_id(channel_id, "shorts"), "maxResults": 1,
        })
    except NotFound as exc:
        if exc.reason == "playlistNotFound":
            return False
        raise
    if not isinstance(page.get("items"), list):
        raise TransientFailure("Unexpected playlistItems.list response")
    return bool(page["items"])


def iter_channel_uploads(
    channel_id: str, publication_type: PublicationType, *, limit: int | None = None,
) -> Iterator[PlaylistVideo]:
    """List newest uploads from YouTube's requested publication-type playlist."""
    playlist_id = _uploads_playlist_id(channel_id, publication_type)
    try:
        yield from iter_playlist_videos(playlist_id, limit=limit)
    except NotFound as exc:
        if publication_type == "all" or exc.reason != "playlistNotFound":
            raise
