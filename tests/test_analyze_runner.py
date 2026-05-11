"""Tests for analyze.runner — wrap _call_* LLM funcs."""
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.analyze.runner import run_analysis


def test_gemini_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        return_value="ANSWER",
    ) as mock:
        out = run_analysis("PROMPT", backend="gemini", api_key="sk-abc")
    mock.assert_called_once_with("PROMPT", "sk-abc")
    assert out == "ANSWER"


def test_claude_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_claude",
        return_value="A",
    ) as mock:
        out = run_analysis("P", backend="claude", api_key="key")
    mock.assert_called_once_with("P", "key")
    assert out == "A"


def test_openai_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_openai",
        return_value="A",
    ) as mock:
        out = run_analysis("P", backend="openai", api_key="key")
    mock.assert_called_once_with("P", "key")
    assert out == "A"


def test_ollama_passes_model_and_host():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_ollama",
        return_value="A",
    ) as mock:
        out = run_analysis(
            "P", backend="ollama", api_key=None,
            ollama_model="qwen2:7b",
            ollama_host="http://example:11434",
        )
    mock.assert_called_once_with(
        "P", model="qwen2:7b", host="http://example:11434",
    )
    assert out == "A"


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown backend"):
        run_analysis("P", backend="bogus", api_key="x")


def test_exception_returns_empty():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        side_effect=RuntimeError("boom"),
    ):
        out = run_analysis("P", backend="gemini", api_key="key")
    assert out == ""


def test_empty_response_returned_as_is():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        return_value="",
    ):
        out = run_analysis("P", backend="gemini", api_key="k")
    assert out == ""
