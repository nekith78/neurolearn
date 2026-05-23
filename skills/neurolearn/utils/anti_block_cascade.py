"""Platform-aware anti-block download cascade.

Strategy: try the strongest attempt available based on what's
configured + what the user said they'd do during onboarding. If the
first attempt is blocked, escalate to whatever next step adds new
information (cookies we haven't used yet). PO Token plugin is OUT
of the cascade — it auto-attaches to every yt-dlp call when the
plugin is installed, so there's no "with PO Token vs without" choice
to make at runtime.

Public API
----------

  plan_attempts(url, cfg) -> list[DownloadAttempt]
      Compute the ordered sequence of attempts for this URL + config.
      Most cases produce 1 attempt; mixed cases (have cookies but
      asked for "light" volume) produce 2.

  PlatformBlockError(diagnosis, attempt_label) extends BackendError
      Raised when no attempt succeeded AND the failure was a
      block-class error. Carries the user-facing fix_instruction so
      callers can surface it directly.

  PlatformPermanentError(diagnosis) extends BackendError
      Raised when the failure is "video deleted / geo-blocked
      permanently / extractor broken" — retrying with more auth
      won't help. Caller should NOT escalate further.
"""
from __future__ import annotations

from dataclasses import dataclass

from skills.neurolearn.config import Config
from skills.neurolearn.utils.platform_errors import (
    ErrorDiagnosis,
    Platform,
    detect_platform,
    diagnose,
    fix_instruction,
)


@dataclass(frozen=True)
class DownloadAttempt:
    """One attempt's parameters. The runner uses `cookies_file` to
    configure yt-dlp; `label` is just for logging/error messages."""
    label: str
    cookies_file: str   # empty = no cookies (anonymous)


class PlatformBlockError(Exception):
    """The platform blocked us; cookies (or proxy) might fix it.
    Carries the user-facing instruction for the caller to print."""

    def __init__(self, diagnosis: ErrorDiagnosis, message: str, *, exit_code: int = 8):
        super().__init__(message)
        self.diagnosis = diagnosis
        self.exit_code = exit_code


class PlatformPermanentError(Exception):
    """The resource is genuinely gone / forbidden / broken; no retry
    would help. Distinct exception so callers don't loop on it."""

    def __init__(self, diagnosis: ErrorDiagnosis, message: str):
        super().__init__(message)
        self.diagnosis = diagnosis


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def _cookies_for_platform(cfg: Config, platform: Platform) -> str:
    """Return the registered cookies path for a platform (empty if
    not set). YouTube has two slots historically — prefer the newer
    `youtube_cookies_file` and fall back to the legacy `cookies_file`."""
    if platform == "youtube":
        return cfg.youtube_cookies_file or cfg.cookies_file or ""
    if platform == "instagram":
        return cfg.instagram_cookies_file or ""
    if platform == "tiktok":
        return cfg.tiktok_cookies_file or ""
    return ""


def _volume_for_platform(cfg: Config, platform: Platform) -> str:
    """Return the per-platform research-volume preference. Empty
    string ('not yet asked') is treated as 'light'."""
    if platform == "youtube":
        v = cfg.youtube_research_volume
    elif platform == "instagram":
        v = cfg.instagram_research_volume
    elif platform == "tiktok":
        v = cfg.tiktok_research_volume
    else:
        v = ""
    return v or "light"


