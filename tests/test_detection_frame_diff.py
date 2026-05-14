"""Tests for frame difference detection via ImageHash."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skills.neurolearn.detection.frame_diff import (
    FrameDiff,
    detect_frame_changes_in_window,
)


def test_frame_diff_dataclass():
    fd = FrameDiff(timestamp=10.5, hamming_distance=18)
    assert fd.timestamp == 10.5
    assert fd.hamming_distance == 18


def test_detect_frame_changes_returns_diffs():
    """Mock ffmpeg + imagehash to return synthetic frames."""
    fake_hashes = [MagicMock(), MagicMock(), MagicMock()]
    # Hamming distances between consecutive: 0, 30 (big change)
    fake_hashes[0].__sub__ = MagicMock(return_value=0)
    fake_hashes[1].__sub__ = MagicMock(return_value=30)
    fake_hashes[2].__sub__ = MagicMock(return_value=5)

    with patch(
        "skills.neurolearn.detection.frame_diff._extract_frame_hashes",
        return_value=[(0.0, fake_hashes[0]), (1.0, fake_hashes[1]), (2.0, fake_hashes[2])],
    ):
        diffs = detect_frame_changes_in_window(
            Path("fake.mp4"), start=0.0, end=2.0, threshold=20
        )
    # Only the diff > threshold (20) makes it to the result
    assert len(diffs) == 1
    assert diffs[0].timestamp == 1.0
    assert diffs[0].hamming_distance == 30


def test_detect_frame_changes_no_changes():
    fake_hashes = [MagicMock(), MagicMock()]
    fake_hashes[0].__sub__ = MagicMock(return_value=2)
    fake_hashes[1].__sub__ = MagicMock(return_value=2)
    with patch(
        "skills.neurolearn.detection.frame_diff._extract_frame_hashes",
        return_value=[(0.0, fake_hashes[0]), (1.0, fake_hashes[1])],
    ):
        diffs = detect_frame_changes_in_window(Path("x.mp4"), 0.0, 1.0, threshold=20)
    assert diffs == []
