"""Unit tests for utils.audio_chunker — pure-logic tests with no ffmpeg shell-outs."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skills.neurolearn.utils import audio_chunker
from skills.neurolearn.utils.audio_chunker import (
    SilenceInterval,
    compute_chunk_count,
    plan_chunk_boundaries,
)


# ---------------------------------------------------------------------------
# compute_chunk_count
# ---------------------------------------------------------------------------

def test_compute_chunk_count_under_limit_returns_1():
    assert compute_chunk_count(10_000, 100_000) == 1


def test_compute_chunk_count_doubles_when_just_over():
    # 200k file, 100k limit → at least 2 (with 5% headroom: ceil(200k / 95k) = 3)
    n = compute_chunk_count(200_000, 100_000)
    assert n >= 2


def test_compute_chunk_count_scales_with_size():
    n2 = compute_chunk_count(50 * 1024 * 1024, 24 * 1024 * 1024)
    n3 = compute_chunk_count(100 * 1024 * 1024, 24 * 1024 * 1024)
    assert n3 > n2


def test_compute_chunk_count_minimum_2_when_chunking():
    """When file exceeds limit, we never return 1 even with tiny excess."""
    # 1 byte over limit: still must split (otherwise upload fails)
    assert compute_chunk_count(101, 100) >= 2


# ---------------------------------------------------------------------------
# plan_chunk_boundaries
# ---------------------------------------------------------------------------

def test_plan_chunk_boundaries_uses_silence_when_available():
    """When silence is near the ideal cut, plan should snap to it."""
    duration = 100.0
    # Ideal cut for N=2 is at t=50. Silence at [48, 52].
    silences = [SilenceInterval(start=48.0, end=52.0)]
    cuts, warnings = plan_chunk_boundaries(duration, 2, silences)
    assert len(cuts) == 1
    assert 48.0 <= cuts[0] <= 52.0
    assert warnings == []


def test_plan_chunk_boundaries_picks_closest_silence():
    """If multiple silences overlap the search window, pick the one
    closest to the ideal cut."""
    duration = 100.0
    silences = [
        SilenceInterval(start=40.0, end=42.0),    # mid 41
        SilenceInterval(start=49.0, end=51.0),    # mid 50 (ideal)
        SilenceInterval(start=58.0, end=60.0),    # mid 59
    ]
    cuts, _ = plan_chunk_boundaries(duration, 2, silences)
    # Cut should land in the middle silence (closest to t=50)
    assert 49.0 <= cuts[0] <= 51.0


def test_plan_chunk_boundaries_falls_back_when_no_silence():
    """If no silence falls anywhere in the search window, the
    boundary is placed at the exact ideal cut and a warning is added."""
    duration = 100.0
    # All silences far from the ideal cut at t=50
    silences = [SilenceInterval(start=0.0, end=1.0), SilenceInterval(start=99.0, end=99.5)]
    cuts, warnings = plan_chunk_boundaries(duration, 2, silences)
    assert cuts == [50.0]
    assert len(warnings) == 1
    assert "No silence" in warnings[0]


def test_plan_chunk_boundaries_n_equals_3_produces_2_cuts():
    duration = 300.0
    silences = [
        SilenceInterval(start=99.5, end=100.5),
        SilenceInterval(start=199.5, end=200.5),
    ]
    cuts, warnings = plan_chunk_boundaries(duration, 3, silences)
    assert len(cuts) == 2
    assert warnings == []
    assert 99.5 <= cuts[0] <= 100.5
    assert 199.5 <= cuts[1] <= 200.5


def test_plan_chunk_boundaries_cuts_monotonically_increase():
    duration = 600.0
    silences = [SilenceInterval(start=i * 100 - 2, end=i * 100 + 2) for i in range(1, 6)]
    cuts, _ = plan_chunk_boundaries(duration, 5, silences)
    assert cuts == sorted(cuts)


# ---------------------------------------------------------------------------
# detect_silences (parses ffmpeg stderr)
# ---------------------------------------------------------------------------

def test_detect_silences_parses_ffmpeg_stderr(tmp_path: Path):
    fake_stderr = """
