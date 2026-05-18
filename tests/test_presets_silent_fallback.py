"""When vision_backend=gemini but no API key — silent fallback to off.

v0.10.6 note: the `smart` preset no longer has vision_backend=gemini by
default, so these tests exercise the `standard` preset (which still
does). The fallback logic itself is preset-agnostic — any preset that
requests a vision backend without the matching API key will silently
fall back to "off" with an info message.
"""
import pytest

from skills.neurolearn.presets.loader import resolve_with_env_checks


def test_standard_preset_gemini_without_key_falls_back(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: None,
    )

    vals, info_messages = resolve_with_env_checks("standard")
    assert vals["vision_backend"] == "off"
    assert any("GEMINI_API_KEY" in m for m in info_messages)


def test_standard_preset_gemini_with_key_kept(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    vals, info_messages = resolve_with_env_checks("standard")
    assert vals["vision_backend"] == "gemini"
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
