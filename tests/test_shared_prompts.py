"""Tests for shared.prompts — interactive URL/query prompts with non-TTY guard."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from skills.neurolearn.shared import prompts


def test_prompt_url_exits_2_when_non_tty():
    """Non-TTY callers must fail fast (exit 2) instead of hanging on stdin."""
    with patch.object(prompts, "_is_tty", return_value=False):
        with pytest.raises(SystemExit) as exc:
            prompts.prompt_url_or_die()
    assert exc.value.code == 2


def test_prompt_url_returns_trimmed_value_when_tty():
    fake_q = MagicMock()
    fake_q.text.return_value.ask.return_value = "  https://example.com/x  "

    with patch.object(prompts, "_is_tty", return_value=True), \
         patch.dict(sys.modules, {"questionary": fake_q}):
        out = prompts.prompt_url_or_die("Paste URL:")
    assert out == "https://example.com/x"
    fake_q.text.assert_called_once_with("Paste URL:")


def test_prompt_url_exits_2_on_empty_input():
    """Pressing Enter with no text → exit 2, not silently continue."""
    fake_q = MagicMock()
    fake_q.text.return_value.ask.return_value = "   "

    with patch.object(prompts, "_is_tty", return_value=True), \
         patch.dict(sys.modules, {"questionary": fake_q}):
        with pytest.raises(SystemExit) as exc:
            prompts.prompt_url_or_die()
    assert exc.value.code == 2


def test_prompt_url_exits_130_on_ctrl_c():
    """questionary returns None on Ctrl+C / Esc — exit with SIGINT convention."""
    fake_q = MagicMock()
    fake_q.text.return_value.ask.return_value = None

    with patch.object(prompts, "_is_tty", return_value=True), \
         patch.dict(sys.modules, {"questionary": fake_q}):
        with pytest.raises(SystemExit) as exc:
            prompts.prompt_url_or_die()
    assert exc.value.code == 130


def test_prompt_urls_exits_2_when_non_tty():
    with patch.object(prompts, "_is_tty", return_value=False):
        with pytest.raises(SystemExit) as exc:
            prompts.prompt_urls_or_die()
    assert exc.value.code == 2


def test_prompt_urls_collects_until_empty_line():
    """Multi-line input: empty line ends collection; whitespace is trimmed."""
    inputs = iter(["  url1  ", "url2", "  ", "ignored_after_empty"])

    with patch.object(prompts, "_is_tty", return_value=True), \
         patch("builtins.input", lambda _: next(inputs)):
        out = prompts.prompt_urls_or_die()
    assert out == ["url1", "url2"]


def test_prompt_urls_collects_until_eof():
    """Ctrl+D (EOFError) ends collection cleanly."""
    inputs = iter(["url1", "url2"])

    def fake_input(_):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with patch.object(prompts, "_is_tty", return_value=True), \
         patch("builtins.input", fake_input):
        out = prompts.prompt_urls_or_die()
    assert out == ["url1", "url2"]


def test_prompt_urls_exits_2_when_no_inputs():
    """User hit empty line immediately — no URLs collected → exit 2."""
    with patch.object(prompts, "_is_tty", return_value=True), \
         patch("builtins.input", lambda _: ""):
        with pytest.raises(SystemExit) as exc:
            prompts.prompt_urls_or_die()
    assert exc.value.code == 2