def plan_attempts(url: str, cfg: Config) -> list[DownloadAttempt]:
    """Return the ordered list of attempts to try for this URL.

    Logic:
      - If volume is "heavy" AND cookies registered → ONE attempt
        starting with cookies. Anonymous would burn time on a
        guaranteed block for high-volume users.
      - If volume is "light" AND cookies registered → TWO attempts:
        anonymous first (preserves cookie session lifetime), then
        cookies as fallback if anonymous gets blocked.
      - If no cookies registered → ONE anonymous attempt. The
        downloader will surface the fix instruction on failure.
      - For platforms where anonymous never works (Instagram
        profile listings), we still try anonymous if no cookies are
        registered so the user sees the specific "register IG
        cookies" message, not a generic yt-dlp error.
    """
    platform: Platform = detect_platform(url)
    cookies = _cookies_for_platform(cfg, platform)
    volume = _volume_for_platform(cfg, platform)

    attempts: list[DownloadAttempt] = []

    if cookies:
        if volume == "heavy":
            # Heavy user with cookies: skip anonymous entirely
            attempts.append(DownloadAttempt(
                label=f"with {platform} cookies",
                cookies_file=cookies,
            ))
        else:
            # Light user with cookies: try anonymous first, escalate
            attempts.append(DownloadAttempt(label="anonymous", cookies_file=""))
            attempts.append(DownloadAttempt(
                label=f"with {platform} cookies",
                cookies_file=cookies,
            ))
    else:
        # No cookies — only one attempt is possible
        attempts.append(DownloadAttempt(label="anonymous", cookies_file=""))

    return attempts


def interpret_attempt_failure(
    stderr: str,
    *,
    url: str,
    cfg: Config,
    attempts_remaining: int,
) -> tuple[ErrorDiagnosis, str | None]:
    """Classify a single attempt's stderr and decide what to do.

    Returns `(diagnosis, fail_message_or_None)`:
      - If we should try the next attempt → returns (diag, None)
      - If we should fail with a user-facing instruction → returns
        (diag, message). The caller raises PlatformBlockError or
        PlatformPermanentError using these.
    """
    diag = diagnose(stderr, url=url)
    platform = diag.platform

    # Permanent failures — never escalate (no retry, no point
    # showing a "register cookies" suggestion either)
    if diag.error_class in ("video_unavailable", "extractor_broken", "network"):
        msg = fix_instruction(diag, has_cookies=bool(_cookies_for_platform(cfg, platform)))
        return diag, msg  # permanent — but we still surface the instruction

    # Block-class — if we have another attempt with new info (cookies
    # we haven't tried yet), continue. Otherwise, this is the last
    # chance — return the instruction.
    if attempts_remaining > 0 and diag.retryable_with_cookies:
        return diag, None

    has_cookies = bool(_cookies_for_platform(cfg, platform))
    msg = fix_instruction(diag, has_cookies=has_cookies)
    return diag, msg


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------

def run_cascade(
    *,
    url: str,
    cfg: Config,
    do_attempt: callable,    # signature: (DownloadAttempt) -> (value | raises with .stderr)
):
    """Execute the cascade, calling `do_attempt(attempt)` for each
    planned attempt.

    `do_attempt` must:
      - Return the result (e.g. downloaded Path) on success.
      - Raise an exception whose `.stderr` attribute (str) contains
        the raw yt-dlp / instaloader stderr. The cascade inspects
        that to classify the error.

    Raises:
      PlatformBlockError    — when blocks were detected and no more
                              attempts available (or cookies wouldn't help).
      PlatformPermanentError — when the resource is truly unavailable.
    """
    plan = plan_attempts(url, cfg)
    last_diag: ErrorDiagnosis | None = None

    for i, attempt in enumerate(plan):
        try:
            return do_attempt(attempt)
        except Exception as e:
            stderr = getattr(e, "stderr", "") or str(e)
            attempts_remaining = len(plan) - i - 1
            diag, fail_msg = interpret_attempt_failure(
                stderr, url=url, cfg=cfg, attempts_remaining=attempts_remaining,
            )
            last_diag = diag

            if fail_msg is None:
                # Continue to next attempt (block, but we have escalation left)
                continue

            # Done — either permanent or last block
            if diag.error_class in ("video_unavailable", "extractor_broken", "network"):
                raise PlatformPermanentError(diag, fail_msg) from e
            raise PlatformBlockError(diag, fail_msg) from e

    # Plan exhausted without a return — shouldn't happen given plan
    # always has ≥1 entry, but be defensive:
    if last_diag is None:
        last_diag = diagnose("", url=url)
    raise PlatformBlockError(
        last_diag,
        f"All {len(plan)} download attempts failed.\n{fix_instruction(last_diag, has_cookies=bool(_cookies_for_platform(cfg, last_diag.platform)))}",
    )
