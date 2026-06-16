"""Tests for refine_with_frame_diff (spec §5 brick C integration).

Drops static windows, boosts rich ones, no-ops on ffmpeg failure.
"""
from pathlib import Path
from unittest.mock import patch

from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.detection.frame_diff import FrameDiff
from skills.neurolearn.detection.window_merge import refine_with_frame_diff


def _w(start, end, score=0.5, reason="universal", phrase="x"):
    return DetectionWindow(
        start=start, end=end, reason=reason,
        score=score, weight=1.0, phrase=phrase,
    )


def test_static_window_dropped():
    """0 frame changes → drop the window (talking head, not worth Gemini call)."""
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[],
    ):
        out = refine_with_frame_diff([_w(0, 5)], Path("fake.mp4"))
    assert out == []


def test_low_activity_window_dropped_below_min_changes():
    """Default min_changes=1: window with 0 changes dropped, 1 kept."""
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[],
    ):
        out = refine_with_frame_diff([_w(0, 5)], Path("fake.mp4"), min_changes=1)
    assert out == []

    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[FrameDiff(timestamp=2.0, hamming_distance=25)],
    ):
        out = refine_with_frame_diff([_w(0, 5)], Path("fake.mp4"), min_changes=1)
    assert len(out) == 1


def test_rich_window_gets_score_boost():
    """>=5 changes → score multiplied by rich_score_boost (default 1.3)."""
    diffs = [FrameDiff(timestamp=t, hamming_distance=25) for t in range(5)]
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=diffs,
    ):
        out = refine_with_frame_diff([_w(0, 10, score=0.6)], Path("fake.mp4"))
    assert len(out) == 1
    assert abs(out[0].score - 0.6 * 1.3) < 1e-6
    # Other fields unchanged
    assert out[0].reason == "universal"
    assert out[0].phrase == "x"


def test_score_clamped_at_one():
    """Boost should not push score above 1.0."""
    diffs = [FrameDiff(timestamp=t, hamming_distance=25) for t in range(5)]
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=diffs,
    ):
        out = refine_with_frame_diff([_w(0, 10, score=0.9)], Path("fake.mp4"))
    assert out[0].score == 1.0


def test_medium_activity_kept_unchanged():
    """1 <= changes < rich_changes → keep window as-is, no score change."""
    diffs = [FrameDiff(timestamp=1.0, hamming_distance=25),
             FrameDiff(timestamp=2.0, hamming_distance=22)]
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=diffs,
    ):
        out = refine_with_frame_diff([_w(0, 5, score=0.6)], Path("fake.mp4"))
    assert len(out) == 1
    assert out[0].score == 0.6  # unchanged


def test_ffmpeg_failure_keeps_window():
    """If frame_diff raises (ffmpeg hiccup), keep the window — don't lose data."""
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        side_effect=Exception("ffmpeg crashed"),
    ):
        out = refine_with_frame_diff([_w(0, 5, score=0.6)], Path("fake.mp4"))
    assert len(out) == 1
    assert out[0].score == 0.6


def test_empty_windows_returns_empty():
    out = refine_with_frame_diff([], Path("fake.mp4"))
    assert out == []


def test_raw_trigger_window_never_dropped():
    """raw-reason windows are user explicit intent — never drop, never re-score."""
    w_raw = _w(0, 5, score=0.5, reason="raw", phrase="TODO")
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[],  # would normally drop
    ) as mock_diff:
        out = refine_with_frame_diff([w_raw], Path("fake.mp4"))
    assert len(out) == 1
    assert out[0].score == 0.5  # unchanged
    mock_diff.assert_not_called()  # short-circuit before ffmpeg


def test_strict_lang_window_never_dropped():
    w_strict = _w(0, 5, score=0.5, reason="strict:ru", phrase="баг")
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[],
    ):
        out = refine_with_frame_diff([w_strict], Path("fake.mp4"))
    assert len(out) == 1


def test_strong_reason_window_never_dropped():
    """A strong-reason window (the user's exact strict-match trigger flagged
    this moment) is never dropped — frame_diff shouldn't override that, even if
    visuals are static."""
    w_strong = _w(0, 5, score=0.9, reason="strict:en", phrase="")
    with patch(
        "skills.neurolearn.detection.frame_diff.detect_frame_changes_in_window",
        return_value=[],
    ):
        out = refine_with_frame_diff([w_strong], Path("fake.mp4"))
    assert len(out) == 1
    assert out[0].score == 0.9
