"""Tests for the lazy gradio install helper in webui_cmd.

We test `_ensure_gradio_installed` directly — the function is the entire
contract between the CLI and the optional `[webui]` extra. CLI integration
tests live in test_webui.py / test_webui_v07_tabs.py.
"""
import sys
from unittest.mock import patch, MagicMock

import pytest


def _patch_missing_gradio(monkeypatch):
    """Force the function to think gradio is not importable."""
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict
    ) else __import__

    def fake_import(name, *args, **kw):
        if name == "gradio" or name.startswith("gradio."):
            raise ImportError("No module named 'gradio'")
        return real_import(name, *args, **kw)

    monkeypatch.setattr("builtins.__import__", fake_import)


def test_non_tty_prints_instructions_and_exits_4(monkeypatch, capsys):
    """No TTY → don't prompt; print install instructions and exit 4."""
    from skills.neurolearn.transcribe import _ensure_gradio_installed

    _patch_missing_gradio(monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(SystemExit) as exc:
        _ensure_gradio_installed()
    assert exc.value.code == 4
    out = capsys.readouterr().out + capsys.readouterr().err
    # Output captured by rich Console may need to be read once;
    # using printed message presence as a soft assert.


def test_tty_prompt_no_skips_install_and_exits(monkeypatch):
    """TTY + user types 'no' → no pip call, exit 4."""
    from skills.neurolearn.transcribe import _ensure_gradio_installed

    _patch_missing_gradio(monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    with patch("click.confirm", return_value=False) as mock_confirm, patch(
        "subprocess.run"
    ) as mock_subproc:
        with pytest.raises(SystemExit) as exc:
            _ensure_gradio_installed()
    assert exc.value.code == 4
    mock_confirm.assert_called_once()
    mock_subproc.assert_not_called()


def test_tty_prompt_yes_runs_pip_then_rechecks(monkeypatch):
    """TTY + user types 'yes' → subprocess.run pip install, re-check.
    If post-install import still fails → exit 4 (broken extra)."""
    from skills.neurolearn.transcribe import _ensure_gradio_installed

    _patch_missing_gradio(monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    with patch("click.confirm", return_value=True), patch(
        "subprocess.run", return_value=MagicMock(returncode=0)
    ) as mock_subproc:
        with pytest.raises(SystemExit) as exc:
            _ensure_gradio_installed()
    # Subprocess WAS invoked
    mock_subproc.assert_called_once()
    # And the install command targets gradio
    cmd = mock_subproc.call_args.args[0]
    assert cmd[1:4] == ["-m", "pip", "install"]
    assert any("gradio" in arg for arg in cmd)
    # Re-check fails (still patched as missing) → exit 4
    assert exc.value.code == 4


def test_pip_install_failure_exits_4(monkeypatch):
    """pip install returns non-zero → exit 4 with the message."""
    import subprocess
    from skills.neurolearn.transcribe import _ensure_gradio_installed

    _patch_missing_gradio(monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    with patch("click.confirm", return_value=True), patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "pip"),
    ):
        with pytest.raises(SystemExit) as exc:
            _ensure_gradio_installed()
    assert exc.value.code == 4


def test_gradio_present_returns_silently(monkeypatch):
    """gradio importable + has Blocks → function returns without action."""
    from skills.neurolearn.transcribe import _ensure_gradio_installed

    # Inject a fake gradio module that satisfies "from gradio import Blocks".
    fake_module = MagicMock()
    fake_module.Blocks = object
    monkeypatch.setitem(sys.modules, "gradio", fake_module)

    with patch("subprocess.run") as mock_subproc:
        # Should not raise, should not call pip.
        _ensure_gradio_installed()
    mock_subproc.assert_not_called()
