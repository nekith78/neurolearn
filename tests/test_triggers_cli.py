"""Tests for `youtube-transcribe triggers` CLI sub-group."""
from pathlib import Path

import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_init_creates_file(tmp_user_path):
    runner = CliRunner()
    res = runner.invoke(triggers_cli, ["init"])
    assert res.exit_code == 0
    assert tmp_user_path.exists()
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "[triggers.universal]" in content
    assert "phrases =" in content


def test_init_force_overwrites(tmp_user_path):
    runner = CliRunner()
    tmp_user_path.write_text("garbage", encoding="utf-8")
    res = runner.invoke(triggers_cli, ["init", "--force"])
    assert res.exit_code == 0
    assert "[triggers.universal]" in tmp_user_path.read_text(encoding="utf-8")


def test_init_without_force_refuses_overwrite(tmp_user_path):
    runner = CliRunner()
    tmp_user_path.write_text("garbage", encoding="utf-8")
    res = runner.invoke(triggers_cli, ["init"])
    assert res.exit_code != 0
    assert "exists" in res.output.lower()


def test_add_universal_phrases(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(
        triggers_cli, ["add", "--universal", "look here; pay attention; hello world"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "look here" in content
    assert "pay attention" in content
    assert "hello world" in content


def test_add_dedupes(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    res = runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    assert res.exit_code == 0
    assert "already exists" in res.output.lower()
    # File should still contain only one occurrence
    assert tmp_user_path.read_text(encoding="utf-8").count('"look here"') == 1


def test_add_strict_per_lang(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(
        triggers_cli, ["add", "--strict", "--lang", "ru", "баг; PR"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "[triggers.languages.ru]" in content
    assert "баг" in content


def test_remove_phrase(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here; remove me"])
    res = runner.invoke(triggers_cli, ["remove", "--universal", "remove me"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "remove me" not in content
    assert "look here" in content


def test_list_command(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    res = runner.invoke(triggers_cli, ["list"])
    assert res.exit_code == 0
    assert "look here" in res.output
