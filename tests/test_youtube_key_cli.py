"""CLI behaviour of the optional YouTube API key: storing it, testing it,
seeing it in `doctor`, and never needing it.

The YouTube API transport (`youtube_api._http_get`) is the only thing faked.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from skills.neurolearn import youtube_api
from skills.neurolearn.config import Config, save_config
from skills.neurolearn.transcribe import BACKEND_CHOICES, cli
from skills.neurolearn.youtube_api import TransientFailure

FAKE_KEY = "AIzaFAKE-not-a-real-key-0123456789"


@pytest.fixture
def home(monkeypatch, tmp_path: Path) -> Path:
    """Isolated config dir with no YouTube key anywhere."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("skills.neurolearn.transcribe.ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")
    return tmp_path


@pytest.fixture
def transport(monkeypatch):
    """Fake transport; set `.response` or `.raises` per test."""

    class _Fake:
        response = (200, {"items": []})
        raises: Exception | None = None
        calls: list = []

        def __call__(self, url, params, headers, timeout):
            self.calls.append((url, params, headers))
            if self.raises is not None:
                raise self.raises
            return self.response

    fake = _Fake()
    fake.calls = []
    monkeypatch.setattr(youtube_api, "_http_get", fake)
    return fake


def _invoke(*args: str, **kwargs):
    return CliRunner().invoke(cli, list(args), **kwargs)


def _store_key(home: Path) -> None:
    r = _invoke("config", "set-key", "youtube", FAKE_KEY)
    assert r.exit_code == 0, r.output


class TestSetKey:
    def test_from_file_stores_the_key_masked(self, home):
        key_file = home / "yt-key.txt"
        key_file.write_text(FAKE_KEY + "\n", encoding="utf-8")
        r = _invoke("config", "set-key", "youtube", "--from-file", str(key_file))
        assert r.exit_code == 0, r.output
        assert f"YOUTUBE_API_KEY={FAKE_KEY}" in (home / ".env").read_text()
        assert FAKE_KEY not in r.output
        assert "AIza***6789" in r.output

    def test_positional_env_and_stdin_forms(self, home, monkeypatch):
        assert _invoke("config", "set-key", "youtube", "positional-key-123").exit_code == 0
        assert "YOUTUBE_API_KEY=positional-key-123" in (home / ".env").read_text()

        monkeypatch.setenv("MY_YT", "from-env-key-12345")
        assert _invoke("config", "set-key", "youtube", "--from-env", "MY_YT").exit_code == 0
        assert "YOUTUBE_API_KEY=from-env-key-12345" in (home / ".env").read_text()

        r = _invoke("config", "set-key", "youtube", "--from-stdin", input="stdin-key-1234567\n")
        assert r.exit_code == 0, r.output
        assert "YOUTUBE_API_KEY=stdin-key-1234567" in (home / ".env").read_text()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
    def test_secrets_file_is_owner_only(self, home):
        _store_key(home)
        assert stat.S_IMODE(os.stat(home / ".env").st_mode) == 0o600

    def test_other_keys_survive(self, home):
        assert _invoke("config", "set-key", "groq", "gsk_existing_value").exit_code == 0
        _store_key(home)
        text = (home / ".env").read_text()
        assert "GROQ_API_KEY=gsk_existing_value" in text
        assert f"YOUTUBE_API_KEY={FAKE_KEY}" in text

    def test_config_show_masks_the_key(self, home, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", FAKE_KEY)
        r = _invoke("config", "show")
        assert r.exit_code == 0, r.output
        assert "youtube" in r.output
        assert "AIza***6789" in r.output
        assert FAKE_KEY not in r.output


class TestKeyBackendOnly:
    def test_not_a_backend_choice(self):
        assert "youtube" not in BACKEND_CHOICES

    @pytest.mark.parametrize("field", ["default_backend", "fallback_backend", "analyze_backend"])
    def test_config_set_rejects_youtube_as_a_backend(self, home, field):
        r = _invoke("config", "set", field, "youtube")
        assert r.exit_code != 0

    @pytest.mark.parametrize("command", ["transcribe", "batch"])
    def test_backend_flag_rejects_youtube(self, home, command):
        r = _invoke(command, "https://youtu.be/abc", "--backend", "youtube")
        assert r.exit_code == 2
        assert "youtube" in r.output


class TestConfigTestYoutube:
    def test_valid_key(self, home, transport):
        _store_key(home)
        r = _invoke("config", "test", "youtube")
        assert r.exit_code == 0, r.output
        assert "key is valid" in r.output
        assert len(transport.calls) == 1

    def test_invalid_key(self, home, transport):
        _store_key(home)
        transport.response = (400, {"error": {
            "code": 400, "message": f"API key {FAKE_KEY} not valid.",
            "errors": [{"reason": "keyInvalid"}],
        }})
        r = _invoke("config", "test", "youtube")
        assert r.exit_code == 4
        assert "rejected" in r.output
        assert FAKE_KEY not in r.output

    def test_network_failure(self, home, transport):
        _store_key(home)
        transport.raises = TransientFailure("ConnectError: no route to host")
        r = _invoke("config", "test", "youtube")
        assert r.exit_code == 5
        assert "could not reach" in r.output.lower()
        assert "rejected" not in r.output
        assert FAKE_KEY not in r.output

    def test_no_key(self, home, transport):
        r = _invoke("config", "test", "youtube")
        assert r.exit_code == 3
        assert "not set" in r.output
        assert transport.calls == []

    def test_quota_spent_still_means_the_key_works(self, home, transport):
        _store_key(home)
        transport.response = (403, {"error": {
            "code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded"}],
        }})
        r = _invoke("config", "test", "youtube")
        assert r.exit_code == 0, r.output
        assert "quota" in r.output.lower()

    def test_three_outcomes_print_different_messages(self, home, transport):
        _store_key(home)
        valid = _invoke("config", "test", "youtube").output
        transport.response = (400, {"error": {"code": 400, "errors": [{"reason": "keyInvalid"}]}})
        invalid = _invoke("config", "test", "youtube").output
        transport.raises = TransientFailure("timeout")
        network = _invoke("config", "test", "youtube").output
        assert len({valid, invalid, network}) == 3


