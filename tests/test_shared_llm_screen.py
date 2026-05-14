"""Tests for shared.llm_screen — LLM-based candidate filtering."""
from dataclasses import dataclass
from unittest.mock import patch

from skills.neurolearn.shared.llm_screen import (
    screen_candidates,
    _build_prompt,
)


@dataclass
class _Cand:
    title: str
    channel: str = "ch"
    upload_date: str | None = None
    duration_sec: int | None = None


def test_screen_returns_subset_from_llm():
    cands = [_Cand(title="A"), _Cand(title="B"), _Cand(title="C")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
        return_value="[1, 3]",
    ):
        out = screen_candidates(cands, "any filter",
                                backend="gemini", api_key="k")
    assert len(out) == 2
    assert out[0].title == "A"
    assert out[1].title == "C"


def test_screen_invalid_json_returns_all():
    """If LLM returns garbage, fall back to keeping all candidates."""
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
        return_value="LLM gibberish here",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    assert out == cands


def test_screen_empty_response_returns_all():
    cands = [_Cand(title="A")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
        return_value="",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    assert out == cands


def test_screen_empty_filter_returns_all_without_llm_call():
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
    ) as mock_run:
        out = screen_candidates(cands, "", backend="gemini", api_key="k")
    assert out == cands
    mock_run.assert_not_called()


def test_screen_indices_out_of_range_ignored():
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
        return_value="[1, 5, 99]",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    # Only index 1 (= "A") is valid; 5 and 99 silently dropped
    assert len(out) == 1
    assert out[0].title == "A"


def test_prompt_includes_metadata():
    cands = [_Cand(title="Claude tutorial", channel="@anth",
                   upload_date="2024-05-01", duration_sec=720)]
    prompt = _build_prompt(cands, "best ones")
    assert "best ones" in prompt
    assert "Claude tutorial" in prompt
    assert "@anth" in prompt
    assert "2024-05-01" in prompt
    assert "12:00" in prompt or "720" in prompt
    assert "JSON" in prompt


def test_prompt_handles_missing_fields():
    cands = [_Cand(title="X", channel=None, upload_date=None,
                   duration_sec=None)]
    prompt = _build_prompt(cands, "f")
    assert "X" in prompt


def test_screen_ollama_no_key():
    cands = [_Cand(title="A")]
    with patch(
        "skills.neurolearn.shared.llm_screen.run_analysis",
        return_value="[1]",
    ) as mock:
        screen_candidates(cands, "f", backend="ollama", api_key=None)
    kwargs = mock.call_args.kwargs
    assert kwargs["backend"] == "ollama"
    assert kwargs["api_key"] is None
