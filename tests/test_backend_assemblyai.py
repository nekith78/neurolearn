"""Tests for AssemblyAIBackend — Task 16.

All tests mock the assemblyai SDK; no real API calls are made.
SDK version: assemblyai>=0.64.0
API: aai.settings.api_key = key; aai.Transcriber(config=...).transcribe(path)
Response: Transcript object with .text, .language_code, .audio_duration, .utterances
Utterances: objects with .start (ms), .end (ms), .text
"""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from skills.youtube_transcribe.backends.assemblyai import AssemblyAIBackend
from skills.youtube_transcribe.backends.base import BackendError, BackendNotConfigured


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_without_key():
    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value=None):
        ok, reason = AssemblyAIBackend(model="best").is_configured()
        assert ok is False
        assert "ASSEMBLYAI_API_KEY" in reason


def test_is_configured_with_key():
    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="aai_test"):
        ok, reason = AssemblyAIBackend(model="best").is_configured()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# transcribe — happy path
# ---------------------------------------------------------------------------

def test_transcribe_uses_utterances(tmp_path: Path):
    """Utterances are mapped to segments, timestamps converted from ms → s."""
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="Hello. World.",
        language_code="en",
        audio_duration=4.0,
        utterances=[
            MagicMock(start=0, end=2000, text="Hello."),
            MagicMock(start=2000, end=4000, text="World."),
        ],
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        b = AssemblyAIBackend(model="best")
        result = b.transcribe(audio, language="en")

    assert result.backend_name == "assemblyai"
    assert result.language_detected == "en"
    assert result.text == "Hello. World."
    assert len(result.segments) == 2
    # Utterance times are in milliseconds → must be converted to seconds
    assert result.segments[0].start == pytest.approx(0.0)
    assert result.segments[0].end == pytest.approx(2.0)
    assert result.segments[1].start == pytest.approx(2.0)
    assert result.segments[1].end == pytest.approx(4.0)


def test_transcribe_ms_to_seconds_conversion(tmp_path: Path):
    """Critical: AssemblyAI returns ms, our Segment uses seconds (divide by 1000)."""
    audio = tmp_path / "ms_test.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="Some text.",
        language_code="en",
        audio_duration=10.5,
        utterances=[
            MagicMock(start=5000, end=10500, text="Some text."),
        ],
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        result = AssemblyAIBackend().transcribe(audio)

    # 5000 ms → 5.0 s, 10500 ms → 10.5 s
    assert result.segments[0].start == pytest.approx(5.0)
    assert result.segments[0].end == pytest.approx(10.5)


def test_transcribe_auto_language(tmp_path: Path):
    """When language='auto', no language_code should constrain the request."""
    audio = tmp_path / "auto.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="Hola.",
        language_code="es",
        audio_duration=1.0,
        utterances=[MagicMock(start=0, end=1000, text="Hola.")],
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        result = AssemblyAIBackend().transcribe(audio, language="auto")

    assert result.language_detected == "es"
    assert result.segments[0].start == pytest.approx(0.0)
    assert result.segments[0].end == pytest.approx(1.0)


def test_transcribe_empty_utterances(tmp_path: Path):
    """Empty utterances → empty segments, no crash."""
    audio = tmp_path / "empty.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="",
        language_code=None,
        audio_duration=0.0,
        utterances=[],
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        result = AssemblyAIBackend().transcribe(audio)

    assert result.segments == []
    assert result.text == ""
    assert result.duration_seconds == pytest.approx(0.0)


def test_transcribe_duration_from_audio_duration(tmp_path: Path):
    """duration_seconds is taken from transcript.audio_duration."""
    audio = tmp_path / "dur.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="Test.",
        language_code="en",
        audio_duration=42.7,
        utterances=[MagicMock(start=0, end=5000, text="Test.")],
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        result = AssemblyAIBackend().transcribe(audio)

    assert result.duration_seconds == pytest.approx(42.7)


def test_transcribe_utterances_none_fallback(tmp_path: Path):
    """If transcript.utterances is None, segments should be empty."""
    audio = tmp_path / "noutts.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text="Something.",
        language_code="en",
        audio_duration=5.0,
        utterances=None,
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        result = AssemblyAIBackend().transcribe(audio)

    assert result.segments == []
    assert result.text == "Something."


# ---------------------------------------------------------------------------
# transcribe — error paths
# ---------------------------------------------------------------------------

def test_transcribe_raises_backend_not_configured_when_key_missing(tmp_path: Path):
    audio = tmp_path / "nokey.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value=None):
        b = AssemblyAIBackend()
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_for_missing_file():
    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"):
        b = AssemblyAIBackend()
        with pytest.raises(BackendError, match="not found"):
            b.transcribe(Path("/nonexistent/path/audio.mp3"))


def test_transcribe_raises_backend_error_on_api_exception(tmp_path: Path):
    audio = tmp_path / "apierr.mp3"
    audio.write_bytes(b"fake")

    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.side_effect = RuntimeError("rate limited")

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        b = AssemblyAIBackend()
        with pytest.raises(BackendError, match="rate limited"):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_on_transcript_error(tmp_path: Path):
    """If transcript has .error set (status=ERROR), raise BackendError."""
    audio = tmp_path / "txterr.mp3"
    audio.write_bytes(b"fake")

    fake_transcript = MagicMock(
        text=None,
        language_code=None,
        audio_duration=0.0,
        utterances=None,
        error="Audio file could not be transcribed.",
    )
    fake_transcriber = MagicMock()
    fake_transcriber.transcribe.return_value = fake_transcript

    with patch("skills.youtube_transcribe.backends.assemblyai.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.assemblyai._build_transcriber", return_value=fake_transcriber):
        b = AssemblyAIBackend()
        with pytest.raises(BackendError, match="Audio file could not be transcribed"):
            b.transcribe(audio)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_backend_attributes():
    b = AssemblyAIBackend()
    assert b.name == "assemblyai"
    assert b.supports_url is False
    assert b.supports_local_file is True


def test_backend_default_model():
    b = AssemblyAIBackend()
    assert b.model == "best"


def test_backend_nano_model():
    b = AssemblyAIBackend(model="nano")
    assert b.model == "nano"
