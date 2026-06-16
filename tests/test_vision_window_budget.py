"""The smart/eco presets keep max_windows_per_video=0 (vision off by default).
--with-visuals turns vision on but must also restore a window budget, else
select_windows_by_budget drops every window → an empty Mode-2 report."""
from skills.neurolearn.transcribe import _ensure_vision_window_budget


def test_budget_restored_when_vision_on_and_zero():
    cfg = {"vision_backend": "gemini", "max_windows_per_video": 0}
    _ensure_vision_window_budget(cfg)
    assert cfg["max_windows_per_video"] == 20


def test_budget_untouched_when_already_set():
    cfg = {"vision_backend": "gemini", "max_windows_per_video": 30}
    _ensure_vision_window_budget(cfg)
    assert cfg["max_windows_per_video"] == 30


def test_budget_untouched_when_vision_off():
    cfg = {"vision_backend": "off", "max_windows_per_video": 0}
    _ensure_vision_window_budget(cfg)
    assert cfg["max_windows_per_video"] == 0


def test_budget_handles_missing_key():
    cfg = {"vision_backend": "groq"}
    _ensure_vision_window_budget(cfg)
    assert cfg["max_windows_per_video"] == 20