class TestDoctor:
    def test_json_without_key(self, home):
        r = _invoke("doctor", "--json")
        assert r.exit_code == 0, r.output
        yt = json.loads(r.output)["youtube"]
        assert yt["key_configured"] is False
        assert "masked" not in yt
        assert yt["key_url"].startswith("https://")

    def test_json_with_key(self, home):
        _store_key(home)
        r = _invoke("doctor", "--json")
        assert r.exit_code == 0, r.output
        assert FAKE_KEY not in r.output
        yt = json.loads(r.output)["youtube"]
        assert yt["key_configured"] is True
        assert yt["masked"] == "AIza***6789"

    def test_human_without_key(self, home):
        r = _invoke("doctor")
        assert r.exit_code == 0, r.output
        assert "YouTube Data API" in r.output
        assert "key: not set (optional)" in r.output

    def test_human_with_key(self, home):
        _store_key(home)
        r = _invoke("doctor")
        assert r.exit_code == 0, r.output
        assert "key: AIza***6789" in r.output
        assert FAKE_KEY not in r.output

    def test_missing_key_is_not_a_readiness_problem(self, home):
        without = json.loads(_invoke("doctor", "--json").output)
        _store_key(home)
        with_key = json.loads(_invoke("doctor", "--json").output)
        assert without["ready"] == with_key["ready"]
        assert "youtube" not in without["keys"]
        assert not any("youtube" in s["step"] for s in without["ready"]["recommended_setup"])


class TestKeyIsOptional:
    def test_onboarding_completes_without_key(self, home):
        r = _invoke("config", "complete-onboarding")
        assert r.exit_code == 0, r.output
        data = json.loads(_invoke("doctor", "--json").output)
        assert data["config"]["onboarding_complete"] is True
        assert data["youtube"]["key_configured"] is False

    def test_work_command_runs_without_key(self, home, monkeypatch):
        """`transcribe` gets past setup checks to target resolution with no
        YouTube key, and says nothing about the missing key."""
        save_config(Config(onboarding_complete=True), home / "config.toml")
        reached: list[str] = []

        def _resolve(*args, **kwargs):
            reached.append("resolve")
            return [], [MagicMock(reason="test-stop")]

        monkeypatch.setattr("skills.neurolearn.transcribe.resolve", _resolve)
        r = _invoke("transcribe", "https://youtu.be/abc", "--backend", "subtitles")
        assert reached == ["resolve"], r.output
        assert r.exit_code != 7
        assert "youtube api" not in r.output.lower()
        assert "YOUTUBE_API_KEY" not in r.output
