"""Tests for GeminiVisionBackend. genai.Client mocked."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision.gemini import GeminiVisionBackend


def _fake_segment(start, end, text):
    """Minimal stand-in for Segment."""
    s = MagicMock()
    s.start = start
    s.end = end
    s.text = text
    return s


def test_gemini_annotate_returns_visual_segments(tmp_path):
    """Mock the entire genai client + ffmpeg keyframe extraction."""
    fake_resp = MagicMock()
    fake_resp.text = json.dumps({
        "description": "Code editor with API call",
        "key_objects": ["editor", "API"],
        "importance": "high",
    })
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/123")
    fake_client.models.generate_content.return_value = fake_resp

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    frame = out_dir / "vid_00010.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG bytes; sent inline

    windows = [
        DetectionWindow(start=10.0, end=15.0, reason="universal", score=0.8, weight=1.0, phrase="code"),
    ]

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[frame],
    ):
        backend = GeminiVisionBackend(api_key="fake", model="gemini-2.5-flash")
        result = backend.annotate_segments(
            video_path=Path("input.mp4"),
            windows=windows,
            prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
            language="en",
            video_id="vid",
            out_dir=out_dir,
        )

    assert len(result) == 1
    assert result[0].description == "Code editor with API call"
    assert result[0].importance == "high"
    assert "editor" in result[0].detected_objects  # fixed: VisualSegment uses detected_objects


def test_gemini_handles_invalid_json(tmp_path):
    """Bad JSON from Gemini → fall back to raw text in description."""
    fake_resp = MagicMock()
    fake_resp.text = "not valid json"
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    frame = out_dir / "vid_00010.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG bytes; sent inline

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[frame],
    ):
        backend = GeminiVisionBackend(api_key="fake")
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="{language}{transcript_snippet}{start_sec}{end_sec}",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
    assert "not valid json" in result[0].description
    assert result[0].importance == "medium"  # default fallback


def test_gemini_window_with_no_keyframes_skipped(tmp_path):
    """If keyframe extraction returns empty, window is skipped."""
    fake_client = MagicMock()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[],
    ):
        backend = GeminiVisionBackend(api_key="fake")
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="x",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
    assert result == []
