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
