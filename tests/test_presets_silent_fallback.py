"""Mode 1 visual reports are keyless — a vision-on preset needs no API key.

Mode 2 (autonomous Gemini/Groq vision) was removed, so vision_backend is now
an on/off gate and keyframe extraction is offline. A preset that requests
vision ('on') therefore resolves to 'on' whether or not any API key is set,
with no fallback message. Presets with vision off stay off and emit nothing.
"""
import pytest

from skills.neurolearn.presets.loader import resolve_with_env_checks


def test_standard_preset_vision_on_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: None,
    )

    vals, info_messages = resolve_with_env_checks("standard")
    assert vals["vision_backend"] == "on"  # keyless — Mode 1 needs no key
    assert not any("GEMINI_API_KEY" in m for m in info_messages)


def test_standard_preset_vision_on_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    vals, info_messages = resolve_with_env_checks("standard")
    assert vals["vision_backend"] == "on"
    assert info_messages == []


def test_smart_preset_unaffected_no_key_no_fallback(monkeypatch):
    """v0.10.6: smart preset has vision_backend=off already, so missing
    Gemini key triggers no fallback message — there's nothing to fall
    back from. Inverse of the eco case."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    vals, info_messages = resolve_with_env_checks("smart")
    assert vals["vision_backend"] == "off"
    # No "GEMINI_API_KEY missing" warning because vision wasn't requested.
    assert not any("GEMINI_API_KEY" in m for m in info_messages)


def test_eco_preset_unaffected_no_key_no_fallback(monkeypatch):
    """Eco has vision_backend=off already, no fallback needed."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    vals, _ = resolve_with_env_checks("eco")
    assert vals["vision_backend"] == "off"
