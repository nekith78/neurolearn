"""Tests for `triggers weight set/unset/list`."""
import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_weight_set_converts_string_to_array(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function"])
    res = runner.invoke(
        triggers_cli, ["weight", "set", "--universal", "function", "1.5"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    # Should now be ["function", 1.5] format
    assert '"function"' in content
    assert "1.5" in content


def test_weight_set_batch_format(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function; class; method"])
    res = runner.invoke(
        triggers_cli,
        ["weight", "set", "--universal", "function:1.5; class:1.5; method:1.5"],
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert content.count("1.5") >= 3


def test_weight_unset_returns_to_string(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function"])
    runner.invoke(triggers_cli, ["weight", "set", "--universal", "function", "1.5"])
    res = runner.invoke(triggers_cli, ["weight", "unset", "--universal", "function"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    # Should no longer have the array form for "function"
    assert '"function"' in content
    assert '["function", 1.5]' not in content


def test_weight_list_shows_only_weighted(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "regular phrase; weighted phrase"])
    runner.invoke(
        triggers_cli, ["weight", "set", "--universal", "weighted phrase", "2.0"]
    )
    res = runner.invoke(triggers_cli, ["weight", "list"])
    assert res.exit_code == 0
    assert "weighted phrase" in res.output
    # "regular phrase" has weight 1.0 (default), should NOT be in list
    assert "regular phrase" not in res.output
