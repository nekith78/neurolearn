"""Tests for CustomBackend — Task 17.

All tests mock the openai SDK; no real API calls are made.
"""
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import pytest

from skills.neurolearn.backends.custom import CustomBackend
from skills.neurolearn.backends.base import BackendError, BackendNotConfigured


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_requires_base_url():
    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="x"):
        b = CustomBackend(base_url="", model="m")
        ok, reason = b.is_configured()
        assert ok is False
        assert "base_url" in reason


def test_is_configured_requires_model():
    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="x"):
        b = CustomBackend(base_url="https://api.example.com/v1", model="")
        ok, reason = b.is_configured()
        assert ok is False
        assert "model" in reason


def test_is_configured_requires_key():
    with patch("skills.neurolearn.backends.custom.get_api_key", return_value=None):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        ok, reason = b.is_configured()
        assert ok is False
        assert "CUSTOM_API_KEY" in reason or "key" in reason.lower()


def test_is_configured_all_set():
    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="x"):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        ok, reason = b.is_configured()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# transcribe — happy path
# ---------------------------------------------------------------------------

def test_transcribe_uses_openai_sdk_with_base_url(tmp_path: Path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_resp = MagicMock(text="Hi.", language="en", duration=1.0, segments=[])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.custom._build_client", return_value=fake_client) as mock_build:
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        result = b.transcribe(audio, language="en")

    mock_build.assert_called_once_with("x", "https://api.example.com/v1")
    assert result.backend_name == "custom"
    assert result.text == "Hi."


def test_transcribe_maps_response(tmp_path: Path):
    audio = tmp_path / "b.mp3"
    audio.write_bytes(b"fake")

    fake_resp = MagicMock(
        text="Hello world.",
        language="en",
        duration=2.5,
        segments=[
            {"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.5, "text": "world."},
        ],
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"), \
         patch("skills.neurolearn.backends.custom._build_client", return_value=fake_client):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        result = b.transcribe(audio, language="en")

    assert result.text == "Hello world."
    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 1.0
    assert result.segments[0].text == "Hello"
    assert result.segments[1].start == 1.0
    assert result.segments[1].end == 2.5
    assert result.segments[1].text == "world."
    assert result.language_detected == "en"
    assert result.duration_seconds == 2.5


def test_transcribe_auto_language_passes_none(tmp_path: Path):
    """When language='auto' the SDK call must receive language=None."""
    audio = tmp_path / "c.mp3"
    audio.write_bytes(b"fake")

    fake_resp = MagicMock(text="Hola.", language="es", duration=1.0, segments=[])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"), \
         patch("skills.neurolearn.backends.custom._build_client", return_value=fake_client):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        b.transcribe(audio, language="auto")

    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs.get("language") is None


def test_transcribe_segments_as_objects(tmp_path: Path):
    """Segments can also be objects (attr-access style), not just dicts."""
    audio = tmp_path / "d.mp3"
    audio.write_bytes(b"fake")

    seg = MagicMock(start=0.0, end=3.0, text="  object segment  ")
    fake_resp = MagicMock(text="object segment", language="en", duration=3.0, segments=[seg])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"), \
         patch("skills.neurolearn.backends.custom._build_client", return_value=fake_client):
        result = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper").transcribe(audio)

    assert result.segments[0].text == "object segment"
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 3.0


# ---------------------------------------------------------------------------
# transcribe — error paths
# ---------------------------------------------------------------------------

def test_transcribe_raises_backend_error_for_missing_file():
    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        with pytest.raises(BackendError, match="not found"):
            b.transcribe(Path("/nonexistent/path/audio.mp3"))


def test_transcribe_raises_backend_not_configured_when_key_missing(tmp_path: Path):
    audio = tmp_path / "nokey.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value=None):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_not_configured_when_base_url_missing(tmp_path: Path):
    audio = tmp_path / "nourl.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"):
        b = CustomBackend(base_url="", model="my-whisper")
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_not_configured_when_model_missing(tmp_path: Path):
    audio = tmp_path / "nomodel.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"):
        b = CustomBackend(base_url="https://api.example.com/v1", model="")
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_on_api_exception(tmp_path: Path):
    audio = tmp_path / "apierr.mp3"
    audio.write_bytes(b"fake")

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("upstream down")

    with patch("skills.neurolearn.backends.custom.get_api_key", return_value="sk-x"), \
         patch("skills.neurolearn.backends.custom._build_client", return_value=fake_client):
        b = CustomBackend(base_url="https://api.example.com/v1", model="my-whisper")
        with pytest.raises(BackendError, match="upstream down"):
            b.transcribe(audio)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_backend_attributes():
    b = CustomBackend()
    assert b.name == "custom"
    assert b.supports_url is False
    assert b.supports_local_file is True


def test_backend_default_config():
    b = CustomBackend()
    assert b.base_url == ""
    assert b.model == ""


def test_backend_custom_config():
    b = CustomBackend(base_url="https://my.api/v1", model="my-model")
    assert b.base_url == "https://my.api/v1"
    assert b.model == "my-model"
