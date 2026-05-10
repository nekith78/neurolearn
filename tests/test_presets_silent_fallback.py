"""When vision_backend=gemini but no API key — silent fallback to off."""
import pytest

from skills.youtube_transcribe.presets.loader import resolve_with_env_checks


def test_smart_preset_gemini_without_key_falls_back(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )

    vals, info_messages = resolve_with_env_checks("smart")
    assert vals["vision_backend"] == "off"
    assert any("GEMINI_API_KEY" in m for m in info_messages)


def test_smart_preset_gemini_with_key_kept(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    vals, info_messages = resolve_with_env_checks("smart")
    assert vals["vision_backend"] == "gemini"
    assert info_messages == []


def test_eco_preset_unaffected_no_key_no_fallback(monkeypatch):
    """Eco has vision_backend=off already, no fallback needed."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    vals, _ = resolve_with_env_checks("eco")
    assert vals["vision_backend"] == "off"
