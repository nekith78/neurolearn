"""Tests for GeminiBackend — Task 12.

All tests mock google-genai SDK; no real API calls are made.
"""
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from skills.neurolearn.backends.gemini import GeminiBackend
from skills.neurolearn.backends.base import BackendError, BackendNotConfigured


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_without_key(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value=None):
        b = GeminiBackend(model="gemini-2.5-flash")
        ok, reason = b.is_configured()
        assert ok is False
        assert "GEMINI_API_KEY" in reason


def test_is_configured_with_key():
    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"):
        b = GeminiBackend(model="gemini-2.5-flash")
        ok, reason = b.is_configured()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# transcribe — happy path
# ---------------------------------------------------------------------------

def test_transcribe_parses_json_response(tmp_path: Path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_response = MagicMock()
    fake_response.text = json.dumps({
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "Hello"},
            {"start": 2.0, "end": 4.0, "text": "World"},
        ],
    })
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/abc")
    fake_client.models.generate_content.return_value = fake_response

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.gemini._build_client", return_value=fake_client):
        b = GeminiBackend(model="gemini-2.5-flash")
        result = b.transcribe(audio, language="en")

    assert result.backend_name == "gemini"
    assert result.language_detected == "en"
    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello"
    assert result.segments[1].text == "World"
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 2.0
    assert result.text == "Hello World"


def test_transcribe_duration_from_last_segment(tmp_path: Path):
    audio = tmp_path / "b.mp3"
    audio.write_bytes(b"fake")

    fake_response = MagicMock()
    fake_response.text = json.dumps({
        "language": "fr",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Bonjour"},
        ],
    })
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.gemini._build_client", return_value=fake_client):
        b = GeminiBackend(model="gemini-2.5-flash")
        result = b.transcribe(audio, language="fr")

    assert result.duration_seconds == 5.0
    assert result.language_detected == "fr"


def test_transcribe_strips_markdown_fences(tmp_path: Path):
    """Gemini sometimes wraps JSON in ```json ... ``` — we must strip it."""
    audio = tmp_path / "c.mp3"
    audio.write_bytes(b"fake")

    payload = json.dumps({
        "language": "de",
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hallo"}],
    })
    fake_response = MagicMock()
    fake_response.text = f"```json\n{payload}\n```"
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.gemini._build_client", return_value=fake_client):
        b = GeminiBackend(model="gemini-2.5-flash")
        result = b.transcribe(audio)

    assert result.language_detected == "de"
    assert result.segments[0].text == "Hallo"


# ---------------------------------------------------------------------------
# transcribe — error paths
# ---------------------------------------------------------------------------

def test_transcribe_raises_backend_error_on_malformed_json(tmp_path: Path):
    audio = tmp_path / "bad.mp3"
    audio.write_bytes(b"fake")

    fake_response = MagicMock()
    fake_response.text = "This is not JSON at all"
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.gemini._build_client", return_value=fake_client):
        b = GeminiBackend(model="gemini-2.5-flash")
        with pytest.raises(BackendError):
            b.transcribe(audio)


def test_transcribe_raises_backend_not_configured_when_key_missing(tmp_path: Path):
    audio = tmp_path / "nokey.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value=None):
        b = GeminiBackend(model="gemini-2.5-flash")
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_on_api_exception(tmp_path: Path):
    audio = tmp_path / "apierr.mp3"
    audio.write_bytes(b"fake")

    fake_client = MagicMock()
    fake_client.files.upload.side_effect = RuntimeError("network timeout")

    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.gemini._build_client", return_value=fake_client):
        b = GeminiBackend(model="gemini-2.5-flash")
        with pytest.raises(BackendError, match="network timeout"):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_for_missing_file():
    with patch("skills.neurolearn.backends.gemini.get_api_key", return_value="x"):
        b = GeminiBackend(model="gemini-2.5-flash")
        with pytest.raises(BackendError, match="not found"):
            b.transcribe(Path("/nonexistent/path/audio.mp3"))


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_backend_attributes():
    b = GeminiBackend()
    assert b.name == "gemini"
    assert b.supports_url is False
    assert b.supports_local_file is True


def test_backend_default_model():
    b = GeminiBackend()
    assert b.model == "gemini-2.5-flash"


def test_backend_custom_model():
    b = GeminiBackend(model="gemini-2.5-pro")
    assert b.model == "gemini-2.5-pro"
