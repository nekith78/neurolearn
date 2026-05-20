"""Tests for `_diagnose_failure_hint` — the error-to-hint mapper used
by both `manifest.json[].hint` and `errors.log` (v0.10.7).

Each branch must produce an actionable hint that names the next command
the user should run."""
from __future__ import annotations

from skills.neurolearn.transcribe import _diagnose_failure_hint


def test_ipblocked_subtitles_hints_cookies_and_smart_fallback():
    """The IpBlocked error from SubtitlesBackend is the actual case from
    the Windows debug-run report. Hint must point at both fixes."""
    hint = _diagnose_failure_hint(
        "backend",
        "Subtitles unavailable for this video (IpBlocked). Try another backend.",
    )
    assert hint is not None
    assert "youtube" in hint.lower()
    assert "smart" in hint.lower()
    assert "cookies" in hint.lower()


def test_subtitles_unavailable_no_ipblock_hints_smart():
    """Plain 'subtitles unavailable' (no IpBlocked) gets a different,
    shorter hint — just suggest smart fallback."""
    hint = _diagnose_failure_hint(
        "backend",
        "Subtitles unavailable for this video (TranscriptsDisabled).",
    )
    assert hint is not None
    assert "smart" in hint.lower()
    # Should NOT recommend cookies for plain missing captions.
    assert "cookies" not in hint.lower()


def test_gemini_429_quota_hints_smart_or_wait():
    """Gemini RESOURCE_EXHAUSTED — common after a heavy day. Hint should
    name `--backend smart` for auto-fallback or the daily reset."""
    hint = _diagnose_failure_hint(
        "backend",
        "Gemini API error (YouTube URL): 429 RESOURCE_EXHAUSTED. quota...",
    )
    assert hint is not None
    assert "smart" in hint.lower() or "wait" in hint.lower() or "reset" in hint.lower()


def test_download_403_still_hints_cookies():
    """Pre-existing 403/bot/sign-in branch unchanged."""
    hint = _diagnose_failure_hint(
        "download",
        "ERROR: 403 Forbidden: bot detection sign in to confirm",
    )
    assert hint is not None
    assert "cookies" in hint.lower()


def test_missing_api_key_still_hints_set_key():
    """Pre-existing api_key branch unchanged."""
    hint = _diagnose_failure_hint(
        "backend",
        "BackendNotConfigured: API_KEY missing for groq",
    )
    assert hint is not None
    assert "set-key" in hint


def test_unrelated_error_returns_none():
    """No false positives: random errors get no hint, not a wrong one."""
    assert _diagnose_failure_hint("backend", "something_else: weird") is None
    assert _diagnose_failure_hint("download", "disk full") is None
