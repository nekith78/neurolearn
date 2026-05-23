"""Unit tests for utils.platform_errors — block-vs-unavailable detector."""
from __future__ import annotations

from skills.neurolearn.utils.platform_errors import (
    detect_platform,
    diagnose,
    fix_instruction,
)


# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------

def test_detect_youtube_url_forms():
    assert detect_platform("https://youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://youtu.be/abc") == "youtube"
    assert detect_platform("https://m.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://music.youtube.com/watch?v=abc") == "youtube"


def test_detect_instagram_url_forms():
    assert detect_platform("https://instagram.com/natgeo/") == "instagram"
    assert detect_platform("https://www.instagram.com/p/ABC/") == "instagram"


def test_detect_tiktok_url_forms():
    assert detect_platform("https://tiktok.com/@user/video/123") == "tiktok"
    assert detect_platform("https://www.tiktok.com/@user") == "tiktok"
    assert detect_platform("https://vm.tiktok.com/xxx") == "tiktok"
    assert detect_platform("https://vt.tiktok.com/xxx") == "tiktok"


def test_detect_unknown_platform():
    assert detect_platform("https://vimeo.com/12345") == "unknown"
    assert detect_platform("https://twitter.com/user/status/123") == "unknown"
    assert detect_platform("") == "unknown"
    assert detect_platform("not a url") == "unknown"


def test_detect_case_insensitive():
    assert detect_platform("https://YouTube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://INSTAGRAM.COM/user") == "instagram"


# ---------------------------------------------------------------------------
# YouTube classification
# ---------------------------------------------------------------------------

def test_youtube_anti_bot_classified_as_anti_bot():
    """The user's reported pain: 'Sign in to confirm you're not a bot'."""
    stderr = """ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot.
Use --cookies-from-browser or --cookies for the authentication.
"""
    d = diagnose(stderr, platform="youtube")
    assert d.platform == "youtube"
    assert d.error_class == "anti_bot"
    assert d.retryable_with_cookies is True
    assert d.is_block is True


def test_youtube_429_classified_as_rate_limit():
    stderr = "ERROR: unable to download webpage: HTTP Error 429: Too Many Requests"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "rate_limit"
    assert d.is_block is True


def test_youtube_403_classified_as_anti_bot():
    """403 from YouTube is almost always anti-bot, not a permanent ban."""
    stderr = "ERROR: HTTP Error 403: Forbidden"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "anti_bot"
    assert d.retryable_with_cookies is True


def test_youtube_private_video_is_not_retryable():
    stderr = "ERROR: [youtube] abc: Video is private. Sign in if you've been granted access to this video."
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "video_unavailable"
    assert d.retryable_with_cookies is False
    assert d.is_block is False


def test_youtube_video_removed_not_retryable():
    stderr = "ERROR: [youtube] abc: This video has been removed by the uploader"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "video_unavailable"
    assert d.retryable_with_cookies is False


def test_youtube_geo_block_not_retryable_with_cookies():
    """A geo block from YouTube needs proxy/VPN, not cookies."""
    stderr = "ERROR: The uploader has not made this video available in your country"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "video_unavailable"
    assert d.retryable_with_cookies is False


# ---------------------------------------------------------------------------
# Instagram classification
# ---------------------------------------------------------------------------

def test_instagram_rate_limit():
    stderr = "ERROR: Instagram says 'Please wait a few minutes before you try again'"
    d = diagnose(stderr, platform="instagram")
    assert d.platform == "instagram"
    assert d.error_class == "rate_limit"
    assert d.retryable_with_cookies is True


def test_instagram_login_required():
    stderr = "ERROR: [instagram] login required to access this resource"
    d = diagnose(stderr, platform="instagram")
    assert d.error_class == "login_required"
    assert d.retryable_with_cookies is True


def test_instagram_401_classified_as_login_required():
    stderr = "ERROR: HTTP Error 401: Unauthorized"
    d = diagnose(stderr, platform="instagram")
    assert d.error_class == "login_required"


def test_instagram_private_account():
    stderr = "ERROR: This account is private"
    d = diagnose(stderr, platform="instagram")
    assert d.error_class == "login_required"
    assert d.retryable_with_cookies is True


# ---------------------------------------------------------------------------
# TikTok classification
# ---------------------------------------------------------------------------

def test_tiktok_403():
    stderr = "ERROR: HTTP Error 403: Forbidden"
    d = diagnose(stderr, platform="tiktok")
    assert d.platform == "tiktok"
    assert d.error_class == "anti_bot"
    assert d.retryable_with_cookies is True


