"""Tests for ASR error correction via cheap text-only LLM."""
import json
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.quality.asr_corrector import (
    _build_input_json,
    _parse_corrected_segments,
    correct_transcript_via_llm,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def _s(start, end, text):
    return Segment(start=start, end=end, text=text)


# === input/output JSON helpers ===

def test_build_input_json_preserves_fields():
    segs = [_s(0.0, 5.5, "hello"), _s(5.5, 10.0, "world")]
    raw = _build_input_json(segs)
    data = json.loads(raw)
    assert data[0]["start"] == 0.0
    assert data[0]["end"] == 5.5
    assert data[0]["text"] == "hello"
    assert data[1]["text"] == "world"


def test_parse_keeps_original_timestamps():
    """Corrected output uses original start/end even if LLM tried to change them."""
    orig = [_s(0.0, 5.0, "elephats")]
    raw = json.dumps([{"start": 99.9, "end": 199.9, "text": "elephants"}])
    out = _parse_corrected_segments(raw, orig)
    assert out[0].start == 0.0
    assert out[0].end == 5.0
    assert out[0].text == "elephants"


def test_parse_invalid_json_returns_original():
    orig = [_s(0.0, 5.0, "hello")]
    out = _parse_corrected_segments("not json", orig)
    assert out == orig


def test_parse_wrong_length_returns_original():
    """LLM dropped/added a segment → reject, keep original."""
    orig = [_s(0.0, 5.0, "a"), _s(5.0, 10.0, "b")]
    raw = json.dumps([{"start": 0, "end": 5, "text": "a"}])  # only 1
    out = _parse_corrected_segments(raw, orig)
    assert out == orig


def test_parse_strips_code_fences():
    orig = [_s(0.0, 5.0, "bad")]
    raw = '```json\n[{"start":0.0,"end":5.0,"text":"good"}]\n```'
    out = _parse_corrected_segments(raw, orig)
    assert out[0].text == "good"


def test_parse_non_list_returns_original():
    orig = [_s(0.0, 5.0, "hello")]
    raw = json.dumps({"not": "a list"})
    out = _parse_corrected_segments(raw, orig)
    assert out == orig


# === backend dispatch ===

def test_correct_via_gemini_mocked():
    orig = [_s(0.0, 5.0, "elephats")]
    fake_resp = MagicMock()
    fake_resp.text = json.dumps([
        {"start": 0.0, "end": 5.0, "text": "elephants"},
    ])
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("google.genai.Client", return_value=fake_client):
        out = correct_transcript_via_llm(orig, "en", api_key="k", backend="gemini")
    assert out[0].text == "elephants"


def test_correct_via_claude_mocked():
    orig = [_s(0.0, 5.0, "elephats")]
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps([
        {"start": 0.0, "end": 5.0, "text": "elephants"},
    ])
    fake_resp = MagicMock()
    fake_resp.content = [text_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    with patch("anthropic.Anthropic", return_value=fake_client):
        out = correct_transcript_via_llm(orig, "en", api_key="k", backend="claude")
    assert out[0].text == "elephants"


def test_correct_via_openai_mocked():
    orig = [_s(0.0, 5.0, "elephats")]
    choice = MagicMock()
    choice.message.content = json.dumps([
        {"start": 0.0, "end": 5.0, "text": "elephants"},
    ])
    fake_resp = MagicMock()
    fake_resp.choices = [choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp

    with patch("openai.OpenAI", return_value=fake_client):
        out = correct_transcript_via_llm(orig, "en", api_key="k", backend="openai")
    assert out[0].text == "elephants"


def test_unknown_backend_returns_original():
    orig = [_s(0.0, 5.0, "hello")]
    out = correct_transcript_via_llm(orig, "en", api_key="k", backend="bogus")
    assert out == orig


def test_empty_segments_returns_empty():
    out = correct_transcript_via_llm([], "en", api_key="k", backend="gemini")
    assert out == []


def test_llm_failure_returns_original():
    """If LLM call raises, return original segments unchanged."""
    orig = [_s(0.0, 5.0, "elephats")]
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = RuntimeError("rate limit")

    with patch("google.genai.Client", return_value=fake_client):
        out = correct_transcript_via_llm(orig, "en", api_key="k", backend="gemini")
    assert out == orig


def test_parse_missing_text_key_returns_original():
    orig = [_s(0.0, 5.0, "hi")]
    raw = json.dumps([{"start": 0, "end": 5}])  # missing "text"
    out = _parse_corrected_segments(raw, orig)
    assert out == orig
