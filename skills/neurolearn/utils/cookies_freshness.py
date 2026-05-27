"""Cookie-freshness helper.

YouTube cookies exported to a Netscape `cookies.txt` go stale fast: ~3-5
days even when exported correctly (incognito + closed tab), and STALE
cookies are net-negative — they can suppress formats and fail auth, i.e.
worse than sending none. See docs/research/yt-dlp-throttle-and-cookies-2026.md.

We don't read cookie expiry from the file contents (the session cookies
that matter often have no/unreliable expiry column); the file's
modification time is a good-enough proxy for "when did you last export".
This module only DETECTS staleness — callers decide whether to warn.
"""
from __future__ import annotations

import time
from pathlib import Path

# Conservative: YouTube cookies typically last ~3-5 days; warn past 3.
DEFAULT_MAX_AGE_DAYS = 3.0


def cookies_age_days(path: str | Path) -> float | None:
    """Age of the cookies file in days (by mtime). None if missing/unreadable."""
    if not path:
        return None
    p = Path(path).expanduser()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    return max(0.0, (time.time() - mtime) / 86400.0)


def is_cookies_stale(
    path: str | Path, *, max_age_days: float = DEFAULT_MAX_AGE_DAYS
) -> bool:
    """True when the cookies file exists and is older than `max_age_days`.
    Missing/unreadable files are NOT 'stale' (there's nothing to refresh)."""
    age = cookies_age_days(path)
    return age is not None and age > max_age_days
