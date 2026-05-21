"""Tests for first-run interactive wizard (v0.12.1 3-stage flow).

The wizard now prompts in this order:
  1. Audio backend     (always)
  2. Smart fallback    (only if audio = "smart")
  3. Vision backend    (always)
  4. Analyze backend   (always)
  5. Gemini tier       (if Gemini in any stage)
  6. Gemini overrides  (if Gemini tier = paid)
  7. Gemini URL fast-path Y/N (if Gemini tier = paid)
  8. Groq tier         (if Groq in any stage)
  9. Groq overrides    (if Groq tier = paid)
 10. API key prompts   (for each cloud backend chosen + not already set)

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


_FAKE_PLATFORM = PlatformInfo(
    label="cpu-only",
    backend_impl="faster",
    device="cpu",
    vram_mb=None,
    recommended_compute_type="int8",
)


def _run_wizard(tmp_path: Path, monkeypatch, prompts: list[str]):
    """Helper: patch paths + detect_platform + Prompt.ask, run the wizard.

    v0.12.2: the wizard now exits with code 2 if stdin is not a TTY (to
    prevent silent hangs when Claude Code invokes it as a subprocess).
    Tests need to spoof sys.stdin.isatty() = True to bypass this guard.
    """
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=prompts),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()
    return load_config(tmp_path / "config.toml")


# Audio menu: 1=smart, 2=groq, 3=whisper-local, 4=subtitles, 5=gemini,
#             6=openai, 7=deepgram, 8=assemblyai, 9=custom.
# Vision menu: 1=groq, 2=gemini, 3=off.
# Analyze menu: 1=groq, 2=gemini, 3=ollama, 4=skip.
# Tier menus: 1=free, 2=paid (groq) / 2=paid 3=paid-tier2 4=paid-tier3 (gemini).


# ---------------------------------------------------------------------------
# Pure-local path: no cloud backend → no tier / key prompts
# ---------------------------------------------------------------------------

def test_wizard_pure_local_path(tmp_path: Path, monkeypatch):
    """audio=whisper-local + vision=off + analyze=skip → no API keys asked,
    no tier prompts, no .env written."""
    cfg = _run_wizard(
        tmp_path, monkeypatch,
        prompts=["3", "3", "4"],  # whisper-local / vision off / analyze skip
    )
    assert cfg.default_backend == "whisper-local"
    assert cfg.vision_backend == "off"
    assert cfg.analyze_backend is None  # "skip" → None
    assert not (tmp_path / ".env").exists()


# ---------------------------------------------------------------------------
# Smart path with Groq fallback + Groq vision + Groq analyze
# ---------------------------------------------------------------------------

def test_wizard_smart_path_with_groq_everywhere(tmp_path: Path, monkeypatch):
    """audio=smart, fallback=groq (1), vision=groq, analyze=groq, groq tier=free.
    Skip the API-key prompt by entering empty string."""
    cfg = _run_wizard(
        tmp_path, monkeypatch,
        prompts=[
            "1",   # audio: smart
            "1",   # smart fallback: groq
            "1",   # vision: groq
            "1",   # analyze: groq
            "1",   # groq tier: free
            "",    # groq API key (skip)
        ],
    )
    assert cfg.default_backend == "smart"
    assert cfg.fallback_backend == "groq"
    assert cfg.vision_backend == "groq"
    assert cfg.analyze_backend == "groq"
    assert cfg.groq_tier == "free"


# ---------------------------------------------------------------------------
# Gemini in any stage triggers gemini tier prompt
# ---------------------------------------------------------------------------

def test_wizard_gemini_audio_triggers_tier_prompt(tmp_path: Path, monkeypatch):
    """audio=gemini, vision=off, analyze=skip, gemini tier=free."""
    cfg = _run_wizard(
        tmp_path, monkeypatch,
        prompts=[
            "5",         # audio: gemini
            "3",         # vision: off
            "4",         # analyze: skip
            "1",         # gemini tier: free
            "test-key",  # gemini API key
        ],
    )
    assert cfg.default_backend == "gemini"
    assert cfg.gemini_tier == "free"
    env_text = (tmp_path / ".env").read_text()
    assert "GEMINI_API_KEY=test-key" in env_text


# ---------------------------------------------------------------------------
# Paid Gemini tier unlocks model-override prompts
# ---------------------------------------------------------------------------

def test_wizard_paid_gemini_unlocks_model_overrides(tmp_path: Path, monkeypatch):
    """audio=gemini, gemini tier=paid → wizard prompts for model overrides
    + URL fast-path Y/N. We accept defaults via empty strings."""
    cfg = _run_wizard(
        tmp_path, monkeypatch,
        prompts=[
            "5",                  # audio: gemini
            "3",                  # vision: off
            "4",                  # analyze: skip
            "2",                  # gemini tier: paid (Tier 1)
            "gemini-3.5-pro",     # audio model override
            "y",                  # enable URL fast-path
            "test-paid-key",      # gemini key
        ],
    )
    assert cfg.gemini_tier == "paid"
    # Override accepted — paid users can pick 3.5-pro.
    assert cfg.gemini_model == "gemini-3.5-pro"
    assert cfg.gemini_url_fastpath is True


# ---------------------------------------------------------------------------
# Free-tier Gemini does NOT show override prompts
# ---------------------------------------------------------------------------

def test_wizard_free_gemini_skips_model_overrides(tmp_path: Path, monkeypatch):
    """When tier=free, no model override or URL fast-path Y/N is asked.
    The wizard would StopIteration if it tried to read more prompts than
    we provided."""
    cfg = _run_wizard(
        tmp_path, monkeypatch,
        prompts=[
            "5",        # audio: gemini
            "3",        # vision: off
            "4",        # analyze: skip
            "1",        # gemini tier: free
            "free-key", # gemini key
        ],
    )
    # Confirm wizard didn't somehow set paid-tier signals.
    assert cfg.gemini_tier == "free"
    assert cfg.gemini_url_fastpath is False
    # Defaults preserved — no override was applied
    assert cfg.gemini_model == "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Default config has v0.12.1 fields
# ---------------------------------------------------------------------------

def test_default_config_has_v012_1_fields():
    from skills.neurolearn.config import DEFAULT_CONFIG
    # v0.12.1 added these new fields — verify they exist with sensible defaults.
    assert DEFAULT_CONFIG.vision_backend == "off"
    assert DEFAULT_CONFIG.groq_tier == "free"
    assert DEFAULT_CONFIG.gemini_vision_model == ""
    assert DEFAULT_CONFIG.gemini_analyze_model == ""
    assert DEFAULT_CONFIG.groq_vision_model == ""
    assert DEFAULT_CONFIG.groq_analyze_model == ""


# ---------------------------------------------------------------------------
# detect_platform called once
# ---------------------------------------------------------------------------

def test_wizard_calls_detect_platform_once(tmp_path: Path, monkeypatch):
    """Pick whisper-local + vision=off + analyze=skip → 3 prompts total."""
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)  # v0.12.2 guard
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM) as mock_dp,
        patch("rich.prompt.Prompt.ask", side_effect=["3", "3", "4"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()
    mock_dp.assert_called_once()


# ---------------------------------------------------------------------------
# v0.12.2 non-TTY guard
# ---------------------------------------------------------------------------

def test_wizard_exits_when_not_tty(tmp_path: Path, monkeypatch, capsys):
    """When stdin is not a TTY (e.g. Claude Code subprocess), wizard must
    exit cleanly with code 2 instead of hanging or crashing with EOFError."""
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    from skills.neurolearn.wizard import run_wizard
    with pytest.raises(SystemExit) as excinfo:
        run_wizard()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "interactive" in err.lower()
    assert "TTY" in err or "tty" in err
    # Must point at the non-interactive escape hatches:
    assert "config set-key" in err
    assert "config set" in err


# ---------------------------------------------------------------------------
# Config persisted on disk
# ---------------------------------------------------------------------------

def test_wizard_config_persisted_to_disk(tmp_path: Path, monkeypatch):
    """Pure-local path persists config.toml."""
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr("skills.neurolearn.wizard.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("skills.neurolearn.wizard.ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)  # v0.12.2 guard
    with (
        patch("skills.neurolearn.wizard.detect_platform", return_value=_FAKE_PLATFORM),
        patch("rich.prompt.Prompt.ask", side_effect=["3", "3", "4"]),
    ):
        from skills.neurolearn.wizard import run_wizard
        run_wizard()
    assert cfg_path.exists()
