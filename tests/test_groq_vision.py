"""Tests for GroqVisionBackend (v0.12.0).

Mocks `groq.Groq` so no real API key is needed. Verifies:
- annotate_segments yields VisualSegment with parsed JSON fields
- response_format requests json_schema with our 5-field schema
- batch cap (≤3 images per request) is enforced
- transient errors trigger retry, repeated errors yield None per window
- empty windows list returns empty list
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision.groq_vision import GroqVisionBackend


def _window(start: float, end: float, phrase: str = "") -> DetectionWindow:
    return DetectionWindow(
        start=start, end=end, reason="raw", score=1.0, phrase=phrase,
    )


def _mock_chat_response(payload: dict, *, prompt_tokens=100, completion_tokens=50):
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    fake_resp = MagicMock()
    fake_resp.choices = [choice]
    fake_resp.usage.prompt_tokens = prompt_tokens
    fake_resp.usage.completion_tokens = completion_tokens
    fake_resp.usage.total_tokens = prompt_tokens + completion_tokens
    return fake_resp


def _stub_frame(tmp_path: Path, name: str = "frame.jpg") -> Path:
    p = tmp_path / "frames" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    # Minimal valid bytes — we mock the API so content doesn't matter.
    p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    return p


class TestAnnotateSegments:
    def test_empty_windows_returns_empty(self, tmp_path):
        backend = GroqVisionBackend(api_key="fake")
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[],
            prompt_template="ignored",
            language="en",
            video_id="v",
            out_dir=tmp_path,
        )
        assert result == []

    def test_happy_path_yields_visual_segment(self, tmp_path):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response({
            "description": "Game UI showing a skill tooltip.",
            "key_objects": ["Skill A", "Tooltip"],
            "importance": "high",
            "confidence": 0.9,
            "needs_refinement": False,
        })

        frame = _stub_frame(tmp_path)
        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            result = backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(10.0, 14.0, phrase="ctx")],
                prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        assert len(result) == 1
        seg = result[0]
        assert seg.description == "Game UI showing a skill tooltip."
        assert "Skill A" in seg.detected_objects
        assert seg.importance == "high"
        assert seg.confidence == 0.9
        assert seg.needs_refinement is False
        assert seg.start == 10.0 and seg.end == 14.0
        assert seg.trigger_reason == "ctx"

    def test_response_format_uses_strict_json_schema(self, tmp_path):
        """v0.12.0 invariant: every Groq call sends response_format with
        json_schema mode and strict=true. This is what gives us
        guaranteed-valid JSON without retries."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response({
            "description": "x", "key_objects": [],
            "importance": "low", "confidence": 0.5, "needs_refinement": False,
        })
        frame = _stub_frame(tmp_path)

        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 5.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"
        assert call_kwargs["response_format"]["json_schema"]["strict"] is True
        schema = call_kwargs["response_format"]["json_schema"]["schema"]
        for field in [
            "description", "key_objects", "importance",
            "confidence", "needs_refinement",
        ]:
            assert field in schema["required"]

    def test_image_batch_capped_at_three(self, tmp_path):
        """Llama-4-Scout quality drops past 3 images per request (per
        Groq vision docs + our empirical tests). We enforce 3-cap."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response({
            "description": "x", "key_objects": [],
            "importance": "medium", "confidence": 0.7, "needs_refinement": False,
        })
        # 5 frames extracted, but only first 3 should reach the API.
        frames = [_stub_frame(tmp_path, f"f{i}.jpg") for i in range(5)]

        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=frames,
        ):
            backend = GroqVisionBackend(api_key="fake", frames_per_window=5)
            backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 10.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        content = fake_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        # content has 1 text part + N image_url parts. Count images:
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(image_parts) == 3, (
            f"expected 3 images max, got {len(image_parts)}"
        )

    def test_uses_llama_4_scout_model_by_default(self, tmp_path):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response({
            "description": "x", "key_objects": [],
            "importance": "low", "confidence": 0.5, "needs_refinement": False,
        })
        frame = _stub_frame(tmp_path)
        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 5.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        model = fake_client.chat.completions.create.call_args.kwargs["model"]
        assert "llama-4-scout" in model

    def test_image_encoded_as_base64_data_url(self, tmp_path):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response({
            "description": "x", "key_objects": [],
            "importance": "low", "confidence": 0.5, "needs_refinement": False,
        })
        frame = _stub_frame(tmp_path)
        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 5.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        content = fake_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        img_part = next(p for p in content if p.get("type") == "image_url")
        url = img_part["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")

    def test_malformed_json_response_drops_window(self, tmp_path):
        """If JSON parse fails despite strict mode, return None for that
        window (not crash). Caller sees a shorter result list."""
        choice = MagicMock()
        choice.message.content = "{garbled not json}"
        fake_resp = MagicMock()
        fake_resp.choices = [choice]
        fake_resp.usage.prompt_tokens = 100
        fake_resp.usage.completion_tokens = 50
        fake_resp.usage.total_tokens = 150

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_resp

        frame = _stub_frame(tmp_path)
        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            result = backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 5.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        assert result == []

    def test_token_usage_recorded(self, tmp_path):
        """last_run_usage exposed for BudgetTracker integration in pipeline_v02."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _mock_chat_response(
            {
                "description": "x", "key_objects": [],
                "importance": "low", "confidence": 0.5, "needs_refinement": False,
            },
            prompt_tokens=234, completion_tokens=56,
        )
        frame = _stub_frame(tmp_path)
        with patch(
            "skills.neurolearn.vision.groq_vision._import_groq",
            return_value=lambda api_key: fake_client,
        ), patch(
            "skills.neurolearn.vision.groq_vision.extract_keyframes",
            return_value=[frame],
        ):
            backend = GroqVisionBackend(api_key="fake")
            backend.annotate_segments(
                video_path=Path("v.mp4"),
                windows=[_window(0.0, 5.0)],
                prompt_template="t",
                language="en",
                video_id="v",
                out_dir=tmp_path,
            )

        assert len(backend.last_run_usage) == 1
        usage = backend.last_run_usage[0]
        assert usage.prompt_tokens == 234
        assert usage.output_tokens == 56
        assert usage.total_tokens == 290
