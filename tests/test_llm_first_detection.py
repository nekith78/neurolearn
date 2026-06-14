"""CP4 — `llm_first` detect_method (v0.21 Mode-2 autonomous moment selection).

The LLM reads the transcript and picks the moments; trigger detection is the
fallback when the LLM can't run (no Gemini key / error / empty result).
"""
from unittest.mock import patch

from skills.neurolearn.pipeline_v02 import find_detection_windows
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.utils.output_writer import Segment
from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.detection.triggers import TriggerConfig


def _result():
    return TranscriptionResult(
        text="click here to open the menu",
        segments=[Segment(start=10.0, end=15.0, text="click here to open the menu")],
        language_detected="en",
        backend_name="subtitles",
        duration_seconds=15.0,
    )


def _triggers_matching():
    """A trigger config whose raw phrase matches the segment text."""
    cfg = TriggerConfig()
    cfg.raw = {"click here": 1.0}
    return cfg


def _patch_gemini_key(value):
    """Patch the Gemini key lookup the llm_first branch uses."""
    return patch(
        "skills.neurolearn.pipeline_v02._config_mod.get_api_key",
        lambda b, env_path=None: value if b == "gemini" else None,
    )


def test_llm_first_uses_llm_windows_when_available():
    """With a Gemini key and a non-empty LLM result, llm_first returns the
    LLM's moments ALONE (no trigger/scene windows mixed in)."""
    llm_out = [DetectionWindow(start=42.0, end=55.0, reason="llm_full_pass:demo",
                               score=0.9, weight=1.0, phrase="")]
    with _patch_gemini_key("k"), patch(
        "skills.neurolearn.pipeline_v02.find_visual_moments_via_llm",
        return_value=llm_out,
    ) as m:
        windows = find_detection_windows(
            _result(), None, _triggers_matching(), "llm_first",
        )
    m.assert_called_once()
    # The Gemini key — not the vision-backend key — must be the one used.
    assert m.call_args.kwargs["api_key"] == "k"
    assert windows == llm_out
    assert all(w.reason.startswith("llm_full_pass") for w in windows)


def test_llm_first_falls_back_to_triggers_without_key():
    """No Gemini key → LLM can't run → trigger windows are used."""
    with _patch_gemini_key(None), patch(
        "skills.neurolearn.pipeline_v02.find_visual_moments_via_llm",
    ) as m:
        windows = find_detection_windows(
            _result(), None, _triggers_matching(), "llm_first",
        )
    m.assert_not_called()  # never attempted without a key
    assert len(windows) == 1
    assert windows[0].phrase == "click here"


def test_llm_first_falls_back_to_triggers_on_empty_llm():
    """Key present but LLM returns nothing → trigger fallback."""
    with _patch_gemini_key("k"), patch(
        "skills.neurolearn.pipeline_v02.find_visual_moments_via_llm",
        return_value=[],
    ):
        windows = find_detection_windows(
            _result(), None, _triggers_matching(), "llm_first",
        )
    assert len(windows) == 1
    assert windows[0].phrase == "click here"


def test_llm_first_falls_back_to_triggers_on_llm_error():
    """LLM raises → swallowed → trigger fallback (never crashes the run)."""
    with _patch_gemini_key("k"), patch(
        "skills.neurolearn.pipeline_v02.find_visual_moments_via_llm",
        side_effect=RuntimeError("network down"),
    ):
        windows = find_detection_windows(
            _result(), None, _triggers_matching(), "llm_first",
        )
    assert len(windows) == 1
    assert windows[0].phrase == "click here"
