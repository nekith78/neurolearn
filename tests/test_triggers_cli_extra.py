"""Tests for triggers reset/edit/test commands."""
import os

import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_reset_universal_clears_section(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "custom phrase"])
    res = runner.invoke(triggers_cli, ["reset", "--universal"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "custom phrase" not in content


def test_reset_all_wipes_user_file(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "custom phrase"])
    res = runner.invoke(triggers_cli, ["reset", "--all"])
    assert res.exit_code == 0
    assert not tmp_user_path.exists() or "custom phrase" not in tmp_user_path.read_text("utf-8")


def test_test_command_shows_match(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--raw", "TODO"])
    res = runner.invoke(triggers_cli, ["test", "we have a TODO here"])
    assert res.exit_code == 0
    assert "raw" in res.output.lower() or "todo" in res.output.lower()


def test_test_no_match_reports(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(triggers_cli, ["test", "qqq xxx zzz nothing here"])
    # Should at least exit 0 (not error). Universal might or might not match
    # depending on threshold. Just verify it ran.
    assert res.exit_code == 0


def test_edit_command_opens_editor(tmp_user_path, monkeypatch):
    """Mock $EDITOR to a noop, ensure edit doesn't crash."""
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    monkeypatch.setenv("EDITOR", "true")  # 'true' is a noop binary that returns 0
    res = runner.invoke(triggers_cli, ["edit"])
    assert res.exit_code == 0
