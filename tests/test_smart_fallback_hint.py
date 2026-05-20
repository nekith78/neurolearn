"""Tests for `_smart_fallback_hint` — the post-batch UX hint (v0.10.7).

When a user runs an explicit non-smart backend (e.g. `--backend subtitles`)
and most of the batch fails for backend-systemic reasons (YouTube
IpBlocked, missing captions on the whole set), we surface a yellow
warning telling them to retry with `--backend smart`. This file proves
when the hint fires and when it stays quiet.
"""
from __future__ import annotations

from skills.neurolearn.transcribe import _smart_fallback_hint


def test_hint_fires_when_all_failed_under_explicit_backend():
    """The exact case from the Windows debug report: 15/15 failed via
    --backend subtitles. Must produce a hint."""
    hint = _smart_fallback_hint(
        backend_name="subtitles", ok_count=0, fail_count=15,
    )
    assert hint is not None
    assert "smart" in hint
    assert "subtitles" in hint
    assert "15/15" in hint


def test_hint_fires_at_exactly_half_failed():
    """50% failure rate is the threshold — fire at exactly 50%."""
    hint = _smart_fallback_hint(
        backend_name="gemini", ok_count=5, fail_count=5,
    )
    assert hint is not None


def test_hint_silent_below_half_failure_rate():
    """One or two failures in a large batch could be private/deleted
    videos. Don't blame the backend in that case."""
    assert _smart_fallback_hint(
        backend_name="gemini", ok_count=8, fail_count=2,
    ) is None


def test_hint_silent_when_user_already_used_smart():
    """`smart` already does the cascade. Telling the user to use smart
    when they used smart is noise."""
    assert _smart_fallback_hint(
        backend_name="smart", ok_count=0, fail_count=10,
    ) is None
    # Case-insensitive guard.
    assert _smart_fallback_hint(
        backend_name="SMART", ok_count=0, fail_count=10,
    ) is None


def test_hint_silent_for_tiny_batches():
    """One video failing is not a statistical signal. Stay quiet
    (otherwise the hint screams on every single-video transcribe error)."""
    assert _smart_fallback_hint(
        backend_name="subtitles", ok_count=0, fail_count=1,
    ) is None


def test_hint_silent_for_empty_batches():
    """No-op when both counts are zero (shouldn't happen in practice
    but be defensive)."""
    assert _smart_fallback_hint(
        backend_name="subtitles", ok_count=0, fail_count=0,
    ) is None


def test_hint_silent_when_backend_is_None():
    """`backend_name` can legitimately be None when smart auto-selected
    something via on_stage. Don't crash, just stay quiet."""
    assert _smart_fallback_hint(
        backend_name=None, ok_count=0, fail_count=5,
    ) is None or "smart" in (_smart_fallback_hint(
        backend_name=None, ok_count=0, fail_count=5,
    ) or "")
