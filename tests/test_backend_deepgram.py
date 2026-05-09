"""Tests for DeepgramBackend — Task 15.

All tests mock the deepgram SDK; no real API calls are made.
SDK version: deepgram-sdk>=7.x
API path: client.listen.v1.media.transcribe_file(request=bytes_data, ...)
Response: Pydantic model (accessed via .results.channels[0].alternatives[0].words)
"""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from skills.youtube_transcribe.backends.deepgram import DeepgramBackend, _group_words_into_segments
from skills.youtube_transcribe.backends.base import BackendError, BackendNotConfigured


# ---------------------------------------------------------------------------
# Helpers — build fake Pydantic-like response objects using MagicMock
# ---------------------------------------------------------------------------

def _make_word(word: str, start: float, end: float):
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    w.confidence = 0.99
    return w


def _make_response(words: list, detected_language: str | None = "en", transcript: str = ""):
    """Build a fake deepgram response matching .results.channels[0].alternatives[0]."""
    alt = MagicMock()
    alt.words = words
    alt.transcript = transcript

    channel = MagicMock()
    channel.alternatives = [alt]
    channel.detected_language = detected_language

    results = MagicMock()
    results.channels = [channel]

    resp = MagicMock()
    resp.results = results
    return resp


# ---------------------------------------------------------------------------
# _group_words_into_segments unit tests
# ---------------------------------------------------------------------------

def test_group_empty_words():
    assert _group_words_into_segments([]) == []


def test_group_single_sentence():
    words = [
        _make_word("Hello", 0.0, 0.5),
        _make_word("world.", 0.5, 1.0),
    ]
    segs = _group_words_into_segments(words)
    assert len(segs) == 1
    assert segs[0].text == "Hello world."
    assert segs[0].start == 0.0
    assert segs[0].end == 1.0


def test_group_two_sentences_by_punctuation():
    words = [
        _make_word("Hello", 0.0, 0.5),
        _make_word("world.", 0.5, 1.0),
        _make_word("Second", 1.5, 2.0),
        _make_word("sentence.", 2.0, 2.5),
    ]
    segs = _group_words_into_segments(words)
    assert len(segs) == 2
    assert segs[0].text == "Hello world."
    assert segs[0].start == 0.0
    assert segs[0].end == 1.0
    assert segs[1].text == "Second sentence."
    assert segs[1].start == 1.5
    assert segs[1].end == 2.5


def test_group_question_mark_ends_segment():
    words = [
        _make_word("Really?", 0.0, 0.8),
        _make_word("Yes!", 1.0, 1.5),
    ]
    segs = _group_words_into_segments(words)
    assert len(segs) == 2
    assert segs[0].text == "Really?"
    assert segs[1].text == "Yes!"


def test_group_gap_triggers_new_segment():
    """A pause >1.0 s between words should start a new segment."""
    words = [
        _make_word("First", 0.0, 0.5),
        _make_word("part", 0.5, 0.8),
        # gap of 2s → new segment
        _make_word("second", 2.9, 3.2),
        _make_word("part", 3.2, 3.6),
    ]
    segs = _group_words_into_segments(words)
    assert len(segs) == 2
    assert segs[0].text == "First part"
    assert segs[1].text == "second part"


def test_group_max_words_limit():
    """Segments must not exceed 15 words (even without punctuation or gap)."""
    words = [_make_word(f"word{i}", float(i), float(i) + 0.5) for i in range(20)]
    segs = _group_words_into_segments(words)
    for seg in segs[:-1]:  # last segment may have fewer
        word_count = len(seg.text.split())
        assert word_count <= 15


def test_group_trailing_words_without_punctuation():
    """Words remaining after last sentence boundary form a final segment."""
    words = [
        _make_word("First.", 0.0, 0.5),
        _make_word("trailing", 0.6, 0.9),
        _make_word("words", 0.9, 1.2),
    ]
    segs = _group_words_into_segments(words)
    assert len(segs) == 2
    assert segs[-1].text == "trailing words"


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_without_key():
    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value=None):
        ok, reason = DeepgramBackend(model="nova-3").is_configured()
        assert ok is False
        assert "DEEPGRAM_API_KEY" in reason


def test_is_configured_with_key():
    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="dg_test"):
        ok, reason = DeepgramBackend(model="nova-3").is_configured()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# transcribe — happy path
# ---------------------------------------------------------------------------

