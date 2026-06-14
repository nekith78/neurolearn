"""Tests for v0.10.1 Gemini backend improvements:
  • caching: video bundle, skip when N<2
  • adaptive concurrency by tier
  • retryDelay parsing from 429 responses
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision.gemini import (
    GeminiVisionBackend, concurrency_for_tier, _parse_retry_delay_seconds,
)


def _kf(path):
    """Create a real dummy JPEG and return [path]. v0.21 sends keyframe
    stills inline (read_bytes), so mocked frames must exist on disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xd8\xff\xd9")
    return [p]


def _fake_response(payload: dict, *, prompt=1000, output=100, cached=0):
    r = MagicMock()
    r.text = json.dumps(payload)
    r.usage_metadata = MagicMock(
        prompt_token_count=prompt,
        candidates_token_count=output,
        cached_content_token_count=cached,
        total_token_count=prompt + output,
    )
    return r


def _windows(n):
    return [
        DetectionWindow(
            start=i * 10.0, end=i * 10.0 + 5.0,
            reason="raw", score=0.8, weight=1.0, phrase=f"p{i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Concurrency by tier
# ---------------------------------------------------------------------------


def test_concurrency_for_free_tier():
    # v0.11.0: bumped from 3 to 6 after Google raised gemini-2.5-flash
    # free-tier RPM from 5 to 10. Six concurrent calls × ~2 s each
    # averages ~7 RPM, well under the cap with room for retries.
    assert concurrency_for_tier("free") == 6


def test_concurrency_for_paid_tier():
    assert concurrency_for_tier("paid") == 10


def test_concurrency_for_paid_tier2():
    assert concurrency_for_tier("paid-tier2") == 20


def test_concurrency_unknown_tier_falls_back_to_free():
    """Unknown tier strings (typos, future tiers we don't know about)
    should not crash — fall back to the safe free-tier floor."""
    assert concurrency_for_tier("enterprise-x9000") == 6
    assert concurrency_for_tier("") == 6


# ---------------------------------------------------------------------------
# retryDelay parsing from 429
# ---------------------------------------------------------------------------


def test_parse_retry_delay_from_429():
    err = Exception(
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, ..., "
        "'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
        "'retryDelay': '31s'}]}}"
    )
    assert _parse_retry_delay_seconds(err) == 31.0


def test_parse_retry_delay_with_decimal():
    err = Exception("429 ... 'retryDelay': '8.5s' ...")
    assert _parse_retry_delay_seconds(err) == 8.5


def test_parse_retry_delay_returns_none_for_non_429():
    """Non-quota errors shouldn't have a retryDelay parsed from them."""
    err = Exception("500 Internal server error")
    assert _parse_retry_delay_seconds(err) is None


def test_parse_retry_delay_returns_none_when_missing():
    err = Exception("429 RESOURCE_EXHAUSTED but no retryDelay in payload")
    assert _parse_retry_delay_seconds(err) is None


# ---------------------------------------------------------------------------
# Caching: skip when N<2, attempt when N>=2
# ---------------------------------------------------------------------------


def test_single_window_skips_cache_creation(tmp_path):
    """1 window → caching is uneconomical. Setup must not happen."""
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/1")
    fake_client.models.generate_content.return_value = _fake_response({
        "description": "x", "key_objects": [],
        "importance": "medium", "confidence": 0.9, "needs_refinement": False,
    })

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        side_effect=lambda *a, **k: _kf(out_dir / "v.jpg"),
    ):
        backend = GeminiVisionBackend(api_key="x")
        backend.annotate_segments(
            video_path=Path("v.mp4"), windows=_windows(1),
            prompt_template="t", language="en",
            video_id="v", out_dir=out_dir,
        )

    fake_client.caches.create.assert_not_called()


def test_no_explicit_cache_or_files_upload_v021(tmp_path):
    """v0.21: keyframe stills are sent inline. Neither explicit cache
    creation nor the Files API video upload is used anymore — both were
    sources of the ACTIVE-state race / free-tier 4xx. The per-window
    prompt text (our template) rides in contents[0]."""
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_response({
        "description": "x", "key_objects": [],
        "importance": "medium", "confidence": 0.9, "needs_refinement": False,
    })

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        side_effect=lambda *a, **k: _kf(out_dir / "v.jpg"),
    ):
        backend = GeminiVisionBackend(api_key="x", max_concurrent=3)
        backend.annotate_segments(
            video_path=Path("v.mp4"), windows=_windows(3),
            prompt_template="MY_PROMPT_TEMPLATE", language="en",
            video_id="v", out_dir=out_dir,
        )

    fake_client.caches.create.assert_not_called()
    fake_client.files.upload.assert_not_called()
    # The template (no placeholders → unchanged) rides in the prompt string.
    first_call = fake_client.models.generate_content.call_args_list[0]
    contents = first_call.kwargs["contents"]
    assert "MY_PROMPT_TEMPLATE" in contents[0]


def test_per_window_contents_carry_inline_stills_v021(tmp_path):
    """v0.21: each per-window call carries the user prompt plus the
    extracted keyframe STILLS inline (image/jpeg Parts) — that's what
    grounds the description. No uploaded-video reference."""
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_response({
        "description": "x", "key_objects": [],
        "importance": "medium", "confidence": 0.9, "needs_refinement": False,
    })

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        side_effect=lambda *a, **k: _kf(out_dir / "v.jpg"),
    ):
        backend = GeminiVisionBackend(api_key="x")
        backend.annotate_segments(
            video_path=Path("v.mp4"), windows=_windows(3),
            prompt_template="t", language="en",
            video_id="v", out_dir=out_dir,
        )

    for call in fake_client.models.generate_content.call_args_list:
        contents = call.kwargs["contents"]
        # [prompt_str, image_Part, ...] — at least the prompt + one still.
        assert len(contents) >= 2
        assert isinstance(contents[0], str)
        still = contents[1]
        assert getattr(still.inline_data, "mime_type", "") == "image/jpeg"
        assert still.inline_data.data == b"\xff\xd8\xff\xd9"
