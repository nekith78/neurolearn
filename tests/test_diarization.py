"""Tests for speaker diarization. pyannote.Pipeline mocked."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.neurolearn.quality import diarization
from skills.neurolearn.quality.diarization import (
    attach_speakers_to_segments,
    diarize_audio,
    is_diarization_available,
)
from skills.neurolearn.utils.output_writer import Segment


def _s(start, end, text):
    return Segment(start=start, end=end, text=text)


def _fake_annotation(intervals):
    """Build a fake pyannote Annotation object with itertracks() output."""
    ann = MagicMock()

    def _iter(yield_label=True):
        for start, end, label in intervals:
            turn = MagicMock()
            turn.start = start
            turn.end = end
            yield (turn, None, label)

    ann.itertracks = _iter
    return ann


# === diarize_audio ===

def test_diarize_audio_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    out = diarize_audio(Path("fake.mp3"))
    assert out == []


def test_diarize_audio_calls_pipeline(monkeypatch, tmp_path):
    fake_pipeline = MagicMock()
    fake_pipeline.return_value = _fake_annotation([
        (0.0, 5.5, "SPEAKER_00"),
        (5.5, 10.0, "SPEAKER_01"),
        (10.0, 15.0, "SPEAKER_00"),
    ])

    monkeypatch.setattr(diarization, "_get_pipeline", lambda token: fake_pipeline)
    monkeypatch.setenv("HF_TOKEN", "fake-token")

    out = diarize_audio(tmp_path / "audio.mp3")
    assert len(out) == 3
    assert out[0] == (0.0, 5.5, "SPEAKER_00")
    assert out[2] == (10.0, 15.0, "SPEAKER_00")


def test_diarize_audio_pipeline_failure_returns_empty(monkeypatch, tmp_path):
    def boom(token):
        raise RuntimeError("pyannote load failed (auth?)")

    monkeypatch.setattr(diarization, "_get_pipeline", boom)
    monkeypatch.setenv("HF_TOKEN", "x")
    out = diarize_audio(tmp_path / "audio.mp3")
    assert out == []


def test_diarize_audio_pipeline_runtime_error_returns_empty(monkeypatch, tmp_path):
    fake_pipeline = MagicMock(side_effect=RuntimeError("CUDA OOM"))
    monkeypatch.setattr(diarization, "_get_pipeline", lambda token: fake_pipeline)
    monkeypatch.setenv("HF_TOKEN", "x")
    out = diarize_audio(tmp_path / "audio.mp3")
    assert out == []


def test_diarize_audio_num_speakers_passed_through(monkeypatch, tmp_path):
    fake_pipeline = MagicMock(return_value=_fake_annotation([]))
    monkeypatch.setattr(diarization, "_get_pipeline", lambda token: fake_pipeline)
    monkeypatch.setenv("HF_TOKEN", "x")

    diarize_audio(tmp_path / "audio.mp3", num_speakers=3)
    # The pipeline was called with num_speakers kwarg
    call = fake_pipeline.call_args
    assert call.kwargs.get("num_speakers") == 3


# === is_diarization_available ===

def test_is_available_no_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    assert is_diarization_available() is False


def test_is_available_with_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake")
    # Whether pyannote is installed or not depends on env. Both branches OK.
    result = is_diarization_available()
    assert isinstance(result, bool)


# === attach_speakers_to_segments ===

def test_attach_speakers_single_speaker():
    segs = [_s(0.0, 5.0, "hello"), _s(5.0, 10.0, "world")]
    intervals = [(0.0, 10.0, "SPEAKER_00")]
    out = attach_speakers_to_segments(segs, intervals)
    assert out[0].text == "[SPEAKER_00] hello"
    assert out[1].text == "[SPEAKER_00] world"
    # Timing preserved
    assert out[0].start == 0.0
    assert out[0].end == 5.0


def test_attach_speakers_changeover():
    segs = [
        _s(0.0, 3.0, "first"),    # speaker A
        _s(3.0, 7.0, "middle"),   # overlap, but more in B
        _s(7.0, 10.0, "third"),   # speaker B
    ]
    intervals = [
        (0.0, 4.0, "SPEAKER_A"),
        (4.0, 10.0, "SPEAKER_B"),
    ]
    out = attach_speakers_to_segments(segs, intervals)
    assert out[0].text == "[SPEAKER_A] first"
    # Middle segment: overlap with A = 1s (3-4), with B = 3s (4-7) → B wins
    assert out[1].text == "[SPEAKER_B] middle"
    assert out[2].text == "[SPEAKER_B] third"


def test_attach_speakers_no_overlap_leaves_unchanged():
    segs = [_s(0.0, 5.0, "hello")]
    intervals = [(20.0, 30.0, "SPEAKER_00")]
    out = attach_speakers_to_segments(segs, intervals)
    assert out[0].text == "hello"  # no prefix


def test_attach_speakers_empty_diarization():
    segs = [_s(0.0, 5.0, "hello")]
    out = attach_speakers_to_segments(segs, [])
    assert out == segs


def test_attach_speakers_empty_segments():
    out = attach_speakers_to_segments([], [(0, 1, "S")])
    assert out == []
