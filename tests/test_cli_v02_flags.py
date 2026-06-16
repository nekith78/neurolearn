"""Tests for v0.2 CLI flags surface area."""
from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def test_cli_help_shows_v02_flags():
    runner = CliRunner()
    res = runner.invoke(cli, ["transcribe", "--help"])
    assert res.exit_code == 0
    assert "--with-visuals" in res.output
    assert "--vision-backend" in res.output
    assert "--detect-method" in res.output
    assert "--preset" in res.output
    assert "--config" in res.output


def test_cli_triggers_subgroup_registered():
    runner = CliRunner()
    res = runner.invoke(cli, ["triggers", "--help"])
    assert res.exit_code == 0
    assert "init" in res.output
    assert "add" in res.output


def test_invalid_preset_value_rejected():
    runner = CliRunner()
    res = runner.invoke(cli, ["transcribe", "--preset", "nonexistent_preset", "fake-url"])
    assert res.exit_code != 0
