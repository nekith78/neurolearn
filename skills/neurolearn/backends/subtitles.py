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


def _run_yt_dlp_subtitle_pass(
    url: str,
    languages: list[str],
    cookies_file: str | None,
    *,
    write_auto: bool,
    throttle: str = "off",
) -> list | None:
    """One yt-dlp invocation to fetch subtitles of a specific kind.

    `write_auto=False` → `--write-subs` only (manual/uploader-provided).
    `write_auto=True`  → `--write-auto-subs` only (machine-generated).

    Returns parsed segments on success, None when yt-dlp produced no
    subtitle file (which means: requested kind isn't available — caller
    falls through to the next pass). Raises BackendError only on
    hard failures (timeout, ffmpeg missing, etc.) that no second pass
    can fix.
    """
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    kind_label = "auto-generated" if write_auto else "manual (uploader-provided)"

    with tempfile.TemporaryDirectory(prefix="neurolearn-subs-") as tmp:
        tmp_path = Path(tmp)
        template = str(tmp_path / "%(id)s.%(ext)s")
        from skills.neurolearn.utils.downloader import throttle_subtitle_flags
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs" if write_auto else "--write-subs",
            "--sub-lang", ",".join(languages),
            "--sub-format", "json3/srv3/srv2/srv1/best",
            "--no-playlist",
            *throttle_subtitle_flags(throttle),
            "-o", template,
        ]
        if cookies_file:
            cmd += ["--cookies", cookies_file]
        cmd.append(url)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            raise BackendError(
                f"yt-dlp subtitle fetch ({kind_label}) timed out after 60s. "
                "Smart mode will switch to the fallback backend."
            )

        # yt-dlp can return rc != 0 even on "subtitle not available"
        # (it sets exit when no subs match the requested filter). We
        # treat ANY rc != 0 as "this kind isn't here, try next pass"
        # rather than a hard error, unless we also see actual files —
        # in which case we use them.
        sub_files = list(tmp_path.glob("*.json3")) \
            + list(tmp_path.glob("*.srv3")) \
            + list(tmp_path.glob("*.srv2")) \
            + list(tmp_path.glob("*.srv1"))

        if not sub_files:
            if proc.returncode != 0:
                # Genuine fetch failure (IP block, network, etc.) — but
                # let the caller try the auto pass; if that also fails,
                # the cascade falls to groq/whisper-local.
                tail = (proc.stderr or "").strip().splitlines()[-2:]
                sys.stderr.write(
                    f"[neurolearn] yt-dlp {kind_label} subs unavailable "
                    f"({' | '.join(tail) or 'no subs'}); trying next pass.\n"
                )
            return None

        sub_path = sub_files[0]
        sys.stderr.write(
            f"[neurolearn] subtitles Path 2 succeeded via yt-dlp "
            f"({kind_label}: {sub_path.name}).\n"
        )
        return _parse_yt_dlp_subtitle_file(sub_path)