some banner
[silencedetect @ 0x7f] silence_start: 10.5
[silencedetect @ 0x7f] silence_end: 11.2 | silence_duration: 0.7
[silencedetect @ 0x7f] silence_start: 50.0
[silencedetect @ 0x7f] silence_end: 51.5 | silence_duration: 1.5
not a silence line
"""
    fake_audio = tmp_path / "x.ogg"
    fake_audio.write_bytes(b"")
    fake_proc = MagicMock(stderr=fake_stderr, returncode=0)

    with patch.object(audio_chunker.subprocess, "run", return_value=fake_proc), \
         patch.object(audio_chunker, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"):
        silences = audio_chunker.detect_silences(fake_audio)

    assert len(silences) == 2
    assert silences[0].start == 10.5 and silences[0].end == 11.2
    assert silences[1].start == 50.0 and silences[1].end == 51.5


def test_detect_silences_handles_no_silences(tmp_path: Path):
    fake_audio = tmp_path / "x.ogg"
    fake_audio.write_bytes(b"")
    fake_proc = MagicMock(stderr="ffmpeg ran but found nothing\n", returncode=0)

    with patch.object(audio_chunker.subprocess, "run", return_value=fake_proc), \
         patch.object(audio_chunker, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"):
        silences = audio_chunker.detect_silences(fake_audio)

    assert silences == []


def test_detect_silences_ignores_dangling_start(tmp_path: Path):
    """silence_start without a matching silence_end must not crash."""
    fake_audio = tmp_path / "x.ogg"
    fake_audio.write_bytes(b"")
    fake_proc = MagicMock(
        stderr="[silencedetect] silence_start: 5.0\n(eof, no end)\n",
        returncode=0,
    )

    with patch.object(audio_chunker.subprocess, "run", return_value=fake_proc), \
         patch.object(audio_chunker, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"):
        silences = audio_chunker.detect_silences(fake_audio)

    assert silences == []


# ---------------------------------------------------------------------------
# probe_duration
# ---------------------------------------------------------------------------

def test_probe_duration_returns_float(tmp_path: Path):
    fake = tmp_path / "a.ogg"
    fake.write_bytes(b"")
    fake_proc = MagicMock(returncode=0, stdout="123.456\n", stderr="")
    with patch.object(audio_chunker.subprocess, "run", return_value=fake_proc), \
         patch.object(audio_chunker, "_require_ffprobe", return_value="/usr/bin/ffprobe"):
        assert audio_chunker.probe_duration(fake) == 123.456


def test_probe_duration_raises_on_failure(tmp_path: Path):
    from skills.neurolearn.backends.base import BackendError
    fake = tmp_path / "a.ogg"
    fake.write_bytes(b"")
    fake_proc = MagicMock(returncode=1, stdout="", stderr="ffprobe boom")
    with patch.object(audio_chunker.subprocess, "run", return_value=fake_proc), \
         patch.object(audio_chunker, "_require_ffprobe", return_value="/usr/bin/ffprobe"):
        with pytest.raises(BackendError, match="ffprobe"):
            audio_chunker.probe_duration(fake)


# ---------------------------------------------------------------------------
# prepare_chunks — orchestrator
# ---------------------------------------------------------------------------

def test_prepare_chunks_returns_original_when_small(tmp_path: Path):
    """File under limit must not trigger any ffmpeg work."""
    audio = tmp_path / "small.ogg"
    audio.write_bytes(b"x" * 1000)

    result = audio_chunker.prepare_chunks(audio, size_limit=10_000)

    assert result == [(audio, 0.0)]


def test_prepare_chunks_splits_when_over_limit(tmp_path: Path):
    """End-to-end: oversize file → probe duration → detect silences →
    split → return chunks."""
    audio = tmp_path / "big.ogg"
    audio.write_bytes(b"x" * 1_000_000)  # 1 MB

    silences = [
        SilenceInterval(start=99.5, end=100.5),
        SilenceInterval(start=199.5, end=200.5),
    ]

    def fake_split(audio, cut_times, duration, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        chunks = []
        boundaries = [0.0, *cut_times, duration]
        for i in range(len(boundaries) - 1):
            p = out_dir / f"chunk{i+1}.ogg"
            p.write_bytes(b"c" * 250_000)
            chunks.append((p, boundaries[i]))
        return chunks

    with patch.object(audio_chunker, "probe_duration", return_value=300.0), \
         patch.object(audio_chunker, "detect_silences", return_value=silences), \
         patch.object(audio_chunker, "split_audio", side_effect=fake_split):
        result = audio_chunker.prepare_chunks(
            audio, size_limit=400_000, work_dir=tmp_path / "work",
        )

    assert len(result) == 3
    assert result[0][1] == 0.0
    assert result[1][1] > 0
    assert result[2][1] > result[1][1]
    for p, _ in result:
        assert p.stat().st_size < 400_000


def test_prepare_chunks_status_messages_capture(tmp_path: Path):
    """Status callback must receive observable messages — important for
    Claude Code chat UX (no TTY, but user still sees what's happening)."""
    audio = tmp_path / "big.ogg"
    audio.write_bytes(b"x" * 1_000_000)

    messages: list[str] = []

    def fake_split(audio, cut_times, duration, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "c1.ogg"
        p.write_bytes(b"c" * 200_000)
        p2 = out_dir / "c2.ogg"
        p2.write_bytes(b"c" * 200_000)
        return [(p, 0.0), (p2, duration / 2)]

    with patch.object(audio_chunker, "probe_duration", return_value=100.0), \
         patch.object(audio_chunker, "detect_silences", return_value=[]), \
         patch.object(audio_chunker, "split_audio", side_effect=fake_split):
        audio_chunker.prepare_chunks(
            audio, size_limit=400_000,
            work_dir=tmp_path / "work",
            on_status=messages.append,
        )

    assert any("exceeds" in m and "splitting" in m for m in messages)
    assert any("silence" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# split_audio shells out with stream copy
# ---------------------------------------------------------------------------

def test_split_audio_uses_stream_copy(tmp_path: Path):
    """Critical: re-encoding Opus → Opus would inflate size and defeat
    the whole point of recompressing first. Stream copy preserves the
    container + codec untouched."""
    audio = tmp_path / "s.ogg"
    audio.write_bytes(b"")
    out_dir = tmp_path / "out"

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # Make the output file exist
        out_idx = cmd.index("-to")
        # Output path is the last positional arg
        Path(cmd[-1]).write_bytes(b"chunk")
        return MagicMock(returncode=0, stderr="")

    with patch.object(audio_chunker.subprocess, "run", side_effect=fake_run), \
         patch.object(audio_chunker, "_require_ffmpeg", return_value="ffmpeg"):
        audio_chunker.split_audio(audio, [30.0, 60.0], 90.0, out_dir)

    assert len(calls) == 3, "should call ffmpeg once per chunk"
    for cmd in calls:
        # Stream copy means '-c copy' (NOT a codec like -c:a aac)
        assert "-c" in cmd and "copy" in cmd
        assert "-i" in cmd
