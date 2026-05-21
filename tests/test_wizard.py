"""Tests for first-run interactive wizard.

All tests are driven via monkeypatching ``rich.prompt.Prompt.ask`` so no
real TTY interaction is needed.  Nothing is written to ``~/.neurolearn/``;
every test redirects CONFIG_PATH / ENV_PATH to a tmp_path directory.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.config import Config, load_config
from skills.neurolearn.utils.platform_detect import PlatformInfo


# ---------------------------------------------------------------------------
# Shared fixture — fake platform info (cpu-only, no GPU)
# ---------------------------------------------------------------------------

_FAKE_PLATFORM = PlatformInfo(
    label="cpu-only",
    backend_impl="faster",
    device="cpu",
    vram_mb=None,
    recommended_compute_type="int8",
)


def _run_wizard_isolated(tmp_path: Path, monkeypatch, prompt_side_effects: list[str]):
    """Helper: patch paths + detect_platform + Prompt.ask, then run the wizard."""
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effects),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()
    return load_config(tmp_path / "config.toml")


# ---------------------------------------------------------------------------
# Test 1 — whisper-local (default choice "1")
# ---------------------------------------------------------------------------

def test_wizard_whisper_local_choice_writes_config(tmp_path: Path, monkeypatch):
    """v0.11.0 menu order: 1=smart, 2=groq, 3=whisper-local, 4=subtitles,
    5=gemini, 6=openai, 7=deepgram, 8=assemblyai, 9=custom.
    Choosing option 3 (whisper-local) saves config; no API key prompt."""
    cfg = _run_wizard_isolated(tmp_path, monkeypatch, prompt_side_effects=["3"])
    assert cfg.default_backend == "whisper-local"
    assert not (tmp_path / ".env").exists(), ".env must NOT be created for offline backend"


# ---------------------------------------------------------------------------
# Test 2 — subtitles (option 3)
# ---------------------------------------------------------------------------

def test_wizard_subtitles_choice_no_key(tmp_path: Path, monkeypatch):
    """Choosing subtitles (option 4 in v0.11.0 menu) saves config without touching .env."""
    cfg = _run_wizard_isolated(tmp_path, monkeypatch, prompt_side_effects=["4"])
    assert cfg.default_backend == "subtitles"
    assert not (tmp_path / ".env").exists()


# ---------------------------------------------------------------------------
# Test 3 — gemini (option 4) → prompts for API key
# ---------------------------------------------------------------------------

def test_wizard_gemini_choice_prompts_for_key(tmp_path: Path, monkeypatch):
    """Choosing gemini (option 5 in v0.11.0 menu) should save config and write GEMINI_API_KEY to .env."""
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    # First call = backend choice "5" (gemini), second = API key value
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=["5", "test-key-123"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()

    cfg = load_config(tmp_path / "config.toml")
    assert cfg.default_backend == "gemini"
    env_text = (tmp_path / ".env").read_text()
    assert "GEMINI_API_KEY=test-key-123" in env_text


# ---------------------------------------------------------------------------
# Test 4 — smart (option 2) → asks for fallback, no API key
# ---------------------------------------------------------------------------

def test_wizard_smart_choice_asks_fallback(tmp_path: Path, monkeypatch):
    """Choosing smart (option 1 in v0.11.0) should prompt for fallback and save both.

    v0.11.0 fallback options: 1=groq, 2=whisper-local, 3=gemini.
    """
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    # First call = "1" (smart), second call = "3" (gemini as fallback in new order)
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=["1", "3"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()

    cfg = load_config(tmp_path / "config.toml")
    assert cfg.default_backend == "smart"
    assert cfg.fallback_backend == "gemini"
    assert not (tmp_path / ".env").exists()


# ---------------------------------------------------------------------------
# Test 5 — groq (option 5) → key saved; empty key skips .env write
# ---------------------------------------------------------------------------

def test_wizard_groq_empty_key_skips_env(tmp_path: Path, monkeypatch):
    """When user presses Enter without typing a key the .env must not be written.

    v0.11.0: groq is option 2 (was 5 in pre-v0.11 menu order).
    """
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    # "2" = groq (v0.11.0), "" = skip key
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=["2", ""]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()

    cfg = load_config(tmp_path / "config.toml")
    assert cfg.default_backend == "groq"
    assert not (tmp_path / ".env").exists()


# ---------------------------------------------------------------------------
# Test 6 — detect_platform is called once
# ---------------------------------------------------------------------------

def test_wizard_calls_detect_platform_once(tmp_path: Path, monkeypatch):
    """v0.11.0: pick "3" (whisper-local) to avoid the second fallback prompt
    that "1" (smart) now triggers."""
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM) as mock_dp,
        patch("rich.prompt.Prompt.ask", side_effect=["3"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()

    mock_dp.assert_called_once()


# ---------------------------------------------------------------------------
# Test 7 — config is actually persisted on disk
# ---------------------------------------------------------------------------

def test_wizard_config_persisted_to_disk(tmp_path: Path, monkeypatch):
    """v0.11.0: pick "3" (whisper-local) to avoid the smart fallback prompt."""
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=["3"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()

    assert cfg_path.exists(), "config.toml must be written to disk"
