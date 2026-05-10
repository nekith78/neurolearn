"""Tests for ClaudeVisionBackend. anthropic.Anthropic mocked."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.detection.base import DetectionWindow
from skills.youtube_transcribe.vision.claude_vision import ClaudeVisionBackend


def _fake_resp(json_text: str):
    """Build an Anthropic-style response with a single text block."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json_text
    resp = MagicMock()
    resp.content = [text_block]
    return resp


def test_claude_annotate_returns_visual_segments(tmp_path):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_resp(json.dumps({
        "description": "Code editor with Anthropic API call visible",
        "key_objects": ["editor", "API", "Anthropic"],
        "importance": "high",
    }))

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    windows = [
        DetectionWindow(start=10.0, end=15.0, reason="universal",
                        score=0.8, weight=1.0, phrase="code"),
    ]
    fake_frame = out_dir / "frames" / "v_00010.jpg"
    fake_frame.parent.mkdir(parents=True)
    fake_frame.write_bytes(b"\xff\xd8\xff" + b"fake jpeg")  # JPEG magic

    with patch(
        "anthropic.Anthropic",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[fake_frame],
    ):
        backend = ClaudeVisionBackend(api_key="fake", frames_per_window=1)
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=windows,
            prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )

    assert len(result) == 1
    assert result[0].description == "Code editor with Anthropic API call visible"
    assert result[0].importance == "high"
    assert "editor" in result[0].detected_objects
    # Verify content blocks contained image + text
    call = fake_client.messages.create.call_args
    content = call.kwargs["messages"][0]["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    text_blocks = [b for b in content if b.get("type") == "text"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert image_blocks[0]["source"]["media_type"] == "image/jpeg"
    assert len(text_blocks) == 1


def test_claude_handles_invalid_json(tmp_path):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_resp("not valid json")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fake_frame = out_dir / "frames" / "x.jpg"
    fake_frame.parent.mkdir(parents=True)
    fake_frame.write_bytes(b"jpg")

    with patch(
        "anthropic.Anthropic",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[fake_frame],
    ):
        backend = ClaudeVisionBackend(api_key="fake")
        out = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1.0, 1.0, "x")],
            prompt_template="x",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
    assert "not valid json" in out[0].description
    assert out[0].importance == "medium"


def test_claude_strips_code_fences(tmp_path):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_resp(
        '```json\n{"description":"d","key_objects":[],"importance":"low"}\n```'
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fake_frame = out_dir / "frames" / "x.jpg"
    fake_frame.parent.mkdir(parents=True)
    fake_frame.write_bytes(b"jpg")

    with patch(
        "anthropic.Anthropic",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[fake_frame],
    ):
        backend = ClaudeVisionBackend(api_key="fake")
        out = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="x",
            language="en", video_id="v", out_dir=out_dir,
        )
    assert out[0].description == "d"
    assert out[0].importance == "low"


def test_claude_empty_keyframes_skipped(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "anthropic.Anthropic",
        return_value=MagicMock(),
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[],
    ):
        backend = ClaudeVisionBackend(api_key="fake")
        out = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="x",
            language="en", video_id="v", out_dir=out_dir,
        )
    assert out == []


def test_claude_api_failure_returns_error_description(tmp_path):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = Exception("rate limit")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fake_frame = out_dir / "frames" / "x.jpg"
    fake_frame.parent.mkdir(parents=True)
    fake_frame.write_bytes(b"jpg")

    with patch(
        "anthropic.Anthropic",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[fake_frame],
    ), patch(
        "time.sleep", lambda x: None,  # speed up retry backoff
    ):
        backend = ClaudeVisionBackend(api_key="fake", max_retries=2)
        out = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="x",
            language="en", video_id="v", out_dir=out_dir,
        )
    assert len(out) == 1
    assert "error" in out[0].description.lower()
    assert "rate limit" in out[0].description
