"""Platform-aware yt-dlp / instaloader error classification.

The anti-block cascade in `utils/anti_block_cascade.py` needs to
distinguish three categories of failures:

1. **Block** — anti-bot defense, rate-limit, IP fingerprint. *Retryable*
   with cookies / proxy / different IP.
2. **Auth required** — login mandatory for this resource (private
   video, members-only, IG profile without session). *Retryable*
   with cookies of an authorized account.
3. **Truly unavailable** — video deleted, geo-blocked permanently,
   private from us specifically. *Not retryable* — escalation
   wouldn't help.

The cascade escalates on (1) and (2), gives up on (3) with a clean
error. This module is the single source of truth for which stderr
signature means what — kept here so we can add new patterns as
YouTube / IG / TT change their error messages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Platform = Literal["youtube", "instagram", "tiktok", "unknown"]
ErrorClass = Literal[
    "anti_bot",          # YouTube "Sign in to confirm you're not a bot"
    "rate_limit",        # IG "Please wait a few minutes", generic 429
    "login_required",    # Private content, profile listing without session
    "video_unavailable", # Deleted / private / region-blocked
    "extractor_broken",  # yt-dlp's extractor for this site broke upstream
    "network",           # Timeout, DNS, generic connection failure
    "unknown",           # Couldn't classify
]


@dataclass(frozen=True)
class ErrorDiagnosis:
    """What kind of error happened and whether retrying with more
    auth/proxy/PO-Token can possibly help."""
    platform: Platform
    error_class: ErrorClass
    retryable_with_cookies: bool
    raw_excerpt: str          # short snippet of stderr for user-facing message

    @property
    def is_block(self) -> bool:
        """Anti-bot / rate-limit blocks — cookies often help."""
        return self.error_class in ("anti_bot", "rate_limit")

    @property
    def needs_auth(self) -> bool:
        """Resource requires a logged-in session, period."""
        return self.error_class == "login_required"


# ---------------------------------------------------------------------------
# URL → platform
# ---------------------------------------------------------------------------

_YT_HOSTS = ("youtube.com", "youtu.be", "music.youtube.com", "m.youtube.com")
_IG_HOSTS = ("instagram.com", "www.instagram.com")
_TT_HOSTS = ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com")


def detect_platform(url: str) -> Platform:
    """Best-effort platform detection from a URL. Returns 'unknown' for
    URLs we don't have a specific cascade for (Vimeo, Twitter, Twitch,
    custom — those still work via yt-dlp's default behavior, just
    without our platform-specific block handling)."""
    if not url:
        return "unknown"
    s = url.lower()
    if any(h in s for h in _YT_HOSTS):
        return "youtube"
    if any(h in s for h in _IG_HOSTS):
        return "instagram"
    if any(h in s for h in _TT_HOSTS):
        return "tiktok"
    return "unknown"


# ---------------------------------------------------------------------------
# stderr → ErrorDiagnosis
# ---------------------------------------------------------------------------

# Patterns ordered by SPECIFICITY (most specific first). The first
# pattern that matches wins. Don't reorder casually — broader
# patterns can over-match if put above narrow ones.

_YOUTUBE_PATTERNS: list[tuple[re.Pattern, ErrorClass, bool]] = [
    # Anti-bot — YouTube's most common rate-defense response. Triggers
    # without cookies on a "hot" IP after 5-10 anonymous fetches.
    (re.compile(r"sign in to confirm you'?re not a bot", re.I), "anti_bot", True),
    (re.compile(r"confirm your age", re.I), "login_required", True),
    # Private / members / age-gated — auth needed (but real)
    (re.compile(r"video is private", re.I), "video_unavailable", False),
    (re.compile(r"members[- ]only", re.I), "login_required", True),
    (re.compile(r"video unavailable", re.I), "video_unavailable", False),
    (re.compile(r"this video has been removed", re.I), "video_unavailable", False),
    (re.compile(r"this video is no longer available", re.I), "video_unavailable", False),
    # Geo block — different from anti-bot, won't help with cookies. The
    # "made.*available in your country" form is what YouTube actually
    # returns ("The uploader has not made this video available in your
    # country") so we match both shapes.
    (re.compile(r"not (?:made )?(?:this video )?available in your country", re.I),
     "video_unavailable", False),
    (re.compile(r"blocked it in your country|geo[- ]restrict", re.I),
     "video_unavailable", False),
    # Generic HTTP — could be anti-bot OR transient. Treat as block, let cascade decide.
    (re.compile(r"http error 403", re.I), "anti_bot", True),
    (re.compile(r"http error 429", re.I), "rate_limit", True),
]

_INSTAGRAM_PATTERNS: list[tuple[re.Pattern, ErrorClass, bool]] = [
    # IG explicitly tells you to wait — rate limit
    (re.compile(r"please wait a few minutes", re.I), "rate_limit", True),
    (re.compile(r"rate[- ]limit", re.I), "rate_limit", True),
    # Login required — IG profiles, stories, anything beyond a public single post
    (re.compile(r"login (?:required|needed)|login.*session|requires.*logged.in", re.I),
     "login_required", True),
    (re.compile(r"this account is private", re.I), "login_required", True),
    # Post deleted
    (re.compile(r"this content (?:is not available|cannot be found)", re.I),
     "video_unavailable", False),
    # Generic
    (re.compile(r"http error 401", re.I), "login_required", True),
    (re.compile(r"http error 403", re.I), "anti_bot", True),
    (re.compile(r"http error 429", re.I), "rate_limit", True),
]

_TIKTOK_PATTERNS: list[tuple[re.Pattern, ErrorClass, bool]] = [
    # TikTok account-level blocks
    (re.compile(r"login required to view", re.I), "login_required", True),
    (re.compile(r"this video is age[- ]restricted", re.I), "login_required", True),
    # Removed / private
    (re.compile(r"video (?:is no longer available|has been removed|is private)", re.I),
     "video_unavailable", False),
    # Generic
    (re.compile(r"http error 403", re.I), "anti_bot", True),
    (re.compile(r"http error 429", re.I), "rate_limit", True),
]

# Cross-platform signals (apply when platform-specific match doesn't fire)
_GENERIC_PATTERNS: list[tuple[re.Pattern, ErrorClass, bool]] = [
    # yt-dlp extractor breakage — upstream issue, needs yt-dlp update,
    # cookies won't help
    (re.compile(r"unable to extract data|marked as broken", re.I),
     "extractor_broken", False),
    # Network — timeout / DNS / connection
    (re.compile(r"(?:timed out|connection (?:reset|refused|aborted)|name (?:or service )?not known)", re.I),
     "network", False),
]


def _shorten_stderr(stderr: str, max_chars: int = 200) -> str:
    """Return the last few lines of stderr, trimmed for display."""
    if not stderr:
        return ""
    tail = "\n".join(stderr.strip().splitlines()[-3:])
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


def diagnose(stderr: str, *, url: str = "", platform: Platform | None = None) -> ErrorDiagnosis:
    """Classify a yt-dlp / instaloader stderr blob.

    Pass either `url` (we detect the platform) or `platform` directly.
    When both are absent, we treat platform as 'unknown' and only the
    generic patterns apply.
    """
    plat: Platform = platform or (detect_platform(url) if url else "unknown")

    # Platform-specific patterns first
    pattern_groups: list[list] = []
    if plat == "youtube":
        pattern_groups.append(_YOUTUBE_PATTERNS)
    elif plat == "instagram":
        pattern_groups.append(_INSTAGRAM_PATTERNS)
    elif plat == "tiktok":
        pattern_groups.append(_TIKTOK_PATTERNS)
    pattern_groups.append(_GENERIC_PATTERNS)

    excerpt = _shorten_stderr(stderr)

    for group in pattern_groups:
        for pat, error_class, retryable in group:
            if pat.search(stderr):
                return ErrorDiagnosis(
                    platform=plat,
                    error_class=error_class,
                    retryable_with_cookies=retryable,
                    raw_excerpt=excerpt,
                )

    return ErrorDiagnosis(
        platform=plat,
        error_class="unknown",
        retryable_with_cookies=False,
        raw_excerpt=excerpt,
    )


# ---------------------------------------------------------------------------
# Platform-specific user-facing fix instructions
# ---------------------------------------------------------------------------

def fix_instruction(diag: ErrorDiagnosis, *, has_cookies: bool) -> str:
    """Return a multi-line message the cascade prints when it can't
    recover automatically. Specific to platform + error class so the
    user gets the *right* one-shot fix, not a generic "register cookies"."""

    if diag.error_class == "video_unavailable":
        return (
            "Video is unavailable (deleted / private / geo-blocked).\n"
            "  This is not a block — retrying with cookies won't help.\n"
            "  Check the URL in a logged-out browser to confirm."
        )

    if diag.error_class == "extractor_broken":
        return (
            "yt-dlp's extractor for this site is broken upstream.\n"
            "  Update yt-dlp: neurolearn update-deps\n"
            "  For Instagram: also `uv sync --extra instagram` (instaloader fallback)."
        )

    if diag.error_class == "network":
        return (
            "Network error (timeout / DNS / connection).\n"
            "  Check your internet connection and retry."
        )

    # The interesting case: block / rate-limit / auth-required — these are
    # all in the same "cookies might help" family, just with different
    # specifics per platform.
    plat = diag.platform

    if plat == "youtube":
        from skills.neurolearn.utils.po_token import DOCKER_RUN_CMD
        if not has_cookies:
            return (
                "YouTube blocked the request (anti-bot / rate limit).\n"
                "  Two-minute fix:\n"
                "    1. Open youtube.com in your browser (logged in).\n"
                "    2. Install 'Get cookies.txt LOCALLY' extension; click → Export.\n"
                "    3. neurolearn config set-cookies --from-file <path-to-cookies.txt>\n"
                "  For fewer blocks, also start the PO Token provider (one-time):\n"
                f"    {DOCKER_RUN_CMD}\n"
                "    (or `npx --yes bgutil-ytdlp-pot-provider` with Node >= 20)\n"
                "  Verify: neurolearn doctor --json → anti_block.po_token_can_generate."
            )
        # Had cookies, still blocked
        return (
            "YouTube blocked the request even with cookies registered.\n"
            "  Possible causes (in order of likelihood):\n"
            "    1. Cookies expired — re-export from your browser, re-register.\n"
            "    2. PO Token provider not running — start it (mints anti-bot tokens):\n"
            f"       {DOCKER_RUN_CMD}\n"
            "    3. Your IP is in a YouTube-flagged range (datacenter, VPN exit).\n"
            "       Solution: residential proxy. See "
            "docs/research/youtube-ip-block-bypass-2026.md."
        )

    if plat == "instagram":
        if not has_cookies:
            return (
                "Instagram requires a logged-in session for this resource.\n"
                "  Two-minute fix:\n"
                "    1. Open instagram.com in your browser (logged in).\n"
                "    2. Install 'Get cookies.txt LOCALLY' extension; click → Export.\n"
                "    3. neurolearn subscribes cookies set instagram --from-file <path>\n"
                "  For heavy IG research: also `uv sync --extra instagram` (instaloader fallback)."
            )
        return (
            "Instagram blocked the request even with cookies registered.\n"
            "  Possible causes:\n"
            "    1. Session expired — re-export cookies from your browser.\n"
            "    2. IG flagged the account for scraping. Wait 1-24h, then retry.\n"
            "    3. Try `uv sync --extra instagram` (uses instaloader instead)."
        )

    if plat == "tiktok":
        if not has_cookies:
            return (
                "TikTok blocked the request or this resource requires login.\n"
                "  Two-minute fix:\n"
                "    1. Open tiktok.com in your browser (logged in).\n"
                "    2. Install 'Get cookies.txt LOCALLY' extension; click → Export.\n"
                "    3. neurolearn subscribes cookies set tiktok --from-file <path>"
            )
        return (
            "TikTok blocked the request even with cookies registered.\n"
            "  Re-export your cookies, or try from a different IP\n"
            "  (residential proxy — see docs/UNLIMITED_RESEARCH.md)."
        )

    # Unknown platform — generic fallback
    return (
        "Download blocked. The host returned an anti-bot / rate-limit response.\n"
        "  If this is a supported platform (YouTube / Instagram / TikTok),\n"
        "  registering cookies will likely fix it. See docs/cookies-walkthrough.md."
    )
