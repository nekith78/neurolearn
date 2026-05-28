import sys
import pytest
from unittest.mock import patch, MagicMock
from skills.neurolearn.backends.subtitles import SubtitlesBackend
from skills.neurolearn.backends.base import BackendError


def test_supports_url_true():
    assert SubtitlesBackend().supports_url is True


def test_only_youtube_urls_supported():
    b = SubtitlesBackend()
    with pytest.raises(BackendError, match="YouTube"):
        b.transcribe("https://vimeo.com/123", language="en")


def test_transcribe_returns_result():
    fake_segments = [
        {"start": 0.0, "duration": 2.5, "text": "Hello"},
        {"start": 2.5, "duration": 2.5, "text": "World"},
    ]
    fake_api = MagicMock()
    fake_api.get_transcript.return_value = fake_segments

    with patch(
        "skills.neurolearn.backends.subtitles._get_transcript_api",
        return_value=fake_api,
    ):
        b = SubtitlesBackend()
        result = b.transcribe("https://youtu.be/dQw4w9WgXcQ", language="en")

    assert result.backend_name == "subtitles"
    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello"
    assert result.segments[0].end == 2.5


def test_transcribe_empty_subtitles_raises_backend_error():
    """Empty transcript list must raise BackendError so smart-mode fallback activates."""
    fake_api = MagicMock()
    fake_api.get_transcript.return_value = []

    with patch(
        "skills.neurolearn.backends.subtitles._get_transcript_api",
        return_value=fake_api,
    ):
        b = SubtitlesBackend()
        with pytest.raises(BackendError, match="empty"):
            b.transcribe("https://youtu.be/aaa", language="en")


def test_is_configured_when_youtube_transcript_api_missing(monkeypatch):
    """If youtube-transcript-api is not installed, is_configured returns (False, hint)."""
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)  # poison the import
    backend = SubtitlesBackend()
    ok, reason = backend.is_configured()
    assert ok is False
    assert reason and "youtube-transcript-api" in reason.lower()


# ---------------------------------------------------------------------------
# v0.15.3: yt-dlp subtitle fallback path
# ---------------------------------------------------------------------------

def test_parse_json3_subtitle_file(tmp_path):
    """Path 2 parser: yt-dlp's json3 subtitle format → Segments."""
    from skills.neurolearn.backends.subtitles import _parse_yt_dlp_subtitle_file
    import json
    sub_file = tmp_path / "video.en.json3"
    sub_file.write_text(json.dumps({
        "events": [
            {"tStartMs": 1000, "dDurationMs": 2000,
             "segs": [{"utf8": "Hello"}, {"utf8": " world"}]},
            {"tStartMs": 3500, "dDurationMs": 1500,
             "segs": [{"utf8": "Second"}, {"utf8": " line"}]},
            # Empty/jumpcut event — should be skipped
            {"tStartMs": 5000, "dDurationMs": 500, "segs": []},
        ],
    }))

    segments = _parse_yt_dlp_subtitle_file(sub_file)

    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 3.0
    assert segments[0].text == "Hello world"
    assert segments[1].start == 3.5
    assert segments[1].end == 5.0
    assert segments[1].text == "Second line"


def test_parse_srv3_subtitle_file(tmp_path):
    """Path 2 parser: yt-dlp's older srv3 (XML-like) format → Segments."""
    from skills.neurolearn.backends.subtitles import _parse_yt_dlp_subtitle_file
    sub_file = tmp_path / "video.en.srv3"
    sub_file.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<timedtext format="3">\n'
        '<body>\n'
        '<p t="0" d="2500"><s>Hello there</s></p>\n'
        '<p t="2500" d="3000"><s>How are you</s></p>\n'
        '</body>\n'
        '</timedtext>\n'
    )

    segments = _parse_yt_dlp_subtitle_file(sub_file)

    assert len(segments) == 2
    assert segments[0].start == 0.0
    assert segments[0].end == 2.5
    assert "Hello there" in segments[0].text
    assert segments[1].start == 2.5
    assert segments[1].end == 5.5


