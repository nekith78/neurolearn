"""Tests for `config` sub-commands (Task 21).

Covers:
  - config show        — prints fields including masked API keys
  - config set         — updates config.toml field + validates keys/values
  - config set-key     — calls set_api_key (mocked), masked confirmation
  - config test        — calls is_configured() on the backend, different outputs
  - config wizard      — delegates to run_wizard
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------

class TestConfigShow:
    def test_show_prints_default_backend(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        monkeypatch.setattr("skills.neurolearn.config.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "show"])
        assert r.exit_code == 0, r.output
        assert "default_backend" in r.output

    def test_show_prints_api_key_status(self, tmp_path: Path, monkeypatch):
        """Each backend section should appear in show output."""
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        monkeypatch.setattr("skills.neurolearn.config.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "show"])
        assert r.exit_code == 0, r.output
        for backend in ["gemini", "groq", "openai", "deepgram", "assemblyai"]:
            assert backend in r.output

    def test_show_masks_api_key(self, tmp_path: Path, monkeypatch):
        """When an API key is present it must appear masked, never in full."""
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        monkeypatch.setattr("skills.neurolearn.config.CONFIG_PATH", tmp_path / "config.toml")
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=sk-1234567890abcdef\n", encoding="utf-8")

        with patch("skills.neurolearn.transcribe.get_api_key") as mock_get:
            mock_get.side_effect = lambda b: "sk-1234567890abcdef" if b == "gemini" else None
            r = _runner().invoke(cli, ["config", "show"])
        assert r.exit_code == 0, r.output
        # full key must NOT appear
        assert "sk-1234567890abcdef" not in r.output
        # masked form (first4***last4) must appear
        assert "sk-1" in r.output and "cdef" in r.output


# ---------------------------------------------------------------------------
# config set
# ---------------------------------------------------------------------------

class TestConfigSet:
    def test_set_backend_writes_toml(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "backend", "groq"])
        assert r.exit_code == 0, r.output
        text = (tmp_path / "config.toml").read_text()
        assert "groq" in text

    def test_set_language(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "language", "ru"])
        assert r.exit_code == 0, r.output
        text = (tmp_path / "config.toml").read_text()
        assert "ru" in text

    def test_set_whisper_model(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "whisper-model", "large"])
        assert r.exit_code == 0, r.output
        text = (tmp_path / "config.toml").read_text()
        assert "large" in text

    def test_set_unknown_key_exits_nonzero(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "unknown_key", "foo"])
        assert r.exit_code != 0
        assert "Unknown key" in r.output or "unknown_key" in r.output

    def test_set_backend_invalid_value_exits_nonzero(self, tmp_path: Path, monkeypatch):
        """Setting backend to a value not in BACKEND_CHOICES should fail."""
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "backend", "invalid-backend"])
        assert r.exit_code != 0

    def test_set_prints_confirmation(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "backend", "gemini"])
        assert r.exit_code == 0
        assert "gemini" in r.output

    def test_set_fallback(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "set", "fallback", "openai"])
        assert r.exit_code == 0
        text = (tmp_path / "config.toml").read_text()
        assert "openai" in text


# ---------------------------------------------------------------------------
# config set-key
# ---------------------------------------------------------------------------

class TestConfigSetKey:
    def test_set_key_gemini_calls_set_api_key(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
        r = _runner().invoke(cli, ["config", "set-key", "gemini"], input="test-key\n")
        assert r.exit_code == 0, r.output
        env_text = (tmp_path / ".env").read_text()
        assert "GEMINI_API_KEY=test-key" in env_text

    def test_set_key_shows_masked_confirmation(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
        r = _runner().invoke(cli, ["config", "set-key", "groq"], input="sk-abcdefgh12345678\n")
        assert r.exit_code == 0, r.output
        # full key must not appear in output
        assert "sk-abcdefgh12345678" not in r.output

    def test_set_key_rejects_invalid_backend(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
        r = _runner().invoke(cli, ["config", "set-key", "unknown_backend"])
        assert r.exit_code != 0

    def test_set_key_empty_input_not_saved(self, tmp_path: Path, monkeypatch):
        """Empty key (just Enter) should NOT save anything."""
        monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
        r = _runner().invoke(cli, ["config", "set-key", "gemini"], input="\n")
        # env file may not even be created, or it should not contain a blank key
        if (tmp_path / ".env").exists():
            env_text = (tmp_path / ".env").read_text()
            assert "GEMINI_API_KEY=\n" not in env_text


# ---------------------------------------------------------------------------
# config test
# ---------------------------------------------------------------------------

class TestConfigTest:
    def test_test_configured_backend_exits_zero(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        mock_backend = MagicMock()
        mock_backend.is_configured.return_value = (True, None)
        with patch("skills.neurolearn.transcribe.build_backend", return_value=mock_backend):
            r = _runner().invoke(cli, ["config", "test", "gemini"])
        assert r.exit_code == 0, r.output
        assert "gemini" in r.output.lower() or "configured" in r.output.lower()

    def test_test_unconfigured_backend_exits_nonzero(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        mock_backend = MagicMock()
        mock_backend.is_configured.return_value = (False, "API key missing")
        with patch("skills.neurolearn.transcribe.build_backend", return_value=mock_backend):
            r = _runner().invoke(cli, ["config", "test", "groq"])
        assert r.exit_code != 0
        assert "API key missing" in r.output or "groq" in r.output.lower()

    def test_test_invalid_backend_rejected(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        r = _runner().invoke(cli, ["config", "test", "not-a-backend"])
        assert r.exit_code != 0

    def test_test_build_backend_exception(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        with patch("skills.neurolearn.transcribe.build_backend", side_effect=ValueError("fail")):
            r = _runner().invoke(cli, ["config", "test", "gemini"])
        assert r.exit_code != 0


# ---------------------------------------------------------------------------
# config wizard
# ---------------------------------------------------------------------------

class TestConfigWizard:
    def test_wizard_calls_run_wizard(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
        with patch("skills.neurolearn.transcribe.run_wizard") as mock_wizard:
            r = _runner().invoke(cli, ["config", "wizard"])
        assert r.exit_code == 0, r.output
        mock_wizard.assert_called_once()
