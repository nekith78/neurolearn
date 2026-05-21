"""Tests for `neurolearn doctor` — diagnostic command for Claude Code plugin UX.

`doctor` reports config + API-key state in human-readable form (default) or
machine-readable JSON (--json). Claude parses --json to drive the onboarding
flow when keys are missing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def _runner() -> CliRunner:
    return CliRunner()


def _wire_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
    # config module also reads ENV_PATH for get_api_key
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")


class TestDoctorHumanOutput:
    def test_doctor_runs_without_config_file(self, tmp_path, monkeypatch):
        """First-run case: no config file yet — doctor must NOT crash."""
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor"])
        assert r.exit_code == 0, r.output

    def test_doctor_marks_missing_config_explicitly(self, tmp_path, monkeypatch):
        """Output must clearly say config is missing (not silently show defaults)."""
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor"])
        assert r.exit_code == 0
        assert "NOT PRESENT" in r.output or "missing" in r.output.lower()

    def test_doctor_lists_all_backend_keys(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor"])
        assert r.exit_code == 0
        for backend in ["gemini", "groq", "openai", "deepgram", "assemblyai"]:
            assert backend in r.output.lower()

    def test_doctor_shows_masked_key_when_set(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_supersecret12345\n")
        r = _runner().invoke(cli, ["doctor"])
        assert r.exit_code == 0, r.output
        # Full key MUST NOT appear
        assert "gsk_supersecret12345" not in r.output
        # Mask hint should be visible (asterisks or ***)
        assert "*" in r.output


class TestDoctorJsonOutput:
    def test_json_output_is_valid_json(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert isinstance(data, dict)

    def test_json_has_required_top_level_fields(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        # Claude reads these to drive onboarding
        for field in ["version", "config_file", "config", "keys", "platform", "ready"]:
            assert field in data, f"missing field {field!r}: {list(data)}"

    def test_json_config_file_section(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        assert "path" in data["config_file"]
        assert "exists" in data["config_file"]
        assert data["config_file"]["exists"] is False  # no file written

    def test_json_keys_section_lists_all_backends(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        for backend in ["gemini", "groq", "openai", "deepgram", "assemblyai"]:
            assert backend in data["keys"]
            assert "configured" in data["keys"][backend]
            assert "key_url" in data["keys"][backend]
            assert data["keys"][backend]["configured"] is False

    def test_json_key_marked_configured_when_set(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_abcdef1234567890\n")
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        assert data["keys"]["groq"]["configured"] is True
        # masked key must be present, full key absent
        assert "masked" in data["keys"]["groq"]
        assert "gsk_abcdef1234567890" not in r.output

    def test_json_ready_section_reports_no_fast_audio_when_no_keys(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        assert data["ready"]["has_fast_audio"] is False
        # Always have an offline fallback (whisper-local) — true
        assert data["ready"]["has_offline_fallback"] is True
        # recommended_setup must be a non-empty list when not ready
        assert isinstance(data["ready"]["recommended_setup"], list)
        assert len(data["ready"]["recommended_setup"]) > 0

    def test_json_ready_with_groq_key(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_ok\n")
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        assert data["ready"]["has_fast_audio"] is True

    def test_json_platform_section(self, tmp_path, monkeypatch):
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        data = json.loads(r.output)
        assert "system" in data["platform"]  # e.g. "darwin" / "linux" / "windows"
        assert "label" in data["platform"]  # human label like "macOS arm64 (mlx-whisper)"

    def test_json_exit_code_zero_even_when_not_ready(self, tmp_path, monkeypatch):
        """`doctor --json` should ALWAYS exit 0 if it produced valid JSON.
        Non-zero would mean Claude couldn't parse our diagnostics."""
        _wire_paths(monkeypatch, tmp_path)
        r = _runner().invoke(cli, ["doctor", "--json"])
        assert r.exit_code == 0
