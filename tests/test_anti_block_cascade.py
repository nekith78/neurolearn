"""Unit tests for utils.anti_block_cascade — plan + runner."""
from __future__ import annotations

import pytest

from skills.neurolearn.config import Config
from skills.neurolearn.utils.anti_block_cascade import (
    DownloadAttempt,
    PlatformBlockError,
    PlatformPermanentError,
    plan_attempts,
    run_cascade,
)


# ---------------------------------------------------------------------------
# plan_attempts — YouTube
# ---------------------------------------------------------------------------

def test_plan_youtube_no_cookies_yields_anonymous_only():
    cfg = Config(youtube_cookies_file="", cookies_file="")
    plan = plan_attempts("https://youtu.be/abc", cfg)
    assert len(plan) == 1
    assert plan[0].label == "anonymous"
    assert plan[0].cookies_file == ""


def test_plan_youtube_with_cookies_light_volume_escalates():
    """Light user: try anonymous first to preserve cookie lifetime,
    fall back to cookies if blocked."""
    cfg = Config(youtube_cookies_file="/path/yt.txt", youtube_research_volume="light")
    plan = plan_attempts("https://youtu.be/abc", cfg)
    assert len(plan) == 2
    assert plan[0].cookies_file == ""           # anonymous
    assert plan[1].cookies_file == "/path/yt.txt"


def test_plan_youtube_with_cookies_heavy_volume_starts_with_cookies():
    """Heavy user with cookies: skip the doomed anonymous attempt."""
    cfg = Config(youtube_cookies_file="/path/yt.txt", youtube_research_volume="heavy")
    plan = plan_attempts("https://youtu.be/abc", cfg)
    assert len(plan) == 1
    assert plan[0].cookies_file == "/path/yt.txt"


def test_plan_youtube_empty_volume_treated_as_light():
    """Pre-v0.15 configs have empty volume strings → cascade is
    backwards-compatible (anonymous first, cookies fallback)."""
    cfg = Config(youtube_cookies_file="/path/yt.txt", youtube_research_volume="")
    plan = plan_attempts("https://youtu.be/abc", cfg)
    assert len(plan) == 2


def test_plan_youtube_falls_back_to_legacy_cookies_field():
    """Pre-v0.10.7 configs used `cookies_file`, post used `youtube_cookies_file`.
    Both should work."""
    cfg = Config(cookies_file="/old.txt", youtube_cookies_file="")
    plan = plan_attempts("https://youtu.be/abc", cfg)
    assert any(a.cookies_file == "/old.txt" for a in plan)


# ---------------------------------------------------------------------------
# plan_attempts — Instagram + TikTok
# ---------------------------------------------------------------------------

def test_plan_instagram_no_cookies_yields_anonymous_to_surface_error():
    """Even though IG anonymous usually fails, we still ATTEMPT it once
    so the cascade can surface the IG-specific 'register cookies' message."""
    cfg = Config(instagram_cookies_file="")
    plan = plan_attempts("https://instagram.com/natgeo/", cfg)
    assert len(plan) == 1
    assert plan[0].cookies_file == ""


def test_plan_instagram_with_cookies():
    cfg = Config(instagram_cookies_file="/ig.txt", instagram_research_volume="heavy")
    plan = plan_attempts("https://instagram.com/natgeo/", cfg)
    assert plan[0].cookies_file == "/ig.txt"


def test_plan_tiktok_no_cookies():
    cfg = Config(tiktok_cookies_file="")
    plan = plan_attempts("https://tiktok.com/@user", cfg)
    assert len(plan) == 1


def test_plan_unknown_platform_falls_back_to_anonymous():
    cfg = Config()
    plan = plan_attempts("https://vimeo.com/12345", cfg)
    assert len(plan) == 1
    assert plan[0].cookies_file == ""


# ---------------------------------------------------------------------------
# run_cascade — orchestration
# ---------------------------------------------------------------------------

class _FakeDownloadError(Exception):
    """Test double — exception carrying a `.stderr` attribute the
    cascade inspects."""
    def __init__(self, stderr: str):
        super().__init__(stderr)
        self.stderr = stderr


def test_cascade_returns_first_success():
    cfg = Config(youtube_cookies_file="/yt.txt", youtube_research_volume="light")
    calls: list[str] = []

    def do_attempt(attempt):
        calls.append(attempt.cookies_file)
        return "downloaded_file_path"

    result = run_cascade(
        url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt,
    )
    assert result == "downloaded_file_path"
    assert calls == [""]   # only first attempt called; cookies attempt never reached


