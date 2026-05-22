"""Tests for GroqBackend — Task 13.

All tests mock the groq SDK; no real API calls are made.
"""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from skills.neurolearn.backends.groq import GroqBackend
from skills.neurolearn.backends.base import BackendError, BackendNotConfigured


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_without_key():
    with patch("skills.neurolearn.backends.groq.get_api_key", return_value=None):
        ok, reason = GroqBackend(model="whisper-large-v3-turbo").is_configured()
        assert ok is False
        assert "GROQ_API_KEY" in reason


def test_is_configured_with_key():
    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="gsk_test"):
        ok, reason = GroqBackend(model="whisper-large-v3-turbo").is_configured()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# transcribe — happy path
# ---------------------------------------------------------------------------

def test_transcribe_maps_response(tmp_path: Path):
    audio = tmp_path / "a.mp3"
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

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client):
        b = GroqBackend(model="whisper-large-v3-turbo")
        result = b.transcribe(audio, language="en")

    assert result.backend_name == "groq"
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


def test_transcribe_auto_language(tmp_path: Path):
    """When language='auto' the SDK call must not pass a language arg (None)."""
    audio = tmp_path / "b.mp3"
    audio.write_bytes(b"fake")

    fake_resp = MagicMock(text="Hola.", language="es", duration=1.0, segments=[])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client):
        b = GroqBackend()
        b.transcribe(audio, language="auto")

    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs.get("language") is None


def test_transcribe_empty_segments(tmp_path: Path):
    audio = tmp_path / "c.mp3"
    audio.write_bytes(b"fake")

    fake_resp = MagicMock(text="", language="en", duration=0.0, segments=[])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client):
        result = GroqBackend().transcribe(audio)

    assert result.segments == []
    assert result.text == ""
    assert result.duration_seconds == 0.0


def test_transcribe_segments_as_objects(tmp_path: Path):
    """Segments can also be objects (attr-access style), not just dicts."""
    audio = tmp_path / "d.mp3"
    audio.write_bytes(b"fake")

    seg = MagicMock(start=0.0, end=3.0, text="  object segment  ")
    fake_resp = MagicMock(text="object segment", language="en", duration=3.0, segments=[seg])
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_resp

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client):
        result = GroqBackend().transcribe(audio)

    assert result.segments[0].text == "object segment"
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 3.0


# ---------------------------------------------------------------------------
# transcribe — error paths
# ---------------------------------------------------------------------------

def test_transcribe_raises_backend_not_configured_when_key_missing(tmp_path: Path):
    audio = tmp_path / "nokey.mp3"
    audio.write_bytes(b"fake")

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value=None):
        b = GroqBackend()
        with pytest.raises(BackendNotConfigured):
            b.transcribe(audio)


def test_transcribe_raises_backend_error_for_missing_file():
    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"):
        b = GroqBackend()
        with pytest.raises(BackendError, match="not found"):
            b.transcribe(Path("/nonexistent/path/audio.mp3"))


def test_transcribe_raises_backend_error_on_api_exception(tmp_path: Path):
    audio = tmp_path / "apierr.mp3"
    audio.write_bytes(b"fake")

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("rate limit")

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client):
        b = GroqBackend()
        with pytest.raises(BackendError, match="rate limit"):
            b.transcribe(audio)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_backend_attributes():
    b = GroqBackend()
    assert b.name == "groq"
    assert b.supports_url is False
    assert b.supports_local_file is True


def test_backend_default_model():
    b = GroqBackend()
    assert b.model == "whisper-large-v3-turbo"


def test_backend_custom_model():
    b = GroqBackend(model="whisper-large-v3")
    assert b.model == "whisper-large-v3"


# ---------------------------------------------------------------------------
# v0.14.1 — tier-aware size limits + Opus recompress + chunking
# ---------------------------------------------------------------------------

from skills.neurolearn.backends.groq import (  # noqa: E402
    _GROQ_AUDIO_LIMIT_BYTES,
    _groq_size_limit_for_tier,
)


