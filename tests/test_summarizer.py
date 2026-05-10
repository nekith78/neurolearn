"""Tests for LLM-based auto-summary."""
import json
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.quality.summarizer import (
    _format_transcript_for_summary,
    summarize_transcript,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def _s(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_format_transcript_uses_hms_timestamps():
    segs = [_s(0.0, 5.0, "hello"), _s(3725.0, 3730.0, "later")]  # 1h2m5s
    out = _format_transcript_for_summary(segs)
    assert "[00:00:00] hello" in out
    assert "[01:02:05] later" in out


def test_format_transcript_truncates_long():
    segs = [_s(i, i + 1, "x" * 200) for i in range(1000)]
    out = _format_transcript_for_summary(segs)
    assert "[...truncated...]" in out


def test_summarize_empty_returns_empty():
    out = summarize_transcript([], api_key="k", backend="gemini")
    assert out == ""


def test_summarize_via_gemini():
    segs = [_s(0, 5, "Hello world this is a test of summarization")]
    fake_resp = MagicMock()
    fake_resp.text = "## TL;DR\nA test summary.\n\n## Key points\n- testing"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch("google.genai.Client", return_value=fake_client):
        out = summarize_transcript(segs, "en", api_key="k", backend="gemini")
    assert "TL;DR" in out
    assert "test summary" in out


def test_summarize_via_claude():
    segs = [_s(0, 5, "x")]
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "## TL;DR\nclaude summary"
    fake_resp = MagicMock()
    fake_resp.content = [text_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    with patch("anthropic.Anthropic", return_value=fake_client):
        out = summarize_transcript(segs, "en", api_key="k", backend="claude")
    assert "claude summary" in out


def test_summarize_via_openai():
    segs = [_s(0, 5, "x")]
    choice = MagicMock()
    choice.message.content = "## TL;DR\nopenai summary"
    fake_resp = MagicMock()
    fake_resp.choices = [choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp

    with patch("openai.OpenAI", return_value=fake_client):
        out = summarize_transcript(segs, "en", api_key="k", backend="openai")
    assert "openai summary" in out


def test_summarize_via_ollama():
    segs = [_s(0, 5, "x")]
    body = json.dumps({"response": "## TL;DR\nollama summary"}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read = MagicMock(return_value=body)
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=None)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        out = summarize_transcript(segs, "en", api_key=None, backend="ollama")
    assert "ollama summary" in out


def test_summarize_llm_failure_returns_empty():
    segs = [_s(0, 5, "x")]
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = RuntimeError("rate limit")

    with patch("google.genai.Client", return_value=fake_client):
        out = summarize_transcript(segs, "en", api_key="k", backend="gemini")
    assert out == ""


def test_summarize_unknown_backend_returns_empty():
    segs = [_s(0, 5, "x")]
    out = summarize_transcript(segs, "en", api_key="k", backend="bogus")
    assert out == ""
