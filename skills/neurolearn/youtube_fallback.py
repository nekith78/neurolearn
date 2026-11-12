"""Report YouTube Data API fallback once per command, including parallel runs."""
from threading import Lock

import click

from skills.neurolearn.youtube_api import InvalidKey, NotConfigured, QuotaExhausted, YouTubeApiError


class FallbackNotice:
    def __init__(self) -> None:
        self._lock = Lock()
        self._reported = False
        self._reported_invalid_key = False

    def report(self, error: YouTubeApiError) -> None:
        with self._lock:
            reason = "request failed"
            if isinstance(error, InvalidKey):
                if self._reported_invalid_key:
                    return
                self._reported_invalid_key = True
                reason = ("key rejected. Replace it with "
                          "neurolearn config set-key youtube --from-file <path>")
                if self._reported:
                    click.echo(f"YouTube Data API: {reason}", err=True)
                    return
            elif isinstance(error, QuotaExhausted):
                reason = "quota exhausted"
            elif isinstance(error, NotConfigured):
                reason = "no key configured"
            if not self._reported:
                self._reported = True
                click.echo(f"YouTube Data API: {reason}. Falling back to yt-dlp.", err=True)


def fallback_notice_for_run() -> FallbackNotice:
    """Get the current Click run's notice, or start a standalone run.

    Parallel and non-CLI callers obtain one notice at entry and share it
    with every worker that can fall back.
    """
    context = click.get_current_context(silent=True)
    if context is None:
        return FallbackNotice()
    key = "neurolearn.youtube_fallback_notice"
    if key not in context.meta:
        context.meta[key] = FallbackNotice()
    return context.meta[key]
