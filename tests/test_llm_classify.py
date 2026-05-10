"""Tests for find_visual_moments_via_llm. genai.Client mocked."""
import json
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.detection.llm_classify import (
    _format_transcript,
    _parse_response,
    find_visual_moments_via_llm,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def _seg(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_format_transcript_includes_timestamps():
    segs = [_seg(0.0, 5.5, "hello"), _seg(6.0, 12.3, "world")]
    text = _format_transcript(segs)
    assert "[0.0 - 5.5]" in text
    assert "[6.0 - 12.3]" in text
    assert "hello" in text
    assert "world" in text


def test_format_transcript_truncates_long():
    """Long transcripts get truncated to keep within TPM."""
    segs = [_seg(i * 1.0, i * 1.0 + 1.0, "x" * 100) for i in range(2000)]
    text = _format_transcript(segs, max_chars=5000)
    assert "[...transcript truncated...]" in text
    assert len(text) < 6000


def test_parse_response_plain_json():
    raw = '[{"start": 10.0, "end": 15.0, "reason": "code", "score": 0.9}]'
    items = _parse_response(raw)
    assert len(items) == 1
    assert items[0]["start"] == 10.0


def test_parse_response_strips_code_fences():
    raw = '```json\n[{"start": 1.0, "end": 2.0, "score": 0.5, "reason": "x"}]\n```'
    items = _parse_response(raw)
    assert len(items) == 1
    assert items[0]["score"] == 0.5


def test_parse_response_invalid_json_returns_empty():
    assert _parse_response("not json") == []
    assert _parse_response("") == []
    assert _parse_response("{not array}") == []


def test_parse_response_non_list_returns_empty():
    assert _parse_response('{"start": 1.0}') == []


def test_find_visual_moments_returns_windows():
    fake_resp = MagicMock()
    fake_resp.text = json.dumps([
        {"start": 10.0, "end": 15.0, "reason": "code on screen", "score": 0.9},
        {"start": 30.0, "end": 35.0, "reason": "diagram", "score": 0.7},
    ])
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch(
        "google.genai.Client",
        return_value=fake_client,
    ):
        windows = find_visual_moments_via_llm(
            [_seg(0, 60, "hello world")],
            api_key="fake",
            language="en",
        )

    assert len(windows) == 2
    assert windows[0].reason.startswith("llm_full_pass:")
    assert "code on screen" in windows[0].reason
    assert windows[0].score == 0.9
    assert windows[0].start == 10.0
    assert windows[0].end == 15.0


def test_find_visual_moments_empty_segments():
    """Empty input → empty output, no API call."""
    with patch("google.genai.Client") as mock_client:
        out = find_visual_moments_via_llm([], api_key="fake")
    assert out == []
    mock_client.assert_not_called()


def test_find_visual_moments_api_failure_returns_empty():
    """If Gemini call raises, return [] gracefully."""
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = Exception("network error")

    with patch("google.genai.Client", return_value=fake_client):
        out = find_visual_moments_via_llm(
            [_seg(0, 5, "hello")],
            api_key="fake",
        )
    assert out == []


def test_find_visual_moments_skips_invalid_items():
    """Items with bad start/end / no end / negative duration are skipped."""
    fake_resp = MagicMock()
    fake_resp.text = json.dumps([
        {"start": 10.0, "end": 15.0, "reason": "ok", "score": 0.9},
        {"start": 20.0},  # missing end
        {"start": 30.0, "end": 25.0, "reason": "bad", "score": 0.5},  # end < start
        {"start": "not a number", "end": 50.0},  # bad type
    ])
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("google.genai.Client", return_value=fake_client):
        out = find_visual_moments_via_llm(
            [_seg(0, 60, "hello")],
            api_key="fake",
        )
    # Only the first item is valid
    assert len(out) == 1
    assert out[0].start == 10.0


def test_find_visual_moments_clamps_score():
    """Score outside [0, 1] should be clamped."""
    fake_resp = MagicMock()
    fake_resp.text = json.dumps([
        {"start": 1.0, "end": 2.0, "reason": "high", "score": 1.5},
        {"start": 3.0, "end": 4.0, "reason": "low", "score": -0.5},
    ])
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("google.genai.Client", return_value=fake_client):
        out = find_visual_moments_via_llm(
            [_seg(0, 5, "hello")],
            api_key="fake",
        )
    assert len(out) == 2
    assert out[0].score == 1.0
    assert out[1].score == 0.0