def test_tier_limits_free_is_around_24mb():
    """Free tier should be ~24 MB (25 MB wire limit minus headroom)."""
    free = _GROQ_AUDIO_LIMIT_BYTES["free"]
    assert 23 * 1024 * 1024 < free < 25 * 1024 * 1024


def test_tier_limits_paid_is_around_98mb():
    paid = _GROQ_AUDIO_LIMIT_BYTES["paid"]
    assert 95 * 1024 * 1024 < paid < 100 * 1024 * 1024


def test_unknown_tier_falls_back_to_free():
    """Typos / unknown tiers must NOT silently get paid limits."""
    assert _groq_size_limit_for_tier("typo") == _GROQ_AUDIO_LIMIT_BYTES["free"]
    assert _groq_size_limit_for_tier(None) == _GROQ_AUDIO_LIMIT_BYTES["free"]
    assert _groq_size_limit_for_tier("") == _GROQ_AUDIO_LIMIT_BYTES["free"]


def test_prepare_uploads_returns_original_when_small(tmp_path: Path):
    """Files already under the limit are uploaded as-is, no recompress."""
    audio = tmp_path / "small.mp3"
    audio.write_bytes(b"a" * 1024)  # 1 KB, way under any limit

    b = GroqBackend(tier="free")
    uploads, tmp_recompress = b._prepare_uploads(audio)

    assert uploads == [(audio, 0.0)]
    assert tmp_recompress is None


def test_prepare_uploads_recompresses_when_over_limit(tmp_path: Path):
    """Files over the limit get Opus-recompressed; if the recompressed
    file fits the limit we upload it as a single chunk."""
    audio = tmp_path / "big.m4a"
    # Make file appear larger than free-tier limit
    audio.write_bytes(b"x" * (30 * 1024 * 1024))

    def fake_recompress(src: Path, dst: Path) -> None:
        # Simulate ffmpeg producing a small file
        dst.write_bytes(b"opus" * 1024)  # 4 KB

    b = GroqBackend(tier="free")
    with patch(
        "skills.neurolearn.backends.groq._recompress_audio_for_groq",
        side_effect=fake_recompress,
    ):
        uploads, tmp_recompress = b._prepare_uploads(audio)

    assert len(uploads) == 1
    upload_path, offset = uploads[0]
    assert upload_path != audio
    assert upload_path.suffix == ".ogg"
    assert offset == 0.0
    assert tmp_recompress == upload_path
    # cleanup
    if upload_path.exists():
        upload_path.unlink()


def test_prepare_uploads_chunks_when_recompress_still_too_big(tmp_path: Path):
    """When even Opus recompress exceeds the limit, the chunker
    splits the file. v0.14.0 used to BackendError here, v0.14.1
    chunks transparently."""
    audio = tmp_path / "huge.m4a"
    audio.write_bytes(b"x" * (50 * 1024 * 1024))   # 50 MB pre-recompress

    def fake_recompress(src: Path, dst: Path) -> None:
        # Recompressed file is still 30 MB — over free-tier limit
        dst.write_bytes(b"y" * (30 * 1024 * 1024))

    fake_chunks = [
        (tmp_path / "huge_groq_compress_chunk01.ogg", 0.0),
        (tmp_path / "huge_groq_compress_chunk02.ogg", 1200.0),
    ]
    for p, _ in fake_chunks:
        p.write_bytes(b"z" * (12 * 1024 * 1024))

    b = GroqBackend(tier="free")
    with patch(
        "skills.neurolearn.backends.groq._recompress_audio_for_groq",
        side_effect=fake_recompress,
    ), patch(
        "skills.neurolearn.utils.audio_chunker.prepare_chunks",
        return_value=fake_chunks,
    ):
        uploads, tmp_recompress = b._prepare_uploads(audio)

    assert uploads == fake_chunks
    assert tmp_recompress is not None
    assert tmp_recompress.suffix == ".ogg"