def test_transcribe_maps_words_to_segments(tmp_path: Path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    words = [
        _make_word("Hello", 0.0, 0.5),
        _make_word("world.", 0.5, 1.0),
        _make_word("Second", 1.5, 2.0),
        _make_word("sentence.", 2.0, 2.5),
    ]
    fake_response = _make_response(words, detected_language="en",
                                   transcript="Hello world. Second sentence.")
    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.return_value = fake_response

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        b = DeepgramBackend(model="nova-3")
        result = b.transcribe(audio, language="en")

    assert result.backend_name == "deepgram"
    assert result.language_detected == "en"
    assert result.text == "Hello world. Second sentence."
    # Two sentences → two segments grouped by sentence-ending punctuation
    assert len(result.segments) == 2
    assert result.segments[0].text.startswith("Hello")
    assert result.segments[1].text.startswith("Second")


def test_transcribe_auto_language_passes_detect_language(tmp_path: Path):
    """When language='auto', detect_language=True and no language param."""
    audio = tmp_path / "b.mp3"
    audio.write_bytes(b"fake")

    words = [_make_word("Hola.", 0.0, 0.5)]
    fake_response = _make_response(words, detected_language="es", transcript="Hola.")
    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.return_value = fake_response

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        result = DeepgramBackend().transcribe(audio, language="auto")

    call_kwargs = fake_client.listen.v1.media.transcribe_file.call_args.kwargs
    assert call_kwargs.get("detect_language") is True
    assert call_kwargs.get("language") is None
    assert result.language_detected == "es"


def test_transcribe_specific_language(tmp_path: Path):
    """When language is specified, detect_language=False and language is passed."""
    audio = tmp_path / "c.mp3"
    audio.write_bytes(b"fake")

    words = [_make_word("Bonjour.", 0.0, 0.5)]
    fake_response = _make_response(words, detected_language=None, transcript="Bonjour.")
    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.return_value = fake_response

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        result = DeepgramBackend().transcribe(audio, language="fr")

    call_kwargs = fake_client.listen.v1.media.transcribe_file.call_args.kwargs
    assert call_kwargs.get("language") == "fr"
    assert call_kwargs.get("detect_language") is False


def test_transcribe_empty_words(tmp_path: Path):
    audio = tmp_path / "d.mp3"
    audio.write_bytes(b"fake")

    fake_response = _make_response([], detected_language="en", transcript="")
    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.return_value = fake_response

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        result = DeepgramBackend().transcribe(audio)

    assert result.segments == []
    assert result.text == ""
    assert result.duration_seconds == 0.0


def test_transcribe_duration_from_last_segment(tmp_path: Path):
    audio = tmp_path / "e.mp3"
    audio.write_bytes(b"fake")

    words = [
        _make_word("Hello", 0.0, 0.5),
        _make_word("world.", 0.5, 3.7),
    ]
    fake_response = _make_response(words, detected_language="en", transcript="Hello world.")
    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.return_value = fake_response

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        result = DeepgramBackend().transcribe(audio)

    assert result.duration_seconds == pytest.approx(3.7)


# ---------------------------------------------------------------------------
# transcribe — error paths
# ---------------------------------------------------------------------------

def test_transcribe_raises_backend_not_configured_when_key_missing(tmp_path: Path):
    audio = tmp_path / "nokey.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value=None):
        b = DeepgramBackend()
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_for_missing_file():
    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"):
        b = DeepgramBackend()
        with pytest.raises(BackendError, match="not found"):
            b.transcribe(Path("/nonexistent/path/audio.mp3"))


def test_transcribe_raises_backend_error_on_api_exception(tmp_path: Path):
    audio = tmp_path / "apierr.mp3"
    audio.write_bytes(b"fake")

    fake_client = MagicMock()
    fake_client.listen.v1.media.transcribe_file.side_effect = RuntimeError("rate limit")

    with patch("skills.youtube_transcribe.backends.deepgram.get_api_key", return_value="x"), \
         patch("skills.youtube_transcribe.backends.deepgram._build_client", return_value=fake_client):
        b = DeepgramBackend()
        with pytest.raises(BackendError, match="rate limit"):
            b.transcribe(audio)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_backend_attributes():
    b = DeepgramBackend()
    assert b.name == "deepgram"
    assert b.supports_url is False
    assert b.supports_local_file is True


def test_backend_default_model():
    b = DeepgramBackend()
    assert b.model == "nova-3"


def test_backend_custom_model():
    b = DeepgramBackend(model="nova-2")
    assert b.model == "nova-2"
