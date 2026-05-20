"""v0.10.9 Fix H: wizard handling in non-TTY contexts.

Before the fix, `transcribe` / `batch` invocations from non-TTY
contexts (Claude Code subprocess, CI, piped commands) hit
`run_wizard()` on first run because `CONFIG_PATH` didn't exist —
then the wizard immediately hit EOF on stdin and aborted the
whole command with `Aborted!`.

Now the helper `_ensure_config_or_skip_wizard()`:
  * If config exists → no-op.
  * If config missing AND TTY → run wizard (legacy behavior).
  * If config missing AND non-TTY → write default Config silently,
    print a stderr notice.

`config show` also distinguishes "present" vs "NOT PRESENT — showing
defaults" so users don't think a missing file is a real config.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.neurolearn.transcribe import (
    _ensure_config_or_skip_wizard, cli,
)


def test_helper_noop_when_config_already_exists(tmp_path: Path):
    """Fast path: existing config means we don't touch anything."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('default_backend = "whisper-local"\n', encoding="utf-8")
    with patch(
        "skills.neurolearn.transcribe.CONFIG_PATH", cfg_path,
    ), patch(
        "skills.neurolearn.transcribe.run_wizard",
    ) as mock_wizard, patch(
        "skills.neurolearn.transcribe.save_config",
    ) as mock_save:
        _ensure_config_or_skip_wizard()
    mock_wizard.assert_not_called()
    mock_save.assert_not_called()


def test_helper_runs_wizard_when_tty_and_no_config(tmp_path: Path):
    """TTY first run: wizard fires as before."""
    cfg_path = tmp_path / "nope.toml"
    with patch(
        "skills.neurolearn.transcribe.CONFIG_PATH", cfg_path,
    ), patch(
        "skills.neurolearn.transcribe._stdin_is_tty", return_value=True,
    ), patch(
        "skills.neurolearn.transcribe.run_wizard",
    ) as mock_wizard, patch(
        "skills.neurolearn.transcribe.save_config",
    ) as mock_save:
        _ensure_config_or_skip_wizard()
    mock_wizard.assert_called_once()
    mock_save.assert_not_called()


def test_helper_writes_default_config_when_non_tty(tmp_path: Path):
    """Non-TTY first run: NO wizard, write defaults instead, continue."""
    cfg_path = tmp_path / "no_config_yet.toml"
    with patch(
        "skills.neurolearn.transcribe.CONFIG_PATH", cfg_path,
    ), patch(
        "skills.neurolearn.transcribe._stdin_is_tty", return_value=False,
    ), patch(
        "skills.neurolearn.transcribe.run_wizard",
    ) as mock_wizard, patch(
        "skills.neurolearn.transcribe.save_config",
    ) as mock_save:
        _ensure_config_or_skip_wizard()
    # The blocking call must not happen — that's the whole point.
    mock_wizard.assert_not_called()
    # And we wrote a default-shaped Config so downstream code can
    # load_config() without crashing.
    mock_save.assert_called_once()
    saved_cfg = mock_save.call_args.args[0]
    assert saved_cfg.default_backend == "whisper-local"


def test_config_show_marks_file_as_not_present_when_missing(tmp_path: Path):
    """`config show` against a missing file used to look exactly like
    a real config (just full of defaults). Now it surfaces the
    'NOT PRESENT' marker so the user isn't confused."""
    cfg_path = tmp_path / "missing.toml"
    with patch("skills.neurolearn.transcribe.CONFIG_PATH", cfg_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "NOT PRESENT" in result.output


def test_config_show_marks_file_as_present_when_real(tmp_path: Path):
    """And conversely, when the file exists, the marker says 'present'."""
    cfg_path = tmp_path / "real.toml"
    cfg_path.write_text('default_backend = "whisper-local"\n', encoding="utf-8")
    with patch("skills.neurolearn.transcribe.CONFIG_PATH", cfg_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "present" in result.output.lower()
    assert "NOT PRESENT" not in result.output
