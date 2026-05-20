"""subtitles backend — fast path via youtube-transcript-api, no API key needed.

v0.10.7 cookies support: when YouTube rate-limits (`IpBlocked`) on
anonymous requests, the user can register a `youtube` cookies.txt via
`neurolearn subscribes cookies set youtube <path>`. This module then
builds a `requests.Session` from that file and hands it to
`YouTubeTranscriptApi(http_client=...)`, which routes the request
through the authenticated session and bypasses the IP block.
"""
from __future__ import annotations

from dataclasses import dataclass

from skills.neurolearn.backends.base import (
    BackendError,
    TranscriptionResult,
)
from skills.neurolearn.utils.downloader import (
    extract_youtube_video_id,
    is_youtube_url,
)
from skills.neurolearn.utils.output_writer import Segment


def _build_authenticated_session(cookies_path: str | None):
    """Return a `requests.Session` populated from a Netscape cookies.txt,
    or None when the path is empty / unreadable. Safe failure: malformed
    cookie files just disable the cookie path; we don't raise."""
    if not cookies_path:
        return None
    try:
        from http.cookiejar import MozillaCookieJar
        import requests
    except ImportError:
        return None
    jar = MozillaCookieJar(cookies_path)
    try:
        # ignore_discard/expires: keep all cookies; some session-cookies
        # have weird flags and we want everything yt-dlp would send.
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, Exception):    # malformed file
        return None
    session = requests.Session()
    session.cookies = jar
    return session


class _ApiAdapter:
    """Adapter over youtube-transcript-api ≥0.6 instance-based API.
    Returns list of dicts with text/start/duration keys for backend convenience."""

    def __init__(self, cookies_file: str | None = None):
        self._cookies_file = cookies_file

    def get_transcript(self, video_id: str, languages: list[str] | None = None) -> list[dict]:
        from youtube_transcript_api import YouTubeTranscriptApi

        langs = languages or ["en"]
        session = _build_authenticated_session(self._cookies_file)
        api = (
            YouTubeTranscriptApi(http_client=session)
            if session is not None
            else YouTubeTranscriptApi()
        )
        fetched = api.fetch(video_id, languages=langs)
        # FetchedTranscript is iterable; each FetchedTranscriptSnippet has .text/.start/.duration
        return [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in fetched
        ]


def _get_transcript_api(cookies_file: str | None = None) -> _ApiAdapter:
    """Return an API adapter object. Lazy-imported so youtube-transcript-api
    is only required at call time. Patched in unit tests."""
    try:
        import youtube_transcript_api  # noqa: F401
    except ImportError as e:
        raise ImportError("youtube-transcript-api is not installed. Run `uv sync`.") from e
    return _ApiAdapter(cookies_file=cookies_file)


@dataclass
class SubtitlesBackend:
    name: str = "subtitles"
    supports_url: bool = True
    supports_local_file: bool = False

    def is_configured(self) -> tuple[bool, str | None]:
        try:
            import youtube_transcript_api  # noqa: F401
            return True, None
        except ImportError:
            return False, "youtube-transcript-api is not installed. Run `uv sync`."

    def transcribe(self, audio_or_url, *, language: str = "auto", **opts) -> TranscriptionResult:
        url = str(audio_or_url)
        if not is_youtube_url(url):
            raise BackendError("Subtitles backend only works with YouTube URLs.")

        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise BackendError(f"Could not extract YouTube video ID from URL: {url}")

        # v0.10.7: opportunistically use the user's YouTube cookies (set
        # via `subscribes cookies set youtube <path>`) to bypass IP rate
        # limits. Resolution is best-effort — if cookies aren't configured
        # or the file doesn't exist, we proceed anonymously.
        cookies_file: str | None = None
        try:
            from skills.neurolearn.subscribes.cookies_onboarding import (
                resolve_cookies_file,
            )
            cookies_file = resolve_cookies_file("youtube") or None
        except Exception:
            cookies_file = None

        api = _get_transcript_api(cookies_file=cookies_file)
        languages = None if language == "auto" else [language]
        try:
            raw = api.get_transcript(video_id, languages=languages or ["en"])
        except Exception as e:
            raise BackendError(
                f"Subtitles unavailable for this video ({type(e).__name__}). "
                "Try another backend."
            ) from e

        segments: list[Segment] = []
        for item in raw:
            start = float(item.get("start", 0.0))
            duration = float(item.get("duration", 0.0))
            segments.append(Segment(
                start=start,
                end=start + duration,
                text=str(item.get("text", "")).strip(),
            ))
        if not segments:
            raise BackendError(
                f"Subtitles for video {video_id} are empty or unavailable in the requested languages. "
                "Smart mode will switch to the fallback backend."
            )
        text = " ".join(s.text for s in segments)
        return TranscriptionResult(
            text=text,
            segments=segments,
            language_detected=language if language != "auto" else None,
            backend_name=self.name,
            duration_seconds=segments[-1].end if segments else 0.0,
        )
