"""After refactor, summarizer goes through analyze.runner."""
from unittest.mock import patch

from skills.youtube_transcribe.quality.summarizer import summarize_transcript
from skills.youtube_transcribe.utils.output_writer import Segment


def test_summarize_calls_run_analysis():
    segs = [Segment(start=0.0, end=1.0, text="hello")]
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="## TL;DR\nOK",
    ) as mock:
        out = summarize_transcript(
            segs, language="en",
            api_key="fake", backend="gemini",
        )
    assert out == "## TL;DR\nOK"
    mock.assert_called_once()
    full_prompt = mock.call_args.args[0]
    # The hardcoded summary template must still be present.
    assert "TL;DR" in full_prompt
    assert "Key points" in full_prompt
    assert "Notable quotes" in full_prompt
    # And the transcript text must be there.
    assert "hello" in full_prompt


def test_summarize_ollama_path():
    segs = [Segment(start=0.0, end=1.0, text="hi")]
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="X",
    ) as mock:
        out = summarize_transcript(
            segs, language="ru",
            api_key=None, backend="ollama",
            ollama_model="llama3.2:3b",
            ollama_host="http://localhost:11434",
        )
    assert out == "X"
    kwargs = mock.call_args.kwargs
    assert kwargs["backend"] == "ollama"
    assert kwargs["api_key"] is None
    assert kwargs["ollama_model"] == "llama3.2:3b"
    assert kwargs["ollama_host"] == "http://localhost:11434"


def test_summarize_empty_segments_returns_empty():
    out = summarize_transcript([], language="en", api_key="k", backend="gemini")
    assert out == ""