def test_tiktok_age_restricted_needs_login():
    stderr = "ERROR: This video is age-restricted and requires login"
    d = diagnose(stderr, platform="tiktok")
    assert d.error_class == "login_required"


# ---------------------------------------------------------------------------
# Cross-platform / generic patterns
# ---------------------------------------------------------------------------

def test_extractor_broken_classified_correctly_across_platforms():
    stderr = "ERROR: unable to extract data; please report this issue"
    for platform in ("youtube", "instagram", "tiktok", "unknown"):
        d = diagnose(stderr, platform=platform)
        assert d.error_class == "extractor_broken", f"failed on {platform}"
        assert d.retryable_with_cookies is False


def test_network_timeout_classified_correctly():
    stderr = "ERROR: socket connection timed out"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "network"
    assert d.retryable_with_cookies is False


def test_unknown_error_does_not_raise():
    """The detector must NEVER raise — it always returns a diagnosis,
    even for stderr it can't classify."""
    d = diagnose("some unrecognised gibberish", platform="youtube")
    assert d.error_class == "unknown"
    assert d.retryable_with_cookies is False


def test_diagnose_accepts_url_instead_of_platform():
    """Convenience form: pass URL, detector figures out platform."""
    stderr = "ERROR: Sign in to confirm you're not a bot"
    d = diagnose(stderr, url="https://youtu.be/abc")
    assert d.platform == "youtube"
    assert d.error_class == "anti_bot"


def test_diagnose_excerpt_truncated_to_recent_lines():
    """Long stderr shouldn't bloat downstream error messages."""
    stderr = "\n".join(f"line {i}" for i in range(50))
    stderr += "\nFINAL: HTTP Error 403"
    d = diagnose(stderr, platform="youtube")
    assert d.error_class == "anti_bot"
    assert "FINAL" in d.raw_excerpt
    assert "line 0" not in d.raw_excerpt
    assert len(d.raw_excerpt) <= 200


# ---------------------------------------------------------------------------
# fix_instruction — user-facing messages
# ---------------------------------------------------------------------------

def test_fix_instruction_youtube_no_cookies_mentions_set_cookies_command():
    d = diagnose("Sign in to confirm you're not a bot", platform="youtube")
    msg = fix_instruction(d, has_cookies=False)
    assert "set-cookies" in msg
    assert "--from-file" in msg, "must reference the secure --from-file form"
    assert "youtube.com" in msg.lower() or "your browser" in msg


def test_fix_instruction_youtube_with_cookies_suggests_node_or_proxy():
    """If cookies exist and we still got blocked, the fix instruction
    must point at the next layer (Node/PO Token or proxy), NOT just
    repeat 'register cookies'."""
    d = diagnose("Sign in to confirm you're not a bot", platform="youtube")
    msg = fix_instruction(d, has_cookies=True)
    assert "node" in msg.lower() or "po token" in msg.lower() or "proxy" in msg.lower()
    assert "set-cookies --from-file" not in msg, (
        "should not tell the user to re-register cookies they already have"
    )


def test_fix_instruction_instagram_no_cookies():
    d = diagnose("login required", platform="instagram")
    msg = fix_instruction(d, has_cookies=False)
    assert "instagram" in msg.lower()
    assert "subscribes cookies set instagram" in msg
    assert "--from-file" in msg


def test_fix_instruction_tiktok_no_cookies():
    d = diagnose("HTTP Error 403", platform="tiktok")
    msg = fix_instruction(d, has_cookies=False)
    assert "tiktok" in msg.lower()
    assert "subscribes cookies set tiktok" in msg


def test_fix_instruction_video_unavailable_doesnt_suggest_cookies():
    """If the video is truly gone, suggesting cookies wastes the user's
    time. The message may *mention* cookies in a "won't help" clarifier
    — that's actually useful context — but it MUST NOT suggest running
    a `set-cookies` command."""
    d = diagnose("This video has been removed by the uploader", platform="youtube")
    msg = fix_instruction(d, has_cookies=False)
    assert "set-cookies" not in msg
    assert "unavailable" in msg.lower() or "deleted" in msg.lower()


def test_fix_instruction_extractor_broken_suggests_update_deps():
    d = diagnose("unable to extract data", platform="youtube")
    msg = fix_instruction(d, has_cookies=False)
    assert "update-deps" in msg or "yt-dlp" in msg.lower()


def test_fix_instruction_network_doesnt_suggest_cookies():
    d = diagnose("socket connection timed out", platform="youtube")
    msg = fix_instruction(d, has_cookies=False)
    assert "cookies" not in msg.lower()
    assert "network" in msg.lower() or "connection" in msg.lower() or "timeout" in msg.lower()