def test_transcribe_chunked_offsets_segment_timestamps(tmp_path: Path):
    """The critical guarantee: when chunking kicks in, each segment's
    timestamp in the returned result is offset by its chunk's start
    position. End-to-end timeline must match the original video."""
    audio = tmp_path / "long.m4a"
    audio.write_bytes(b"fake")

    chunk1 = tmp_path / "long_chunk01.ogg"
    chunk2 = tmp_path / "long_chunk02.ogg"
    chunk1.write_bytes(b"c1")
    chunk2.write_bytes(b"c2")

    # Chunk 1 starts at 0s, chunk 2 starts at 100s.
    fake_uploads = [(chunk1, 0.0), (chunk2, 100.0)]

    # Each chunk's response has segments expressed relative to its own
    # start; reassembly must add the offset.
    # Use realistic char-density so segments survive the v0.14.2
    # hallucination filter (≥ 2 cps).
    resp1 = MagicMock(
        text="Hello, this is the first chunk of real speech.",
        language="en",
        duration=10.0,
        segments=[{
            "start": 0.0, "end": 5.0,
            "text": "Hello, this is the first chunk of real speech.",
        }],
    )
    resp2 = MagicMock(
        text="And here is the second chunk continuing the talk.",
        language="en",
        duration=15.0,
        segments=[{
            "start": 0.0, "end": 8.0,
            "text": "And here is the second chunk continuing the talk.",
        }],
    )
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = [resp1, resp2]

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client), \
         patch.object(GroqBackend, "_prepare_uploads", return_value=(fake_uploads, None)):
        result = GroqBackend(tier="free").transcribe(audio)

    # The second chunk's segment must be offset to absolute timeline.
    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 5.0
    assert result.segments[0].text.startswith("Hello")
    assert result.segments[1].start == 100.0   # offset applied
    assert result.segments[1].end == 108.0     # offset applied
    assert result.segments[1].text.startswith("And here")

    # Texts are joined; durations summed
    assert "Hello" in result.text and "second chunk" in result.text
    assert result.duration_seconds == 25.0


def test_transcribe_chunked_calls_groq_once_per_chunk(tmp_path: Path):
    """Three chunks → three SDK calls. Catches a regression where
    we only upload the first chunk."""
    audio = tmp_path / "long.m4a"
    audio.write_bytes(b"fake")

    chunks = [
        (tmp_path / f"c{i}.ogg", float(i * 200))
        for i in range(3)
    ]
    for p, _ in chunks:
        p.write_bytes(b"c")

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = MagicMock(
        text="x", language="en", duration=1.0, segments=[],
    )

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client), \
         patch.object(GroqBackend, "_prepare_uploads", return_value=(chunks, None)):
        GroqBackend(tier="free").transcribe(audio)

    assert fake_client.audio.transcriptions.create.call_count == 3


def test_transcribe_chunked_cleans_up_temp_files(tmp_path: Path):
    """After a successful chunked transcribe, the chunk files AND
    the recompress temp must be deleted. The user's original file
    must NOT be touched."""
    audio = tmp_path / "long.m4a"
    audio.write_bytes(b"original")

    chunk1 = tmp_path / "long_chunk01.ogg"
    chunk2 = tmp_path / "long_chunk02.ogg"
    recompress = tmp_path / "long_groq_compress.ogg"
    chunk1.write_bytes(b"c1")
    chunk2.write_bytes(b"c2")
    recompress.write_bytes(b"opus")

    fake_uploads = [(chunk1, 0.0), (chunk2, 100.0)]

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = MagicMock(
        text="x", language="en", duration=1.0, segments=[],
    )

    with patch("skills.neurolearn.backends.groq.get_api_key", return_value="x"), \
         patch("skills.neurolearn.backends.groq._build_client", return_value=fake_client), \
         patch.object(GroqBackend, "_prepare_uploads",
                      return_value=(fake_uploads, recompress)):
        GroqBackend(tier="free").transcribe(audio)

    assert audio.exists(), "user's original file must survive"
    assert not chunk1.exists(), "chunk files should be cleaned up"
    assert not chunk2.exists(), "chunk files should be cleaned up"
    assert not recompress.exists(), "recompress temp should be cleaned up"
