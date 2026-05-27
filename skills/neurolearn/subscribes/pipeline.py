"""Subscribes command orchestration — stateful incremental update.

State update rules:
  • normal incremental (no --days/--since/--until): advance state to the
    newest RSS entry seen — even if transcription failed. A one-off network
    blip / 429 doesn't permanently re-replay the same videos; failed ids
    end up in `errors.log` and can be picked up via `research --since`.
  • first run (channel has no last_seen_*): MUST be invoked with explicit
    --days or --since to bootstrap the window. State is initialized in
    this run regardless of transcription outcome.
  • override on a channel that already has state (--days/--since/--until):
    one-off window, state is NOT touched — keeps the incremental stream
    intact for normal subsequent runs.

The "state advances after RSS, not after transcribe success" rule is the
fix for the v0.7 bootstrap deadlock: previously, --days marked the whole
run as "override → don't update state", so first run never initialized
state and the next incremental run still asked for --days.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from skills.neurolearn.utils.console import make_console

from skills.neurolearn.subscribes.store import (
    Channel, load_subscribes, DEFAULT_MODE, MODES,
)
from skills.neurolearn.subscribes.state import (
    update_last_seen, channels_without_state,
)
from skills.neurolearn.subscribes.group import filter_by_group
from skills.neurolearn.subscribes.rss import (
    fetch_rss, entries_after, RssEntry,
)
from skills.neurolearn.shared.date_filter import (
    parse_window, in_window,
)
from skills.neurolearn.shared.match import match_titles
from skills.neurolearn.shared.llm_screen import screen_candidates
from skills.neurolearn.history.store import RunEntry, append_run
from skills.neurolearn.transcribe import (
    _run_batch_pipeline, _run_then_analyze, _stdin_is_tty,
)
from skills.neurolearn.utils.resolver import ResolvedTarget
from skills.neurolearn.research.source import SearchCandidate


class SubscribesError(Exception):
    """Pipeline-level error (e.g. missing initial state)."""


class ChannelNotFoundError(Exception):
    """A channel's identifier (IG username / TikTok @handle) doesn't resolve
    on the platform anymore — typically a rename.

    Raised by _fetch_via_yt_dlp; the per-channel loop catches it and surfaces
    the friendly "username changed?" hint without aborting other channels.
    """


@dataclass
class _ChannelVideo:
    """Unified shape for entries from RSS or yt-dlp channel scrape."""
    video_id: str
    url: str
    title: str
    duration_sec: int | None  # None on RSS path; populated by yt-dlp path
    published: datetime


_console = make_console()


_NOT_FOUND_SIGNATURES = (
    "does not exist",
    "is not available",
    "user not found",
    "profile not found",
    "404",
    "not found",
    "private account",
    "this account",
)

# yt-dlp signatures indicating the Instagram extractor itself is broken
# upstream (not a per-user problem). When we see one of these on an IG
# URL, we fall back to instaloader. Don't include "not found" here —
# that's a real channel-not-found situation, handled separately.
_YT_DLP_IG_BROKEN_SIGNATURES = (
    "unable to extract data",
    "marked as broken",
    "empty media response",
)


def _looks_like_yt_dlp_broken_extractor(err_text: str) -> bool:
    lower = err_text.lower()
    return any(sig in lower for sig in _YT_DLP_IG_BROKEN_SIGNATURES)


def _looks_like_channel_not_found(err_text: str) -> bool:
    """Heuristic: did yt-dlp fail because the username doesn't exist?

    yt-dlp's error messages vary by extractor; pattern-match common
    "user gone" signatures so we can give a useful hint instead of
    re-raising a wall of yt-dlp text.
    """
    lower = err_text.lower()
    return any(sig in lower for sig in _NOT_FOUND_SIGNATURES)


def _fetch_instagram(ch, *, cookies_file: str | None) -> list[_ChannelVideo]:
    """Two-step Instagram fetch: yt-dlp first, instaloader as fallback.

    The Instagram extractor in yt-dlp is currently broken upstream — when
    it returns "Unable to extract data" / similar, we try instaloader
    (optional dep). If instaloader isn't installed, we re-raise the
    original yt-dlp DownloadError so the user sees the suggestion to
    install the `[instagram]` extra.

    Username (the instaloader identifier) is the channel_id we stored at
    `subscribes add` time.
    """
    try:
        return _fetch_via_yt_dlp(
            ch.url,
            cookies_file=cookies_file,
            accept_missing_dates=True,
        )
    except Exception as e:
        if not _looks_like_yt_dlp_broken_extractor(str(e)):
            raise

    # yt-dlp's IG extractor is broken upstream — try instaloader.
    try:
        from skills.neurolearn.subscribes.instagram_loader import (
            InstaloaderUnavailable, fetch_profile_videos,
        )
    except ImportError:
        _console.print(
            "[yellow]Instagram fallback: instaloader not installed. "
            "Run `uv sync --extra instagram` to enable.[/yellow]"
        )
        return []

    try:
        username = ch.channel_id or (ch.handle or "").lstrip("@")
        if not username:
            return []
        return fetch_profile_videos(
            username, cookies_file=cookies_file, limit=30,
        )
    except InstaloaderUnavailable as e:
        _console.print(f"[yellow]Instagram fallback unavailable: {e}[/yellow]")
        return []
    except ValueError as e:
        # ValueError from instagram_loader._load_cookies_into_session
        # signals malformed cookies file — the message already contains
        # the re-export instruction.
        _console.print(f"[yellow]Instagram fallback: {e}[/yellow]")
        return []
    except Exception as e:
        if _looks_like_channel_not_found(str(e)):
            raise ChannelNotFoundError(str(e)) from e
        # instaloader.LoginRequiredException → cookies expired
        err_text = str(e).lower()
        cls_name = type(e).__name__
        if (
            cls_name == "LoginRequiredException"
            or "login" in err_text
            or "logged in" in err_text
            or "401" in err_text
            or "403" in err_text
        ):
            _console.print(
                "[yellow]Instagram cookies look expired or rate-limited.\n"
                "  Re-export from your browser and update:\n"
                "  neurolearn subscribes cookies set instagram <path>[/yellow]"
            )
            return []
        _console.print(
            f"[yellow]Instagram fallback (instaloader) failed for "
            f"{ch.url}: {e}[/yellow]"
        )
        return []


def _fetch_via_yt_dlp(
    channel_url: str,
    *,
    limit: int = 30,
    cookies_file: str | None = None,
    accept_missing_dates: bool = False,
) -> list[_ChannelVideo]:
    """yt-dlp profile scraper. Returns entries with `duration_sec` populated.

    Used for:
      • YouTube `--no-rss` fallback (no RSS, want duration metadata)
      • Instagram (no RSS exists; needs cookies)
      • TikTok (no RSS exists; cookies optional)

    `cookies_file` is the path to a Netscape cookies.txt the user exported
    themselves. We DELIBERATELY don't accept a `cookies_browser` parameter:
    `cookies-from-browser` pulls ALL the user's browser cookies into process
    memory, violating principle of least privilege. See the project memory
    file `feedback_cookies_strict_file_only.md`.

    `accept_missing_dates=True` (set for IG/TikTok): when yt-dlp's flat
    extract returns an entry without `upload_date` — which is the norm
    for IG and TikTok — synthesize a descending sequence of timestamps
    starting from now() so the entries keep their newest-first order
    through the date-window filter. The caller is expected to dedup by
    `video_id` against `last_seen_video_id` instead of trusting the dates.

    Raises ChannelNotFoundError when the platform reports the user
    doesn't exist — the per-channel loop catches it to print a clear
    "username changed?" hint without halting the whole run.
    """
    from skills.neurolearn.utils.downloader import (
        expand_channel_or_playlist,
    )
    try:
        entries = expand_channel_or_playlist(
            channel_url, limit=limit, cookies_file=cookies_file,
        )
    except Exception as e:
        if _looks_like_channel_not_found(str(e)):
            raise ChannelNotFoundError(str(e)) from e
        if _looks_like_yt_dlp_broken_extractor(str(e)):
            # Don't swallow — propagate so platform-specific fetchers
            # (e.g. _fetch_instagram) can decide whether to try a
            # fallback like instaloader. Other callers still get a
            # raised exception they can handle generically.
            raise
        _console.print(
            f"[yellow]yt-dlp fetch failed for {channel_url}: {e}[/yellow]"
        )
        return []

    out: list[_ChannelVideo] = []
    now = datetime.now(timezone.utc)
    for idx, e in enumerate(entries):
        if e.upload_date is not None:
            pub = datetime.combine(
                e.upload_date, datetime.min.time(), tzinfo=timezone.utc,
            )
        elif accept_missing_dates:
            # Synthetic descending stamp: idx=0 (newest) → now, idx=1 →
            # now - 1min, etc. Preserves ordering for the downstream window
            # filter without claiming a real publish time.
            pub = now.replace(microsecond=0) - timedelta(minutes=idx)
        else:
            # YouTube path: without a date we can't apply the window — skip.
            continue
        out.append(_ChannelVideo(
            video_id=e.video_id, url=e.url, title=e.title or "",
            duration_sec=e.duration_sec, published=pub,
        ))
    return out


def _fetch_shorts(
    channel_url: str,
    *,
    limit: int = 20,
    cookies_file: str | None = None,
) -> list[_ChannelVideo]:
    """Fetch the channel's `/shorts` tab via yt-dlp full-extract.

    Why full-extract (`extract_flat=False`):
      yt-dlp's flat-extract on `<channel>/shorts` returns video IDs but
      sets `duration` and `upload_date` to None — verified empirically
      (2026-05-27). Without dates the date-window filter ("shorts in
      the last N days") can't run, so we must pay for full info per
      entry. `playlistend=limit` caps the network cost: for default
      cap=5 the orchestrator passes limit=20 (cap*4 buffer for window
      filtering), so worst case ~20 HTTP requests per channel per
      update on `auto`/`shorts-only` mode.

    Returns `_ChannelVideo` entries with `duration_sec` populated and
    URLs in `https://www.youtube.com/shorts/<id>` form (yt-dlp emits
    `webpage_url=watch?v=...` on full-extract, but we rewrite to the
    canonical shorts URL so downstream batch metadata matches what
    YouTube classifies as a Short).

    Errors mirror `_fetch_via_yt_dlp` — ChannelNotFoundError bubbles
    up so the per-channel loop can print a clear hint without aborting.
    """
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    shorts_url = channel_url.rstrip("/") + "/shorts"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "playlistend": max(1, int(limit)),
        "lazy_playlist": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(shorts_url, download=False) or {}
    except DownloadError as e:
        if _looks_like_channel_not_found(str(e)):
            raise ChannelNotFoundError(str(e)) from e
        _console.print(
            f"[yellow]yt-dlp /shorts fetch failed for {channel_url}: "
            f"{e}[/yellow]"
        )
        return []

    out: list[_ChannelVideo] = []
    entries = info.get("entries") or []
    for e in entries:
        if not e or not e.get("id"):
            continue
        vid = e["id"]
        ts = e.get("timestamp")
        upload = e.get("upload_date")
        # Prefer `timestamp` (unix seconds, second-precision) over
        # `upload_date` (YYYYMMDD, day-precision). Day-precision is
        # fine for the window filter but loses ordering granularity
        # when several shorts dropped on the same day.
        if ts is not None:
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        elif upload:
            try:
                d = datetime.strptime(upload, "%Y%m%d").date()
                published = datetime.combine(
                    d, datetime.min.time(), tzinfo=timezone.utc,
                )
            except ValueError:
                # yt-dlp gave us an unparseable date — skip rather than
                # silently date this entry to epoch, which would make
                # every window-filter request include it.
                continue
        else:
            continue
        out.append(_ChannelVideo(
            video_id=vid,
            url=f"https://www.youtube.com/shorts/{vid}",
            title=e.get("title") or "",
            duration_sec=int(e["duration"]) if e.get("duration") else None,
            published=published,
        ))
    return out


def _fetch_youtube_videos(ch: Channel, *, no_rss: bool) -> list[_ChannelVideo]:
    """YouTube full-video stream: RSS by default, yt-dlp on `--no-rss`.

    Extracted from the old per-channel branch so the four-mode router can
    invoke it independently from the Shorts fetcher.
    """
    if no_rss:
        return _fetch_via_yt_dlp(ch.url)
    return [
        _ChannelVideo(
            video_id=e.video_id, url=e.url, title=e.title,
            duration_sec=None, published=e.published,
        )
        for e in fetch_rss(ch.channel_id)
    ]


def _apply_window(
    entries: list[_ChannelVideo],
    ch: Channel,
    window,
) -> list[_ChannelVideo]:
    """Apply window filter; fall through to `last_seen_published` cursor when
    no explicit window was provided. Mirrors the pre-v0.17 inline logic."""
    if window is not None:
        return [e for e in entries if in_window(e.published, window)]
    cutoff = (
        _parse_iso(ch.last_seen_published) if ch.last_seen_published else None
    )
    if cutoff is not None:
        return [e for e in entries if e.published > cutoff]
    return list(entries)


def _cap_shorts(
    entries: list[_ChannelVideo], ch: Channel, cap: int,
) -> list[_ChannelVideo]:
    """Cap a Shorts stream after window filter. `cap=0` means no cap.

    Warning is printed once per channel when the cap actually fires —
    silent capping would hide that the user is missing content.
    """
    if cap <= 0 or len(entries) <= cap:
        return entries
    sorted_entries = sorted(entries, key=lambda e: e.published, reverse=True)
    capped = sorted_entries[:cap]
    label = ch.handle or ch.channel_id or ch.url
    _console.print(
        f"[yellow][warn] {label}: {len(entries)} shorts in window, "
        f"taking {cap} newest. Raise with --shorts-cap N or set "
        f"shorts_max_per_update in config.toml.[/yellow]"
    )
    return capped


def _dedup_by_id(
    entries: list[_ChannelVideo],
) -> list[_ChannelVideo]:
    """Keep first occurrence by `video_id` (preserves input ordering).
    Caller is expected to sort the merged stream so the entry it wants
    to win on collision is listed first."""
    seen: set[str] = set()
    out: list[_ChannelVideo] = []
    for e in entries:
        if e.video_id in seen:
            continue
        seen.add(e.video_id)
        out.append(e)
    return out


def _shorts_fetch_limit(cap: int) -> int:
    """How many raw `/shorts` entries to ask yt-dlp for.

    Buffer of `cap*4` (min 20) leaves room for window filtering: if the
    user wants the 5 newest shorts in the last 3 days but the channel
    posted 12 a week ago, we still pull enough to give the window
    something to chew on. `cap=0` (unbounded user intent) caps at 100
    so a forever-running shorts firehose can't lock up the update.
    """
    if cap <= 0:
        return 100
    return max(cap * 4, 20)


def _fetch_youtube_entries(
    ch: Channel,
    *,
    effective_mode: str,
    no_rss: bool,
    window,
    shorts_cap: int,
    youtube_cookies_file: str,
) -> list[_ChannelVideo]:
    """Route fetch+window+cap for a YouTube channel per its effective mode.

    Returns the channel's contribution to the candidate list (post-window,
    post-cap, deduped where applicable). See docs/specs/v0.17-subscribes-shorts.md
    for the routing decision tree.
    """
    if effective_mode == "videos-only":
        videos = _fetch_youtube_videos(ch, no_rss=no_rss)
        return _apply_window(videos, ch, window)

    if effective_mode == "shorts-only":
        shorts = _fetch_shorts(
            ch.url,
            limit=_shorts_fetch_limit(shorts_cap),
            cookies_file=youtube_cookies_file or None,
        )
        shorts = _apply_window(shorts, ch, window)
        return _cap_shorts(shorts, ch, shorts_cap)

    if effective_mode == "shorts-and-videos":
        videos = _apply_window(
            _fetch_youtube_videos(ch, no_rss=no_rss), ch, window,
        )
        shorts = _apply_window(
            _fetch_shorts(
                ch.url,
                limit=_shorts_fetch_limit(shorts_cap),
                cookies_file=youtube_cookies_file or None,
            ),
            ch, window,
        )
        shorts = _cap_shorts(shorts, ch, shorts_cap)
        # Sort by published desc, dedup by id. Shorts come first in the
        # concat so a colliding id (rare — same content visible on both
        # tabs) keeps the Shorts entry (it has `duration_sec`, RSS path
        # doesn't, and the Shorts URL is the canonical one for that ID).
        merged = sorted(
            shorts + videos, key=lambda e: e.published, reverse=True,
        )
        return _dedup_by_id(merged)

    # "auto": videos first, fallback to shorts only if window has nothing.
    videos = _apply_window(
        _fetch_youtube_videos(ch, no_rss=no_rss), ch, window,
    )
    if videos:
        return videos
    shorts = _fetch_shorts(
        ch.url,
        limit=_shorts_fetch_limit(shorts_cap),
        cookies_file=youtube_cookies_file or None,
    )
    shorts = _apply_window(shorts, ch, window)
    return _cap_shorts(shorts, ch, shorts_cap)


def run_subscribes_update(
    *,
    subscribes_path: Path,
    group: str | None,
    days: int | None,
    since: date | None,
    until: date | None,
    match: str | None,
    filter_text: str | None,
    no_rss: bool,
    yes: bool,
    no_analyze: bool,
    prompt: str | None,
    prompt_file: Path | None,
    analyze_backend: str,
    filter_backend: str,
    ollama_model: str,
    ollama_host: str,
    no_stdout: bool,
    output_dir: str,
    api_keys: dict[str, str | None],
    batch_opts: dict,
    platform: str | None = None,
    instagram_cookies_file: str = "",
    tiktok_cookies_file: str = "",
    youtube_cookies_file: str = "",
    # v0.17: shorts handling
    cli_override_mode: str | None = None,
    shorts_cap: int = 5,
) -> Path | None:
    """Run subscribes update. Returns Path to batch folder or None."""

    channels = load_subscribes(subscribes_path)
    channels = filter_by_group(channels, group)
    if platform:
        # Combines with --group: AND semantics. Empty result is a noisy no-op
        # rather than an error — the user might be running both filters
        # simultaneously in a script.
        channels = [c for c in channels if c.platform == platform]
    if not channels:
        scope_bits = []
        if platform:
            scope_bits.append(f"platform={platform}")
        if group:
            scope_bits.append(f"group={group}")
        scope = " ".join(scope_bits) if scope_bits else "—"
        _console.print(
            f"[yellow]No channels match the filter ({scope}).[/yellow]"
        )
        return None

    is_override = days is not None or since is not None or until is not None
    window = parse_window(days=days, since=since, until=until,
                         now=date.today()) if is_override else None

    # First-run validation
    if not is_override:
        missing = channels_without_state(channels)
        if missing:
            handles = ", ".join(c.handle or c.channel_id for c in missing)
            raise SubscribesError(
                f"--days or --since required for initial run of: {handles}"
            )

    # Per-channel: fetch + filter
    candidates: list[SearchCandidate] = []
    state_updates: list[tuple[str, str, str]] = []

    for ch in channels:
        if not ch.channel_id:
            continue

        # Per-platform source dispatch:
        #   • YouTube: routed through _fetch_youtube_entries which honors
        #     the per-channel `mode` (auto / videos-only / shorts-only /
        #     shorts-and-videos), the `--shorts-cap`, and the window filter.
        #     v0.17+: includes Shorts fallback on `auto` when RSS is empty.
        #   • Instagram: yt-dlp first; on broken-extractor fallback to
        #     instaloader (optional `[instagram]` extra). No RSS exists.
        #   • TikTok: always yt-dlp scrape; cookies optional.
        # `accept_missing_dates=True` for IG/TT — those platforms' flat
        # extracts don't include upload_date, so we synthesize a descending
        # stamp from now() and rely on last_seen_video_id for dedup below.
        # Cookies come from a user-managed file (see config.toml [instagram]/
        # [tiktok].cookies_file), NOT from `cookies-from-browser`.
        try:
            if ch.platform == "instagram":
                entries = _fetch_instagram(
                    ch, cookies_file=instagram_cookies_file or None,
                )
            elif ch.platform == "tiktok":
                entries = _fetch_via_yt_dlp(
                    ch.url,
                    cookies_file=tiktok_cookies_file or None,
                    accept_missing_dates=True,
                )
            else:
                # YouTube — four-mode router (auto/videos-only/shorts-only/
                # shorts-and-videos). The mode is resolved here so per-call
                # CLI overrides win over the stored per-channel setting.
                effective_mode = cli_override_mode or ch.mode or DEFAULT_MODE
                entries = _fetch_youtube_entries(
                    ch,
                    effective_mode=effective_mode,
                    no_rss=no_rss,
                    window=window,
                    shorts_cap=shorts_cap,
                    youtube_cookies_file=youtube_cookies_file,
                )
        except ChannelNotFoundError:
            # Username changed (or account deleted / privated). Surface a clear
            # hint and move to the next channel — DO NOT advance state, so on
            # the next run we still notice the channel is broken.
            identifier = ch.handle or ch.channel_id
            _console.print(
                f"[red]✗ {identifier}: channel not found on {ch.platform}.[/red]\n"
                f"  The user may have changed their username or deleted the account.\n"
                f"  Check {ch.url} and update the entry:\n"
                f"    neurolearn subscribes remove {identifier}\n"
                f"    neurolearn subscribes add <new-url>"
            )
            continue
        if not entries:
            continue

        # IG/TT post-fetch filtering (kept inline — YouTube already had its
        # window applied inside `_fetch_youtube_entries`).
        # For IG/TikTok, dates are synthetic — the date window pass-through is
        # imprecise. Reliable dedup is via last_seen_video_id: yt-dlp returns
        # entries newest-first, so we stop scanning when we hit the last id
        # we processed previously. On first run (no last_seen_video_id), every
        # entry is "new".
        if ch.platform in ("instagram", "tiktok"):
            if ch.last_seen_video_id:
                fresh: list[_ChannelVideo] = []
                for e in entries:
                    if e.video_id == ch.last_seen_video_id:
                        break
                    fresh.append(e)
                entries = fresh
            elif window is not None:
                entries = [e for e in entries if in_window(e.published, window)]
            else:
                cutoff = (
                    _parse_iso(ch.last_seen_published)
                    if ch.last_seen_published else None
                )
                if cutoff is not None:
                    entries = [e for e in entries if e.published > cutoff]

        if not entries:
            continue

        for e in entries:
            candidates.append(SearchCandidate(
                video_id=e.video_id, url=e.url, title=e.title,
                channel=ch.handle or ch.url,
                duration_sec=e.duration_sec,
                upload_date=e.published.date(),
                source_language="(subscribes)",
            ))

        # Should state advance? Two cases that DO update:
        #   1. normal incremental (no override flags) — sliding window forward
        #   2. bootstrap — channel had no state, this is the first run, the
        #      --days/--since/--until window is initializing rather than
        #      "overriding" anything.
        # Override on a channel that already has state stays a no-op.
        is_bootstrap = ch.last_seen_published is None
        if not is_override or is_bootstrap:
            newest = max(entries, key=lambda e: e.published)
            state_updates.append((
                ch.channel_id, newest.video_id, newest.published.isoformat(),
            ))

    if not candidates:
        _console.print(
            "[yellow]No new videos since the last run.[/yellow]"
        )
        return None

    # Apply --match
    if match:
        candidates = match_titles(candidates, match)

    # Apply --filter (LLM)
    if filter_text and candidates:
        candidates = screen_candidates(
            candidates, filter_text,
            backend=filter_backend,
            api_key=api_keys.get(_backend_to_key(filter_backend)),
            ollama_model=ollama_model, ollama_host=ollama_host,
        )

    if not candidates:
        _console.print("[yellow]Nothing left after filters.[/yellow]")
        return None

    # TTY checkpoint
    if not yes and _stdin_is_tty():
        candidates = _tty_checkpoint(candidates)
        if not candidates:
            _console.print("[yellow]Cancelled.[/yellow]")
            return None

    # Batch pipeline
    targets = [
        ResolvedTarget(
            url=c.url, video_id=c.video_id, title=c.title,
            channel=c.channel, duration_sec=c.duration_sec,
            upload_date=c.upload_date, source="channel",
            source_language=getattr(c, "source_language", None),
        )
        for c in candidates
    ]
    batch_name = f"subscribes_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    from skills.neurolearn.config import (
        load_config, CONFIG_PATH, DEFAULT_CONFIG,
    )
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else DEFAULT_CONFIG
    opts = {
        "output_dir": output_dir,
        "batch_name": batch_name,
        "no_combined": batch_opts.get("no_combined", False),
        "fail_fast": batch_opts.get("fail_fast", False),
        **batch_opts,
    }
    batch_dir = _run_batch_pipeline(targets=targets, cfg=cfg, opts=opts)

    analyze_attempted = False
    analyze_produced = False
    if not no_analyze and batch_dir is not None and batch_dir.exists():
        analyze_attempted = True
        _run_then_analyze(
            batch_folder=batch_dir,
            prompt_inline=prompt, prompt_file=prompt_file,
            backend=analyze_backend,
        )
        analyze_produced = any(batch_dir.glob("analysis-*.md"))

    # State update: collected per-channel above according to bootstrap /
    # incremental / override rules. Applied unconditionally — we want state
    # to advance even when 0/N transcripts succeeded (failed ids show up in
    # errors.log; user can re-fetch them via `research --since`).
    for chan_id, vid, pub in state_updates:
        update_last_seen(subscribes_path, chan_id, vid, pub)

    if batch_dir is None:
        status = "failed"
    elif analyze_attempted and not analyze_produced:
        status = "partial"
    else:
        status = "ok"

    _append_history(
        group=group, output=str(batch_dir) if batch_dir else "",
        videos_found=len(candidates),
        prompt=prompt or (prompt_file.read_text() if prompt_file else None),
        analyze_backend=None if no_analyze else analyze_backend,
        status=status,
    )

    return batch_dir


def _tty_checkpoint(candidates: list) -> list:
    try:
        import questionary
    except ImportError:
        return list(candidates)
    choices = []
    for i, c in enumerate(candidates, start=1):
        title = (c.title or "—")[:60]
        date_str = c.upload_date.isoformat() if c.upload_date else "—"
        label = f"{date_str}  {title}  [{c.channel}]"
        choices.append(questionary.Choice(title=label, value=i - 1, checked=True))
    answer = questionary.checkbox(
        "Pick videos to analyze (Space=toggle, Enter=ok):",
        choices=choices,
    ).ask()
    if answer is None:
        return []
    return [candidates[i] for i in answer]


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _backend_to_key(backend: str) -> str:
    return {"gemini": "gemini", "claude": "anthropic",
            "openai": "openai", "ollama": "ollama"}[backend]


def _append_history(
    *, group, output, videos_found, prompt, analyze_backend,
    status: str = "ok",
) -> None:
    p = Path.home() / ".neurolearn" / "history.toml"
    # See research.pipeline._append_history for the format rationale.
    ts = datetime.now(timezone.utc).strftime("%m%d-%H%M%S")
    run_id = f"s-{ts}"
    entry = RunEntry(
        id=run_id, type="subscribes",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=None, group=group,
        output=output, videos_found=videos_found,
        analyze_backend=analyze_backend,
        analyze_prompt_preview=((prompt or "")[:200]) if prompt else None,
        status=status,
    )
    append_run(p, entry)
