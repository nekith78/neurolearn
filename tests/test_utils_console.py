"""Tests for the cross-platform Console factory (Bug A fix, v0.10.7).

The factory exists to keep `console.print("✓ ok")` from crashing on
Windows hosts with cp1251 / cp866 / cp936 code pages. We assert the
two behaviors that prevent the crash:

  1. On Darwin/Linux it returns a plain Console (no funny business).
  2. On win32 it forces `legacy_windows=False` so Rich emits ANSI
     escapes instead of going through the codepage-encoded
     `LegacyWindowsTerm` path.
"""
from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

from skills.neurolearn.utils.console import make_console


def test_make_console_on_darwin_no_force_legacy(monkeypatch):
    """On macOS / Linux the helper is a drop-in for plain Console()."""
    monkeypatch.setattr(sys, "platform", "darwin")
    c = make_console()
    # No assertion on legacy_windows — Rich on non-Windows ignores it
    # anyway. Just confirm we didn't raise and got a Console.
    assert c is not None


def test_make_console_on_win32_forces_legacy_windows_false():
    """On win32, legacy_windows must be False so Rich uses ANSI escapes
    instead of the codepage-encoded LegacyWindowsTerm path."""
    captured: dict = {}

    def spy_console(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("skills.neurolearn.utils.console.sys.platform", "win32"), \
         patch("skills.neurolearn.utils.console.Console", side_effect=spy_console):
        make_console()

    # The kwarg must be present AND False — the bug is when Rich falls
    # through to LegacyWindowsTerm.
    assert captured.get("legacy_windows") is False, captured


def test_make_console_on_win32_reconfigures_stdio_to_utf8():
    """Belt-and-braces: in addition to ANSI mode, stdout/stderr get
    reconfigured to UTF-8 with errors='replace' so any stray glyph
    in error text never crashes the process — it becomes '?'."""
    stdout_mock = MagicMock()
    stderr_mock = MagicMock()

    with patch("skills.neurolearn.utils.console.sys.platform", "win32"), \
         patch("skills.neurolearn.utils.console.sys.stdout", stdout_mock), \
         patch("skills.neurolearn.utils.console.sys.stderr", stderr_mock), \
         patch("skills.neurolearn.utils.console.Console", return_value=MagicMock()):
        make_console()

    # Both streams reconfigured with the same encoding/errors policy.
    for stream in (stdout_mock, stderr_mock):
        assert stream.reconfigure.call_count == 1
        kw = stream.reconfigure.call_args.kwargs
        assert kw["encoding"] == "utf-8"
        assert kw["errors"] == "replace"


def test_make_console_on_win32_survives_streams_without_reconfigure():
    """`sys.stdout.reconfigure` doesn't exist on every stream type
    (e.g. when stdout is redirected to a non-text stream by a wrapper).
    The factory must swallow that AttributeError, not crash."""
    bad_stream = MagicMock()
    bad_stream.reconfigure.side_effect = AttributeError(
        "stream has no reconfigure",
    )

    with patch("skills.neurolearn.utils.console.sys.platform", "win32"), \
         patch("skills.neurolearn.utils.console.sys.stdout", bad_stream), \
         patch("skills.neurolearn.utils.console.sys.stderr", bad_stream), \
         patch("skills.neurolearn.utils.console.Console", return_value=MagicMock()):
        # Must not raise.
        c = make_console()
    assert c is not None


def test_make_console_passes_kwargs_through():
    """Caller-supplied kwargs (record=True, width=120) reach Console."""
    captured: dict = {}

    def spy(**kw):
        captured.update(kw)
        return MagicMock()

    with patch("skills.neurolearn.utils.console.Console", side_effect=spy):
        make_console(record=True, width=120)

    assert captured.get("record") is True
    assert captured.get("width") == 120
