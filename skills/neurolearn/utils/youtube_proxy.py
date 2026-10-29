"""Opt-in secret for direct-first YouTube caption recovery (never media)."""
from __future__ import annotations

import os
from json import JSONDecodeError
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from dotenv import dotenv_values
from requests import Session
from requests.exceptions import ConnectionError, Timeout

from skills.neurolearn.config import ENV_PATH

PROXY_ENV = "NEUROLEARN_YOUTUBE_PROXY"
MAX_PROXY_ATTEMPTS = 2


class ProxyFallbackFailed(Exception):
    """Sanitized failure after bounded proxy recovery; existing fallback may run."""


class TranscriptSession(Session):
    def request(self, method, url, **kwargs):
        # Connect/read timeouts, not an overall wall-clock deadline.
        kwargs.setdefault("timeout", (10, 15))
        return super().request(method, url, **kwargs)


def get_proxy_url() -> str | None:
    """Read only the dedicated secret; empty environment value disables it."""
    value = os.environ.get(PROXY_ENV)
    if value is None:
        try:
            value = dotenv_values(ENV_PATH).get(PROXY_ENV)
        except OSError:
            return None
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.port == 0 or any(c.isspace() for c in value)):
            return None
    except ValueError:
        return None
    return value


def may_retry_with_proxy(error: Exception) -> bool:
    return isinstance(error, (ConnectionError, Timeout, ParseError, JSONDecodeError)) or type(error).__name__ in {
        "IpBlocked", "RequestBlocked", "YouTubeRequestFailed",
        "YouTubeDataUnparsable", "PoTokenRequired",
    }
