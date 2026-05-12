"""Subscribes command orchestration — stateful incremental update.

Default: per-channel RSS-first discovery filtered by last_seen_published.
After successful run, updates last_seen_* in TOML.

Override (--days / --since / --until): applies global window, does NOT
update state — keeps incremental stream intact for normal runs.

First-run for channels without state: requires explicit --days or
--since (else SubscribesError).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console

from skills.youtube_transcribe.subscribes.store import (
    Channel, load_subscribes,
)
from skills.youtube_transcribe.subscribes.state import (
    update_last_seen, channels_without_state,
)
from skills.youtube_transcribe.subscribes.group import filter_by_group
from skills.youtube_transcribe.subscribes.rss import (
    fetch_rss, entries_after, RssEntry,
)
from skills.youtube_transcribe.shared.date_filter import (
    parse_window, in_window,
)
from skills.youtube_transcribe.shared.match import match_titles
from skills.youtube_transcribe.shared.llm_screen import screen_candidates
from skills.youtube_transcribe.history.store import RunEntry, append_run
from skills.youtube_transcribe.transcribe import (
    _run_batch_pipeline, _run_then_analyze, _stdin_is_tty,
)
from skills.youtube_transcribe.utils.resolver import ResolvedTarget
from skills.youtube_transcribe.research.source import SearchCandidate


class SubscribesError(Exception):
    """Pipeline-level error (e.g. missing initial state)."""


_console = Console()


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
) -> Path | None:
    """Run subscribes update. Returns Path to batch folder or None."""

    channels = load_subscribes(subscribes_path)
    channels = filter_by_group(channels, group)
    if not channels:
        _console.print("[yellow]Нет каналов (или группа пуста).[/yellow]")
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

        if no_rss:
            _console.print(f"[yellow]--no-rss not yet implemented for "
                           f"{ch.handle}; skipping.[/yellow]")
            continue

        entries = fetch_rss(ch.channel_id)
        if not entries:
            continue

        if window is not None:
            entries = [e for e in entries if in_window(e.published, window)]
        else:
            cutoff = _parse_iso(ch.last_seen_published) if ch.last_seen_published else None
            if cutoff is not None:
                entries = entries_after(entries, cutoff)

        if not entries:
            continue

        for e in entries:
            candidates.append(SearchCandidate(
                video_id=e.video_id, url=e.url, title=e.title,
                channel=ch.handle or ch.url,
                duration_sec=None,
                upload_date=e.published.date(),
                source_language="(subscribes)",
            ))

        if not is_override:
            newest = max(entries, key=lambda e: e.published)
            state_updates.append((
                ch.channel_id, newest.video_id, newest.published.isoformat(),
            ))

    if not candidates:
        _console.print(
            "[yellow]Нет новых видео с момента последнего запуска.[/yellow]"
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
        _console.print("[yellow]После фильтров ничего не осталось.[/yellow]")
        return None

    # TTY checkpoint
    if not yes and _stdin_is_tty():
        candidates = _tty_checkpoint(candidates)
        if not candidates:
            _console.print("[yellow]Отменено.[/yellow]")
            return None

    # Batch pipeline
    targets = [
        ResolvedTarget(
            url=c.url, video_id=c.video_id, title=c.title,
            channel=c.channel, duration_sec=c.duration_sec,
            upload_date=c.upload_date, source="channel",
        )
        for c in candidates
    ]
    batch_name = f"subscribes_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    from skills.youtube_transcribe.config import (
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

    if not no_analyze and batch_dir is not None and batch_dir.exists():
        _run_then_analyze(
            batch_folder=batch_dir,
            prompt_inline=prompt, prompt_file=prompt_file,
            backend=analyze_backend,
        )

    # State update (only if NOT override and we actually ran successfully)
    if not is_override and batch_dir is not None:
        for chan_id, vid, pub in state_updates:
            update_last_seen(subscribes_path, chan_id, vid, pub)

    _append_history(
        group=group, output=str(batch_dir) if batch_dir else "",
        videos_found=len(candidates),
        prompt=prompt or (prompt_file.read_text() if prompt_file else None),
        analyze_backend=None if no_analyze else analyze_backend,
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
        "Выбери видео для analyze (Space=toggle, Enter=ok):",
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


def _append_history(*, group, output, videos_found, prompt, analyze_backend) -> None:
    p = Path.home() / ".youtube-transcribe" / "history.toml"
    run_id = (
        f"subscribes_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )
    entry = RunEntry(
        id=run_id, type="subscribes",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=None, group=group,
        output=output, videos_found=videos_found,
        analyze_backend=analyze_backend,
        analyze_prompt_preview=((prompt or "")[:200]) if prompt else None,
        status="ok",
    )
    append_run(p, entry)
