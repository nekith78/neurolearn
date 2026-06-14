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


def test_parse_box_2d():
    from skills.neurolearn.vision.gemini import _parse_box_2d
    assert _parse_box_2d('{"box_2d":[48,550,980,994]}') == (48, 550, 980, 994)
    assert _parse_box_2d('```json\n{"box_2d":[0,0,1000,1000]}\n```') == (0, 0, 1000, 1000)
    assert _parse_box_2d('{"description":"x"}') is None          # absent
    assert _parse_box_2d('{"box_2d":[0,800,1000,200]}') is None  # xmin>xmax
    assert _parse_box_2d('not json') is None


def test_crop_keyframes_to_box_crops_and_skips_full_frame(tmp_path):
    from PIL import Image
    from skills.neurolearn.vision.gemini import _crop_keyframes_to_box
    f = tmp_path / "frames"; f.mkdir()
    p = f / "vid_00010.jpg"
    Image.new("RGB", (1000, 500), (0, 0, 0)).save(p)

    # A real sub-region → cropped file referenced.
    out = _crop_keyframes_to_box([p], (0, 500, 1000, 1000))
    assert out == ["frames/vid_00010_crop.jpg"]
    assert (f / "vid_00010_crop.jpg").exists()

    # Near-full-frame box → left uncropped (nothing to gain).
    assert _crop_keyframes_to_box([p], (0, 0, 1000, 1000)) == ["frames/vid_00010.jpg"]
    # No box → original frames.
    assert _crop_keyframes_to_box([p], None) == ["frames/vid_00010.jpg"]


def test_procedure_window_gets_denser_frames(tmp_path):
    """A procedure moment (stepwise transcript + long span) extracts more
    frames across the span; a showcase keeps the compact bracket."""
    import skills.neurolearn.vision.frames as frames_mod
    backend = GeminiVisionBackend(api_key="x", frames_per_window=3)

    proc = DetectionWindow(
        start=100.0, end=140.0, reason="raw", score=1.0, weight=1.0, phrase="x",
        transcript_context=(
            "First grab the base, then chaos spam it, after that fracture it, "
            "and finally quality the amulet."
        ),
    )
    with patch.object(frames_mod, "extract_keyframes", return_value=[]) as ek:
        backend._extract_frames_for_window(Path("v.mp4"), proc, tmp_path, "v")
    assert ek.call_args.kwargs["count"] == 5  # max(3, 5)

    show = DetectionWindow(
        start=10.0, end=15.0, reason="raw", score=1.0, weight=1.0, phrase="x",
        transcript_context="This amulet grants cast on dodge for free.",
    )
    with patch.object(frames_mod, "extract_keyframes", return_value=[]) as ek2:
        backend._extract_frames_for_window(Path("v.mp4"), show, tmp_path, "v")
    assert ek2.call_args.kwargs["count"] == 3  # frames_per_window default


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
