"""Test-wide conftest.

Primes macOS dyld search path so test code that imports `weasyprint`
directly (rather than via the report package) can still find
Homebrew-installed pango/cairo/gobject. The report package does the
same priming on import, but standalone test imports go through
pytest.importorskip and don't touch the package.
"""
from __future__ import annotations

import pytest

from skills.neurolearn.report._macos import prime_native_libs_for_weasyprint


prime_native_libs_for_weasyprint()


@pytest.fixture(autouse=True)
def _skip_onboarding_gate(monkeypatch):
    """v0.13.0: tests don't go through the wizard, so the
    `onboarding_complete` gate would block every transcribe/batch test.
    Patch the gate function to no-op for all tests. Tests that
    specifically verify the gate logic re-patch it back via their own
    fixtures (see test_onboarding_gate.py)."""
    monkeypatch.setenv("NEUROLEARN_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("NEUROLEARN_YOUTUBE_PROXY", "")
    monkeypatch.setattr(
        "skills.neurolearn.transcribe._require_onboarding_complete",
        lambda *args, **kwargs: None,
    )


@pytest.fixture(autouse=True)
def _isolate_youtube_quota(monkeypatch, tmp_path):
    """Fake API requests must never consume the user's local quota."""
    monkeypatch.setattr("skills.neurolearn.config.CONFIG_PATH", tmp_path / "config.toml")


@pytest.fixture(autouse=True)
def _isolate_youtube_credentials(monkeypatch, tmp_path):
    """Automatic statistics lookup must never use a developer's key in unit tests."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")