def test_transcript_api_blocked_falls_through_to_yt_dlp(tmp_path):
    """v0.15.3 cascade: when transcript-api raises IpBlocked, the backend
    should fall through to the yt-dlp path instead of failing outright."""
    from skills.neurolearn.backends.subtitles import SubtitlesBackend

    class _FakeIpBlocked(Exception):
        pass
    _FakeIpBlocked.__name__ = "IpBlocked"

    fake_api = MagicMock()
    fake_api.get_transcript.side_effect = _FakeIpBlocked("blocked by youtube")

    yt_dlp_segments = [
        # Pre-built Segments as if yt-dlp succeeded
        # Returned by _fetch_via_yt_dlp
    ]
    from skills.neurolearn.utils.output_writer import Segment
    yt_dlp_segments = [
        Segment(start=0.0, end=2.0, text="Hello world"),
        Segment(start=2.0, end=4.0, text="Second line"),
    ]

    with patch(
        "skills.neurolearn.backends.subtitles._get_transcript_api",
        return_value=fake_api,
    ), patch.object(
        SubtitlesBackend, "_fetch_via_yt_dlp",
        return_value=yt_dlp_segments,
    ):
        b = SubtitlesBackend()
        result = b.transcribe("https://youtu.be/abc", language="en")

    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello world"
    assert result.segments[1].text == "Second line"
    assert result.backend_name == "subtitles"


def test_yt_dlp_pass_prefers_manual_subs_over_auto(tmp_path, monkeypatch):
    """v0.15.4: when both manual and auto subs are available, Path 2's
    two-pass yt-dlp invocation must use manual first.

    We patch _run_yt_dlp_subtitle_pass to record which `write_auto`
    flag was used. The first pass should be write_auto=False (manual);
    the second pass should not be invoked if the first found a file.
    """
    from skills.neurolearn.backends.subtitles import SubtitlesBackend
    from skills.neurolearn.utils.output_writer import Segment

    manual_segments = [Segment(start=0.0, end=2.0, text="Manual line 1")]
    calls: list[bool] = []

    def fake_pass(url, languages, cookies_file, *, write_auto, throttle="off"):
        calls.append(write_auto)
        # Manual pass succeeds; auto pass never runs in this scenario
        if write_auto is False:
            return manual_segments
        return None

    monkeypatch.setattr(
        "skills.neurolearn.backends.subtitles._run_yt_dlp_subtitle_pass",
        fake_pass,
    )
    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/bin/yt-dlp",
    )

    b = SubtitlesBackend()
    result = b._fetch_via_yt_dlp("https://youtu.be/abc", ["en"], None)

    assert calls == [False], (
        f"Expected only manual pass (write_auto=False), got: {calls}"
    )
    assert result == manual_segments


def test_yt_dlp_falls_back_to_auto_when_no_manual(tmp_path, monkeypatch):
    """v0.15.4: if manual subs aren't available, Path 2 falls through
    to auto-generated. Both passes are invoked, second one returns segments."""
    from skills.neurolearn.backends.subtitles import SubtitlesBackend
    from skills.neurolearn.utils.output_writer import Segment

    auto_segments = [Segment(start=0.0, end=2.0, text="Auto-generated line")]
    calls: list[bool] = []

    def fake_pass(url, languages, cookies_file, *, write_auto, throttle="off"):
        calls.append(write_auto)
        if write_auto is True:
            return auto_segments
        return None

    monkeypatch.setattr(
        "skills.neurolearn.backends.subtitles._run_yt_dlp_subtitle_pass",
        fake_pass,
    )
    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/bin/yt-dlp",
    )

    b = SubtitlesBackend()
    result = b._fetch_via_yt_dlp("https://youtu.be/abc", ["en"], None)

    assert calls == [False, True], (
        f"Expected manual then auto, got: {calls}"
    )
    assert result == auto_segments


def test_yt_dlp_raises_when_neither_pass_has_subs(monkeypatch):
    """If both passes find nothing, smart cascade gets BackendError to
    fall through to groq / whisper-local."""
    from skills.neurolearn.backends.subtitles import SubtitlesBackend

    monkeypatch.setattr(
        "skills.neurolearn.backends.subtitles._run_yt_dlp_subtitle_pass",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/bin/yt-dlp",
    )

    b = SubtitlesBackend()
    with pytest.raises(BackendError, match="no subtitles"):
        b._fetch_via_yt_dlp("https://youtu.be/abc", ["en"], None)


