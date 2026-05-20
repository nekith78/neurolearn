"""v0.10.9 Fix F+G: `batch` accepts `--no-analyze` and `--yes` for
symmetry with `research`.

Users who copy-paste a research command and swap `research` → `batch`
shouldn't be greeted with "No such option" errors. Both flags are
informational on `batch`:

  * `batch` doesn't run analyze by default — `--then-analyze` is opt-in.
    `--no-analyze` is a no-op (the negative state is the default).
  * `batch` has no TTY checkpoint to skip. `--yes` is a no-op.

These tests just prove Click accepts the flags. Semantic behavior is
unchanged.
"""
from __future__ import annotations

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def test_batch_help_does_not_advertise_compat_flags():
    """The hidden=True keeps the flags out of --help so we don't
    teach users to depend on them — the canonical CLI surface is
    --then-analyze (opt-in for analyze)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--help"])
    assert result.exit_code == 0
    # Symmetry flags exist but stay hidden.
    assert "--no-analyze" not in result.output
    assert "--yes" not in result.output
    # The intended way is still surfaced.
    assert "--then-analyze" in result.output


def test_batch_accepts_no_analyze_flag_without_error():
    """The flag parses cleanly — Click doesn't reject it."""
    runner = CliRunner()
    # No inputs → exit 2 with a usage hint, NOT the "no such option" error.
    result = runner.invoke(cli, ["batch", "--no-analyze"])
    # We don't care about exit code here — only that the parser accepted
    # the flag (i.e. the error, if any, is not about an unknown option).
    assert "No such option" not in result.output
    assert "--no-analyze" not in result.output or "unknown" not in result.output.lower()


def test_batch_accepts_yes_flag_without_error():
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--yes"])
    assert "No such option" not in result.output


def test_batch_accepts_both_flags_together():
    """Composed usage — both flags on the same invocation."""
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--no-analyze", "--yes"])
    assert "No such option" not in result.output
