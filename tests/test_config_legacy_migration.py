"""Tests for v0.9 legacy config-directory migration.

When the project was renamed from `youtube-transcribe` to `neurolearn`,
the config directory moved from `~/.youtube-transcribe/` to
`~/.neurolearn/`. On first run after upgrade, the migration helper
in `config.py` renames the directory once so the user keeps their
API keys, cookies, subscribes.toml, history.toml, and triggers.toml
without manual intervention.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_migrates_legacy_dir_when_new_missing(tmp_path: Path):
    """Pre-v0.9 dir exists, new dir doesn't → mv happens, contents preserved."""
    legacy = tmp_path / ".youtube-transcribe"
    new = tmp_path / ".neurolearn"
    legacy.mkdir()
    (legacy / "config.toml").write_text('default_backend = "gemini"\n')
    (legacy / ".env").write_text("GEMINI_API_KEY=test\n")

    with patch("skills.neurolearn.config._LEGACY_CONFIG_DIR", legacy), \
         patch("skills.neurolearn.config.CONFIG_DIR", new):
        from skills.neurolearn.config import _maybe_migrate_legacy_config_dir
        _maybe_migrate_legacy_config_dir()

    assert not legacy.exists(), "legacy dir should be gone after mv"
    assert new.exists(), "new dir should now exist"
    assert (new / "config.toml").read_text() == 'default_backend = "gemini"\n'
    assert (new / ".env").read_text() == "GEMINI_API_KEY=test\n"


def test_no_op_when_new_dir_already_exists(tmp_path: Path):
    """If `.neurolearn/` already exists (user installed fresh), leave both alone."""
    legacy = tmp_path / ".youtube-transcribe"
    new = tmp_path / ".neurolearn"
    legacy.mkdir()
    (legacy / "config.toml").write_text("legacy=1\n")
    new.mkdir()
    (new / "config.toml").write_text("new=1\n")

    with patch("skills.neurolearn.config._LEGACY_CONFIG_DIR", legacy), \
         patch("skills.neurolearn.config.CONFIG_DIR", new):
        from skills.neurolearn.config import _maybe_migrate_legacy_config_dir
        _maybe_migrate_legacy_config_dir()

    # Both directories untouched.
    assert legacy.exists()
    assert new.exists()
    assert (new / "config.toml").read_text() == "new=1\n"


def test_no_op_when_legacy_dir_absent(tmp_path: Path):
    """Fresh install — neither dir exists yet → no-op, no error."""
    legacy = tmp_path / ".youtube-transcribe"
    new = tmp_path / ".neurolearn"
    # Neither directory created.

    with patch("skills.neurolearn.config._LEGACY_CONFIG_DIR", legacy), \
         patch("skills.neurolearn.config.CONFIG_DIR", new):
        from skills.neurolearn.config import _maybe_migrate_legacy_config_dir
        _maybe_migrate_legacy_config_dir()

    assert not legacy.exists()
    assert not new.exists()


def test_oserror_does_not_crash(tmp_path: Path, capsys):
    """A failing rename (cross-device, permission, etc.) prints a warning
    but does not raise — startup must continue."""
    legacy = tmp_path / ".youtube-transcribe"
    new = tmp_path / ".neurolearn"
    legacy.mkdir()

    fake_rename = lambda *_a, **_k: (_ for _ in ()).throw(  # noqa: E731
        OSError("simulated cross-device link")
    )

    with patch("skills.neurolearn.config._LEGACY_CONFIG_DIR", legacy), \
         patch("skills.neurolearn.config.CONFIG_DIR", new), \
         patch.object(Path, "rename", fake_rename):
        from skills.neurolearn.config import _maybe_migrate_legacy_config_dir
        _maybe_migrate_legacy_config_dir()  # must not raise

    err = capsys.readouterr().err
    assert "Could not migrate" in err
