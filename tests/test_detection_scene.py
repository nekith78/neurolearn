"""Tests for scene boundary detection. PySceneDetect is mocked."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.neurolearn.detection.scene import find_scene_boundaries


def test_find_scene_boundaries_calls_pyscenedetect():
    fake_scene_list = [
        # PySceneDetect returns list of (FrameTimecode start, FrameTimecode end)
        (MagicMock(get_seconds=lambda: 0.0), MagicMock(get_seconds=lambda: 10.5)),
        (MagicMock(get_seconds=lambda: 10.5), MagicMock(get_seconds=lambda: 25.0)),
        (MagicMock(get_seconds=lambda: 25.0), MagicMock(get_seconds=lambda: 60.0)),
    ]
    with patch("scenedetect.detect", return_value=fake_scene_list):
        boundaries = find_scene_boundaries(Path("fake.mp4"), threshold=27.0)
    # Boundaries are scene START times (excluding first scene)
    assert boundaries == [10.5, 25.0]


def test_find_scene_boundaries_empty_video():
    with patch("scenedetect.detect", return_value=[]):
        boundaries = find_scene_boundaries(Path("empty.mp4"))
    assert boundaries == []


def test_find_scene_boundaries_single_scene():
    """One-scene video has no boundaries."""
    fake = [(MagicMock(get_seconds=lambda: 0.0), MagicMock(get_seconds=lambda: 60.0))]
    with patch("scenedetect.detect", return_value=fake):
        boundaries = find_scene_boundaries(Path("single.mp4"))
    assert boundaries == []