def test_cascade_escalates_to_cookies_after_anti_bot_block():
    """User's actual painful flow: anonymous fails with anti-bot →
    cascade silently retries with cookies → success."""
    cfg = Config(youtube_cookies_file="/yt.txt", youtube_research_volume="light")
    calls: list[str] = []

    def do_attempt(attempt):
        calls.append(attempt.cookies_file)
        if attempt.cookies_file == "":
            raise _FakeDownloadError("Sign in to confirm you're not a bot")
        return "success_with_cookies"

    result = run_cascade(
        url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt,
    )
    assert result == "success_with_cookies"
    assert calls == ["", "/yt.txt"]


def test_cascade_raises_block_error_when_no_cookies_to_escalate_to():
    """No cookies registered → first anonymous attempt blocks → no
    escalation possible → PlatformBlockError with fix instruction."""
    cfg = Config(youtube_cookies_file="", cookies_file="")

    def do_attempt(attempt):
        raise _FakeDownloadError("Sign in to confirm you're not a bot")

    with pytest.raises(PlatformBlockError) as exc_info:
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)

    err = exc_info.value
    assert err.diagnosis.platform == "youtube"
    assert err.diagnosis.error_class == "anti_bot"
    assert err.exit_code == 8
    # The user-facing message must include the fix command
    assert "set-cookies --from-file" in str(err)


def test_cascade_raises_block_error_when_cookies_also_fail():
    """Both anonymous AND cookies fail with anti-bot → escalation
    exhausted → PlatformBlockError with the 'cookies expired or
    need proxy' message."""
    cfg = Config(youtube_cookies_file="/yt.txt", youtube_research_volume="light")

    def do_attempt(attempt):
        raise _FakeDownloadError("HTTP Error 403: Forbidden")

    with pytest.raises(PlatformBlockError) as exc_info:
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)

    # Since we DID have cookies, the message should point to next layer
    # (Node/PO Token / proxy), not "go register cookies"
    msg = str(exc_info.value)
    assert "set-cookies --from-file" not in msg, "shouldn't suggest re-registering"
    assert any(w in msg.lower() for w in ("node", "po token", "proxy", "expired"))


def test_cascade_raises_permanent_error_for_deleted_video():
    """Deleted video → no escalation, distinct exception type so
    callers can handle it differently (e.g. continue with next URL
    in a batch instead of stopping cold)."""
    cfg = Config(youtube_cookies_file="/yt.txt", youtube_research_volume="light")
    calls: list[str] = []

    def do_attempt(attempt):
        calls.append(attempt.cookies_file)
        raise _FakeDownloadError("This video has been removed by the uploader")

    with pytest.raises(PlatformPermanentError) as exc_info:
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)

    # Only ONE attempt should have happened — no point retrying a deletion
    assert len(calls) == 1
    assert exc_info.value.diagnosis.error_class == "video_unavailable"


def test_cascade_raises_permanent_error_for_geo_block():
    cfg = Config()

    def do_attempt(attempt):
        raise _FakeDownloadError("The uploader has not made this video available in your country")

    with pytest.raises(PlatformPermanentError):
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)


def test_cascade_raises_permanent_error_for_network_failure():
    """Network errors → not retried (no cookies could help), but
    distinct from blocks — caller may want to retry with backoff."""
    cfg = Config(youtube_cookies_file="/yt.txt")

    def do_attempt(attempt):
        raise _FakeDownloadError("socket connection timed out")

    with pytest.raises(PlatformPermanentError) as exc_info:
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)
    assert exc_info.value.diagnosis.error_class == "network"


def test_cascade_works_with_instagram_url():
    """Sanity check: detector + plan + runner integrate cleanly for IG."""
    cfg = Config(instagram_cookies_file="/ig.txt", instagram_research_volume="heavy")

    def do_attempt(attempt):
        assert attempt.cookies_file == "/ig.txt"   # heavy → starts with cookies
        return "ig_post.mp4"

    result = run_cascade(
        url="https://instagram.com/p/ABC/", cfg=cfg, do_attempt=do_attempt,
    )
    assert result == "ig_post.mp4"


def test_cascade_block_error_has_exit_code_8():
    """The new exit code 8 is the contract for 'anti-bot block'.
    Caller scripts (transcribe, batch, research) translate it to
    sys.exit(8) so Claude in chat can distinguish a fixable block
    from a generic transcribe failure."""
    cfg = Config()

    def do_attempt(attempt):
        raise _FakeDownloadError("HTTP Error 403")

    with pytest.raises(PlatformBlockError) as exc_info:
        run_cascade(url="https://youtu.be/abc", cfg=cfg, do_attempt=do_attempt)
    assert exc_info.value.exit_code == 8