def _parse_yt_dlp_subtitle_file(path) -> list:
    """Parse a yt-dlp-produced subtitle file (json3 / srv3 / srv2 / srv1)
    into a list of Segments. The internal YouTube formats are JSON-based
    with similar shapes; we handle the json3 family explicitly and fall
    through to plain text parsing for older srv formats.

    json3 structure:
      {
        "events": [
          {"tStartMs": 12345, "dDurationMs": 2000,
           "segs": [{"utf8": "Hello"}, {"utf8": " world"}]},
          ...
        ]
      }
    """
    import json
    from pathlib import Path
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")

    segments: list = []
    if p.suffix == ".json3":
        data = json.loads(text)
        for ev in data.get("events", []):
            if not ev.get("segs"):
                continue
            start_ms = ev.get("tStartMs", 0)
            dur_ms = ev.get("dDurationMs", 0) or 0
            seg_text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
            if not seg_text:
                continue
            segments.append(Segment(
                start=start_ms / 1000.0,
                end=(start_ms + dur_ms) / 1000.0,
                text=seg_text,
            ))
    else:
        # srv1/srv2/srv3 are XML-shaped — yt-dlp's JSON variants of the
        # internal format. Cheap regex parse is adequate: <p t="ms"
        # d="ms">text</p>.
        import re
        TS = re.compile(
            r'<p\s+t="(\d+)"\s+d="(\d+)"[^>]*>(.*?)</p>',
            re.DOTALL,
        )
        TAG_STRIP = re.compile(r"<[^>]+>")
        for m in TS.finditer(text):
            start_ms = int(m.group(1))
            dur_ms = int(m.group(2))
            txt = TAG_STRIP.sub("", m.group(3)).strip()
            if not txt:
                continue
            segments.append(Segment(
                start=start_ms / 1000.0,
                end=(start_ms + dur_ms) / 1000.0,
                text=txt,
            ))
    return segments


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
    # v0.19.0: self-throttle tier applied to the yt-dlp subtitle pass
    # (request pacing only — see throttle_subtitle_flags). Set by the
    # factory from cfg.throttle; "off" keeps legacy/direct construction unchanged.
    throttle: str = "off"

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

        languages = [language] if language != "auto" else ["en"]

        # v0.15.3: two-tier subtitle fetch. Path 1 is fast (~3 s, pure
        # Python, no subprocess). When YouTube IP-blocks the timedtext
        # endpoint directly — common on residential IPs and almost
        # always on cloud/VPN IPs — fall through to Path 2: yt-dlp's
        # subtitle extractor, which uses our full anti-block stack
        # (cookies, PO Token plugin auto-attached). Slower (~8 s) but
        # often works where Path 1 doesn't because yt-dlp negotiates
        # the player handshake before fetching captions.
        segments = self._fetch_via_transcript_api(video_id, languages, cookies_file)
        if segments is None:
            segments = self._fetch_via_yt_dlp(url, languages, cookies_file)

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

    # ------------------------------------------------------------------
    # v0.15.3: subtitle fetch paths
    # ------------------------------------------------------------------

    def _fetch_via_transcript_api(
        self, video_id: str, languages: list[str], cookies_file: str | None,
    ) -> list[Segment] | None:
        """Path 1 — fast, pure-Python. Returns parsed segments on success,
        None when blocked (so the caller falls through to yt-dlp).
        Re-raises on auth-related errors that yt-dlp also can't fix."""
        import sys
        api = _get_transcript_api(cookies_file=cookies_file)
        try:
            raw = api.get_transcript(video_id, languages=languages)
        except Exception as e:
            cls = type(e).__name__
            # IpBlocked / RequestBlocked / PoTokenRequired → yt-dlp may
            # succeed where we failed because of cookies + PO Token.
            # TranscriptsDisabled / NoTranscriptFound → no subtitles at
            # all; yt-dlp won't help, surface BackendError directly.
            if cls in ("IpBlocked", "RequestBlocked", "PoTokenRequired",
                       "YouTubeRequestFailed", "YouTubeDataUnparsable"):
                sys.stderr.write(
                    f"[neurolearn] subtitles Path 1 (transcript-api) "
                    f"blocked ({cls}); falling through to Path 2 (yt-dlp).\n"
                )
                return None
            raise BackendError(
                f"Subtitles unavailable for this video ({cls}). "
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
        return segments

    def _fetch_via_yt_dlp(
        self, url: str, languages: list[str], cookies_file: str | None,
    ) -> list[Segment]:
        """Path 2 — yt-dlp subtitle fetch. Uses our full anti-block stack:
        registered cookies + PO Token plugin + curl_cffi TLS impersonation.
        yt-dlp negotiates the player handshake before fetching, which the
        direct timedtext API call (transcript-api) cannot do.

        v0.15.4: two-pass to prefer MANUAL subtitles over auto-generated.
        The uploader-provided captions are usually higher quality (often
        professionally produced or community-contributed); auto-generated
        is YouTube's own ASR, which is what we'd be trying to *replace*
        with Whisper anyway.

          Pass 1: --write-subs only (manual / uploader-provided)
                    ↓ if file found, use it
          Pass 2: --write-auto-subs (YouTube's machine-generated)
                    ↓ if file found, use it
                    ↓ else, raise BackendError → smart cascade →
                      groq/whisper-local does real Whisper ASR.
        """
        import shutil
        if shutil.which("yt-dlp") is None:
            raise BackendError(
                "yt-dlp not on PATH. Cannot use subtitle fallback path. "
                "Install via `uv sync` or `pip install yt-dlp`."
            )

        # Pass 1: manual subtitles only
        result = _run_yt_dlp_subtitle_pass(
            url, languages, cookies_file, write_auto=False, throttle=self.throttle,
        )
        if result is not None:
            return result

        # Pass 2: fall back to auto-generated
        result = _run_yt_dlp_subtitle_pass(
            url, languages, cookies_file, write_auto=True, throttle=self.throttle,
        )
        if result is not None:
            return result

        raise BackendError(
            "yt-dlp found no subtitles for the requested languages "
            "(neither manual nor auto-generated). Smart mode will switch "
            "to the fallback backend."
        )