def test_resolve_cookies_file_falls_back_to_legacy_slot(tmp_path, monkeypatch):
    """v0.15.3: subtitles backend resolves YouTube cookies from EITHER
    the new `cfg.youtube_cookies_file` slot OR the legacy `cfg.cookies_file`
    slot. The legacy slot is what `neurolearn config set-cookies` has
    historically written to; without this fallback, every user with
    cookies registered via that command hits IpBlocked even though
    cookies are technically present on disk."""
    from skills.neurolearn.config import Config, save_config, CONFIG_PATH
    from skills.neurolearn.subscribes.cookies_onboarding import resolve_cookies_file

    fake_cookie_file = tmp_path / "yt.txt"
    fake_cookie_file.write_text("# Netscape HTTP Cookie File\n")

    cfg_path = tmp_path / "config.toml"
    cfg = Config(cookies_file=str(fake_cookie_file), youtube_cookies_file="")
    save_config(cfg, cfg_path)

    resolved = resolve_cookies_file("youtube", config_path=cfg_path)
    assert resolved == str(fake_cookie_file), (
        "Legacy cookies_file slot must be picked up when youtube_cookies_file is empty"
    )


# === v0.19.x: subtitle language on `auto` (Fix B) ===

def test_ytdlp_caption_langs_original_first():
    """yt-dlp metadata → caption langs original-first (not English-first)."""
    from unittest.mock import patch
    from skills.neurolearn.backends import subtitles as S

    class _FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {
                "language": "ru",
                "subtitles": {},
                "automatic_captions": {"en": [], "ru": [], "ru-orig": []},
            }

    with patch("yt_dlp.YoutubeDL", _FakeYDL):
        langs = S._ytdlp_caption_langs("https://x/y", None)
    assert langs[0] == "ru"        # original first, not "en"
    assert "en" in langs


def test_list_language_codes_ranks_generated_before_manual():
    """list_language_codes must rank the auto-GENERATED track (spoken/original
    language) ahead of a manually-created one — a creator's manual English
    track on a Russian video must NOT win over the auto Russian captions.
    Regression for the H1 ordering bug."""
    from unittest.mock import patch
    from skills.neurolearn.backends import subtitles as S

    class _T:
        def __init__(self, code, generated):
            self.language_code = code
            self.is_generated = generated

    # A Russian video: creator uploaded a MANUAL English (translation) track,
    # YouTube auto-GENERATED the Russian (original-language) captions.
    fake_list = [_T("en", generated=False), _T("ru", generated=True)]

    class _FakeApi:
        def __init__(self, *a, **kw): pass
        def list(self, video_id): return fake_list

    with patch(
        "youtube_transcript_api.YouTubeTranscriptApi", _FakeApi,
    ), patch.object(S, "_build_authenticated_session", return_value=None):
        codes = S._ApiAdapter().list_language_codes("vid123")
    assert codes[0] == "ru"   # generated original first, not the manual "en"
    assert codes == ["ru", "en"]


def test_transcribe_auto_requests_original_language_not_english():
    """language=auto must request the resolved original language, not ['en']."""
    from unittest.mock import patch
    from skills.neurolearn.backends.subtitles import SubtitlesBackend
    from skills.neurolearn.utils.output_writer import Segment

    be = SubtitlesBackend()
    captured = {}

    def fake_fetch(self, video_id, languages, cookies_file):
        captured["langs"] = languages
        return [Segment(start=0.0, end=1.0, text="привет")]

    with patch.object(SubtitlesBackend, "_resolve_auto_languages", return_value=["ru"]), \
         patch.object(SubtitlesBackend, "_fetch_via_transcript_api", fake_fetch):
        res = be.transcribe("https://www.youtube.com/watch?v=abc123", language="auto")
    assert captured["langs"] == ["ru"]
    assert res.text == "привет"
