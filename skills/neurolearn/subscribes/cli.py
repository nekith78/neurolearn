"""CLI for `neurolearn subscribes` group:
add / remove / list / edit / update / schedule install|uninstall.
"""
from __future__ import annotations
from skills.neurolearn.constants import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
from skills.neurolearn.utils.console import make_console
from rich.table import Table

from skills.neurolearn.subscribes.store import (
    Channel, MODES, DEFAULT_MODE, add_channel, load_subscribes,
    remove_channel, update_channel_mode,
)
from skills.neurolearn.subscribes._sync_hook import maybe_sync
from skills.neurolearn.subscribes.group import filter_by_group
from skills.neurolearn.subscribes.channel_resolver import (
    resolve_channel,
)
from skills.neurolearn.subscribes.schedule import (
    detect_platform, parse_interval,
    generate_cron_line, generate_launchd_plist,
    generate_systemd_units, generate_taskscheduler_xml,
)

SUBSCRIBES_PATH = Path.home() / ".neurolearn" / "subscribes.toml"

_console = make_console()


@click.group(name="subscribes")
def subscribes_group() -> None:
    """Manage and run subscribes (channel list + incremental update)."""
    maybe_sync("on_read")   # optional local state pull at group entry (inert unless opted in)


@subscribes_group.command(name="add")
@click.argument("channel_url", required=False)
@click.option("--group", default=None,
              help="Optional group tag (e.g. 'ai-research').")
@click.option("--mode", "mode_opt",
              type=click.Choice(list(MODES)), default=DEFAULT_MODE,
              show_default=True,
              help="Per-channel content-source mode (YouTube only): "
                   "auto (RSS + Shorts fallback when RSS empty), "
                   "videos-only, shorts-only, shorts-and-videos. v0.17+.")
def add_cmd(channel_url: str | None, group: str | None,
            mode_opt: str) -> None:
    """Add a channel by URL. Platform is auto-detected from the URL."""
    if not channel_url:
        from skills.neurolearn.shared.prompts import prompt_url_or_die
        channel_url = prompt_url_or_die("Paste channel URL:")
    try:
        resolved = resolve_channel(channel_url)
    except ValueError as e:
        _console.print(f"[red]Could not resolve channel:[/red] {e}")
        sys.exit(3)

    # On first IG / TikTok add: if cookies aren't set up yet AND we're in
    # a TTY, offer the interactive wizard. In non-TTY (Claude Code, CI)
    # we silently print a one-liner hint — no blocking prompts.
    if resolved.platform in ("instagram", "tiktok"):
        from skills.neurolearn.subscribes.cookies_onboarding import (
            resolve_cookies_file, wizard,
        )
        if not resolve_cookies_file(resolved.platform):
            if sys.stdin.isatty() and click.confirm(
                f"Cookies for {resolved.platform} are not configured yet. "
                "Set them up now?",
                default=False,
            ):
                wizard(resolved.platform)
            else:
                _console.print(
                    f"[dim]⚠ {resolved.platform} needs cookies. "
                    f"Set them up later: "
                    f"neurolearn subscribes cookies set "
                    f"{resolved.platform}[/dim]"
                )

    # mode is YouTube-only — silently coerce IG/TT to "auto" so the
    # toml stays clean and a future YouTube-mode flag rename doesn't
    # silently break IG entries.
    effective_mode = mode_opt if resolved.platform == "youtube" else DEFAULT_MODE
    channel = Channel(
        url=resolved.url,
        handle=resolved.handle,
        channel_id=resolved.channel_id,
        group=group,
        added=date.today().isoformat(),
        platform=resolved.platform,
        mode=effective_mode,
    )
    add_channel(SUBSCRIBES_PATH, channel)
    mode_suffix = (
        f", mode={effective_mode}"
        if resolved.platform == "youtube" and effective_mode != DEFAULT_MODE
        else ""
    )
    _console.print(
        f"[green]✓[/green] Added {resolved.handle or resolved.url} "
        f"([cyan]{resolved.platform}[/cyan], "
        f"id={resolved.channel_id}, group={group or '—'}{mode_suffix})"
    )
    if resolved.platform != "youtube" and mode_opt != DEFAULT_MODE:
        _console.print(
            "[dim]Note: --mode applies to YouTube channels only; "
            "stored as 'auto' for IG/TT.[/dim]"
        )


@subscribes_group.command(name="remove")
@click.argument("identifier")
def remove_cmd(identifier: str) -> None:
    """Remove a channel by handle, URL, or channel_id."""
    if not remove_channel(SUBSCRIBES_PATH, identifier):
        _console.print(f"[red]Channel not found: {identifier}[/red]")
        sys.exit(3)
    _console.print(f"[green]✓[/green] Removed {identifier}")


@subscribes_group.command(name="set-mode")
@click.argument("identifier")
@click.argument("mode", type=click.Choice(list(MODES)))
def set_mode_cmd(identifier: str, mode: str) -> None:
    """Set the per-channel mode for an existing subscription. v0.17+.

    \b
    Modes (YouTube channels only):
      auto              — RSS first; fall back to /shorts when RSS is
                          empty in the requested window. Default.
      videos-only       — RSS only, never look at /shorts.
      shorts-only       — /shorts only, never look at full uploads.
      shorts-and-videos — BOTH streams, deduped by video id, newest
                          first. Use for channels that mix both.

    IDENTIFIER matches the same way as `subscribes remove`: by handle,
    URL, or channel_id.
    """
    try:
        updated = update_channel_mode(SUBSCRIBES_PATH, identifier, mode)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
    if not updated:
        _console.print(f"[red]Channel not found: {identifier}[/red]")
        sys.exit(3)
    _console.print(
        f"[green]✓[/green] {identifier} → mode=[cyan]{mode}[/cyan]"
    )


@subscribes_group.command(name="list")
@click.option("--group", default=None, help="Filter by group.")
@click.option("--platform",
              type=click.Choice(["youtube", "instagram", "tiktok"]),
              default=None,
              help="Show only one platform.")
def list_cmd(group: str | None, platform: str | None) -> None:
    """List subscribed channels grouped by platform."""
    from skills.neurolearn.subscribes.store import PLATFORMS
    channels = load_subscribes(SUBSCRIBES_PATH)
    channels = filter_by_group(channels, group)
    if platform:
        channels = [c for c in channels if c.platform == platform]
    if not channels:
        _console.print("[yellow]No channels.[/yellow]")
        return

    # Partition by platform, render one table per group with non-empty rows.
    by_platform: dict[str, list] = {p: [] for p in PLATFORMS}
    for c in channels:
        # Defensive: silently skip any platform we don't know how to render.
        if c.platform in by_platform:
            by_platform[c.platform].append(c)

    printed_any = False
    for plat in PLATFORMS:
        rows = by_platform[plat]
        if not rows:
            continue
        if printed_any:
            _console.print()
        printed_any = True
        title = {
            "youtube": "YouTube",
            "instagram": "Instagram",
            "tiktok": "TikTok",
        }[plat]
        table = Table(
            title=f"[bold]{title}[/bold]",
            show_header=True, header_style="bold",
        )
        table.add_column("Handle")
        table.add_column("Group")
        table.add_column("Mode")
        table.add_column("Channel ID / Username")
        table.add_column("Last seen")
        for c in rows:
            # Mode only applies to YouTube channels; IG/TT rows print "—"
            # so the user isn't misled into thinking the field is wired
            # for those platforms in v0.17.
            mode_cell = (
                c.mode if plat == "youtube" else "[dim]—[/dim]"
            )
            table.add_row(
                c.handle or "—",
                c.group or "—",
                mode_cell,
                c.channel_id or "—",
                c.last_seen_published or "—",
            )
        _console.print(table)


@subscribes_group.command(name="edit")
def edit_cmd() -> None:
    """Open subscribes.toml in $EDITOR (vi/notepad fallback)."""
    SUBSCRIBES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SUBSCRIBES_PATH.exists():
        SUBSCRIBES_PATH.write_text("# subscribes — neurolearn v0.7\n",
                                   encoding="utf-8")

    editor = os.environ.get("EDITOR") or _default_editor()
    try:
        subprocess.run([editor, str(SUBSCRIBES_PATH)], check=True)
    except FileNotFoundError:
        _console.print(f"[red]Editor not found: {editor}. Set $EDITOR.[/red]")
        sys.exit(4)
    except subprocess.CalledProcessError as e:
        if e.returncode != 0:
            _console.print(f"[yellow]Editor exited with {e.returncode}[/yellow]")
    maybe_sync("on_write", SUBSCRIBES_PATH)   # `edit` writes past store.py — sync the manual edit


def _default_editor() -> str:
    """Cross-OS fallback editor."""
    if sys.platform == "win32":
        return "notepad"
    return "vi"


@subscribes_group.command(name="update")
@click.option("--group", default=None)
@click.option("--platform",
              type=click.Choice(["youtube", "instagram", "tiktok"]),
              default=None,
              help="Update only channels from this platform. Combines with "
                   "--group: --platform tiktok --group ai-research → only "
                   "TikTok channels in that group.")
@click.option("--days", type=int, default=None,
              help="Override stateful window: last N days (state NOT updated).")
@click.option("--since", default=None)
@click.option("--until", default=None)
@click.option("--match", default=None)
@click.option("--filter", "filter_text", default=None)
# --no-rss: deprecated no-op since v0.20. RSS was retired as the YouTube
# video source (it leaked livestreams and was empty for some channels);
# the /videos tab is now always used. Flag kept so old scripts don't break.
@click.option("--no-rss", is_flag=True, default=False)
@click.option("--yes", is_flag=True, default=False)
@click.option("--no-analyze", is_flag=True, default=False)
@click.option("--prompt", "prompt_inline", default=None)
@click.option("--prompt-file", "prompt_file", default=None,
              type=click.Path(exists=True, path_type=Path))
@click.option("--analyze-backend", "analyze_backend_opt",
              type=click.Choice(["groq", "gemini", "openai", "ollama"]),
              default=None,
              help="LLM backend for analyze. Default: ask once and remember "
                   "in config.toml (non-TTY → skip silently).")
@click.option("--filter-backend", "filter_backend_opt",
              type=click.Choice(["gemini", "groq", "openai", "ollama"]),
              default="gemini")
@click.option("--ollama-model", "ollama_model_opt", default=None)
@click.option("--ollama-host", "ollama_host_opt", default=None)
@click.option("--no-stdout", "no_stdout_opt", is_flag=True, default=False)
@click.option("--output-dir", "output_dir_opt", default=None)
@click.option("--backend",
              type=click.Choice([
                  "subtitles", "whisper-local", "gemini", "groq",
                  "openai", "deepgram", "assemblyai", "custom", "smart",
              ]), default=None)
@click.option("--whisper-model",
              type=click.Choice(["turbo", "large", "medium", "small", "distil"]),
              default=None)
@click.option("--language", default=None)
@click.option("--workers", "workers_opt", type=int, default=1)
@click.option(
    "--learn-into", "learn_into_memory", default="", metavar="MEMORY_NAME",
    help="After transcribe, ingest into the named memory file. v0.16.1+.",
)
@click.option(
    "--learn-claude-extract/--no-learn-claude-extract", "learn_claude_extract",
    default=None,
    help="With --learn-into: control the memory-diff mode. Auto-on when "
         "$CLAUDE_PLUGIN_ROOT is set. Use --no-learn-claude-extract to "
         "force the Groq path. v0.16.2+.",
)
# v0.17: shorts handling. The three boolean flags are mutex (manual check
# below — Click has no native mutex group). --shorts-cap stacks on any of
# them. All four are YouTube-only; IG/TT channels ignore the routing.
@click.option(
    "--shorts-only", "shorts_only_opt", is_flag=True, default=False,
    help="Per-call override: fetch only Shorts from YouTube channels in "
         "scope, ignoring stored per-channel mode. v0.17+. Mutex with "
         "--include-shorts / --no-shorts.",
)
@click.option(
    "--include-shorts", "include_shorts_opt", is_flag=True, default=False,
    help="Per-call override: fetch BOTH full videos and Shorts (deduped, "
         "sorted by publish date), ignoring stored per-channel mode. "
         "v0.17+. Mutex with --shorts-only / --no-shorts.",
)
@click.option(
    "--no-shorts", "no_shorts_opt", is_flag=True, default=False,
    help="Per-call override: skip Shorts on YouTube channels in scope, "
         "fetch only full videos via RSS. v0.17+. Mutex with --shorts-only "
         "/ --include-shorts.",
)
@click.option(
    "--shorts-cap", "shorts_cap_opt", type=int, default=None,
    help="Per-call override: cap the per-channel-per-update Shorts pull. "
         "0 = no cap. Default: cfg.shorts_max_per_update (5). v0.17+.",
)
def update_cmd(
    group, platform, days, since, until, match, filter_text, no_rss, yes,
    no_analyze, prompt_inline, prompt_file, analyze_backend_opt,
    filter_backend_opt, ollama_model_opt, ollama_host_opt, no_stdout_opt,
    output_dir_opt, learn_into_memory, learn_claude_extract,
    shorts_only_opt, include_shorts_opt, no_shorts_opt, shorts_cap_opt,
    **batch_passthrough,
) -> None:
    """Run subscribes update — fetch latest, filter, transcribe, analyze."""
    from datetime import date as _date
    from skills.neurolearn.analyze.backend_resolver import (
        resolve_analyze_backend,
    )

    # v0.17: mutex among the three shorts-routing flags (Click has no
    # native mutex group). Resolve to a single cli_override_mode string
    # before handing off to the pipeline.
    set_flags = sum([shorts_only_opt, include_shorts_opt, no_shorts_opt])
    if set_flags > 1:
        _console.print(
            "[red]--shorts-only, --include-shorts, and --no-shorts are "
            "mutually exclusive — pass at most one.[/red]"
        )
        sys.exit(2)
    if shorts_only_opt:
        cli_override_mode = "shorts-only"
    elif include_shorts_opt:
        cli_override_mode = "shorts-and-videos"
    elif no_shorts_opt:
        cli_override_mode = "videos-only"
    else:
        cli_override_mode = None

    # Resolve analyze backend first (flag > config > onboarding > skip).
    # `None` here means "don't analyze".
    resolved_analyze_backend = resolve_analyze_backend(
        cli_flag=analyze_backend_opt, no_analyze=no_analyze,
    )
    effective_no_analyze = no_analyze or resolved_analyze_backend is None

    if not effective_no_analyze:
        if bool(prompt_inline) == bool(prompt_file):
            _console.print(
                "[red]With analyze enabled — pass exactly one of[/red] "
                "--prompt / --prompt-file."
            )
            sys.exit(2)

    since_d = _date.fromisoformat(since) if since else None
    until_d = _date.fromisoformat(until) if until else None

    from skills.neurolearn.config import (
        get_api_key, load_config, CONFIG_PATH,
    )
    api_keys = {
        "gemini": get_api_key("gemini"),
        "groq": get_api_key("groq"),
        "openai": get_api_key("openai"),
        "ollama": None,
    }

    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    output_dir = output_dir_opt or (cfg.output_dir if cfg else "./transcripts")
    batch_opts = {k: v for k, v in batch_passthrough.items() if v is not None}

    # v0.17: resolve shorts cap — explicit flag > config > default 5.
    if shorts_cap_opt is not None:
        if shorts_cap_opt < 0:
            _console.print("[red]--shorts-cap must be >= 0 (0 = no cap).[/red]")
            sys.exit(2)
        effective_shorts_cap = shorts_cap_opt
    elif cfg is not None:
        effective_shorts_cap = cfg.shorts_max_per_update
    else:
        effective_shorts_cap = 5

    # Mid-flow safety net: if --platform targets IG/TT and we're in a TTY
    # but cookies aren't set, give the user one chance to set them via the
    # wizard before yt-dlp gets the "Unable to extract data" error.
    if platform in ("instagram", "tiktok") and sys.stdin.isatty() and cfg is not None:
        cookies_path = (
            cfg.instagram_cookies_file if platform == "instagram"
            else cfg.tiktok_cookies_file
        )
        if not cookies_path:
            if click.confirm(
                f"Cookies for {platform} are not configured — yt-dlp will "
                f"likely fail. Set them up now?",
                default=False,
            ):
                from skills.neurolearn.subscribes.cookies_onboarding import (
                    wizard,
                )
                wizard(platform)
                # Reload config so the just-saved file is picked up below.
                cfg = load_config(CONFIG_PATH)

    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, SubscribesError,
    )
    try:
        batch_dir_result = run_subscribes_update(
            subscribes_path=SUBSCRIBES_PATH,
            group=group, platform=platform,
            days=days, since=since_d, until=until_d,
            match=match, filter_text=filter_text,
            no_rss=no_rss, yes=yes, no_analyze=effective_no_analyze,
            prompt=prompt_inline, prompt_file=prompt_file,
            analyze_backend=resolved_analyze_backend or "gemini",
            filter_backend=filter_backend_opt,
            ollama_model=ollama_model_opt or DEFAULT_OLLAMA_MODEL,
            ollama_host=ollama_host_opt or DEFAULT_OLLAMA_HOST,
            no_stdout=no_stdout_opt,
            output_dir=output_dir,
            api_keys=api_keys,
            batch_opts=batch_opts,
            instagram_cookies_file=(
                cfg.instagram_cookies_file if cfg else ""
            ),
            tiktok_cookies_file=(
                cfg.tiktok_cookies_file if cfg else ""
            ),
            youtube_cookies_file=(
                cfg.youtube_cookies_file if cfg else ""
            ),
            cli_override_mode=cli_override_mode,
            shorts_cap=effective_shorts_cap,
        )
        # v0.16.1: --learn-into hook after a successful subscribes update
        if learn_into_memory and batch_dir_result is not None:
            from skills.neurolearn.memory.cli import run_learn_into_batch
            run_learn_into_batch(
                batch_dir=batch_dir_result,
                memory_name=learn_into_memory,
                cfg=cfg or load_config(CONFIG_PATH),
                auto_yes=bool(yes),
                claude_extract=learn_claude_extract,
            )
    except SubscribesError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)


@subscribes_group.group(name="cookies")
def cookies_group() -> None:
    """Manage Instagram / TikTok / YouTube cookies file (Netscape cookies.txt).

    Step-by-step setup:

      1. Install the open-source "Get cookies.txt LOCALLY" extension
         (Chrome / Firefox) — it does NOT phone home.
      2. Open the site (logged in) → click the extension → Export.
      3. Register the file:
           neurolearn subscribes cookies set instagram ~/Downloads/ig.txt
           neurolearn subscribes cookies set tiktok    ~/Downloads/tt.txt
           neurolearn subscribes cookies set youtube   ~/Downloads/yt.txt

    YouTube cookies (v0.10.7+) are used by the subtitles backend and
    by yt-dlp when YouTube rate-limits or geoblocks your IP — typical
    after >10 anonymous requests from the same address. Symptom:
    "Subtitles unavailable for this video (IpBlocked)".

    Files are copied to `~/.neurolearn/<platform>-cookies.txt` with
    mode 0600. To revoke, just delete that file or run
    `neurolearn subscribes cookies clear <platform>`.
    """


@cookies_group.command(name="set")
@click.argument("platform",
                type=click.Choice(["instagram", "tiktok", "youtube"]),
                required=False)
@click.argument("path",
                type=click.Path(exists=True, dir_okay=False),
                required=False)
@click.option(
    "--from-file", "from_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to cookies.txt — alias for the positional form, kept for "
         "consistency with `set-key --from-file`. Use this from Claude Code "
         "chat so the file path stays out of conversation logs.",
)
def cookies_set_cmd(platform: str | None, path: str | None, from_file: str | None) -> None:
    """Register a cookies.txt for PLATFORM (instagram / tiktok / youtube).

    Three equivalent forms:

      neurolearn subscribes cookies set                  # interactive wizard
      neurolearn subscribes cookies set instagram ~/ig.txt
      neurolearn subscribes cookies set instagram --from-file ~/ig.txt
    """
    from skills.neurolearn.subscribes.cookies_onboarding import (
        set_cookies_file, wizard,
    )

    # v0.15.0: --from-file takes precedence; if neither is set, fall
    # through to the interactive wizard (existing behavior).
    chosen_path = from_file or path

    if chosen_path is None:
        # Either missing platform too (full wizard) or only path missing
        # (still walk the wizard — it'll re-prompt for the path).
        if not wizard(platform):
            sys.exit(2)
        return

    try:
        dest = set_cookies_file(platform, chosen_path)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
    _console.print(
        f"[green]✓[/green] {platform} cookies saved to "
        f"[bold]{dest}[/bold] (mode 0600)\n"
        f"[dim]When yt-dlp returns login-required / empty response — that's "
        f"the signal cookies expired. Re-export and run `cookies set` again.[/dim]"
    )


@cookies_group.command(name="clear")
@click.argument("platform", type=click.Choice(["instagram", "tiktok", "youtube"]))
def cookies_clear_cmd(platform: str) -> None:
    """Remove the registered cookies file for PLATFORM."""
    from skills.neurolearn.config import (
        CONFIG_PATH, load_config, save_config, Config,
    )
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else Config()
    current = {
        "instagram": cfg.instagram_cookies_file,
        "tiktok": cfg.tiktok_cookies_file,
        "youtube": cfg.youtube_cookies_file,
    }[platform]
    if not current:
        _console.print(
            f"[yellow]No cookies file configured for {platform}.[/yellow]"
        )
        return
    p = Path(current).expanduser()
    if p.exists():
        try:
            p.unlink()
        except OSError as e:
            _console.print(f"[yellow]Could not remove {p}: {e}[/yellow]")
    if platform == "instagram":
        cfg.instagram_cookies_file = ""
    elif platform == "tiktok":
        cfg.tiktok_cookies_file = ""
    else:    # youtube
        cfg.youtube_cookies_file = ""
    save_config(cfg, CONFIG_PATH)
    _console.print(
        f"[green]✓[/green] {platform} cookies cleared. "
        f"Next run will go through anonymously."
    )


def _cookies_rows(cfg) -> list[tuple[str, str]]:
    """Helper used by `show` and `list` — keep them in sync."""
    return [
        ("instagram", cfg.instagram_cookies_file),
        ("tiktok",    cfg.tiktok_cookies_file),
        ("youtube",   cfg.youtube_cookies_file),
    ]


def _render_cookies_table(cfg) -> "Table":
    """Build the platform/path/status table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Platform")
    table.add_column("Cookies file")
    table.add_column("Status")
    for plat, p in _cookies_rows(cfg):
        if not p:
            status = "[dim]not set[/dim]"
        elif Path(p).expanduser().exists():
            status = "[green]ok[/green]"
        else:
            status = "[red]missing[/red]"
        table.add_row(plat, p or "—", status)
    return table


@cookies_group.command(name="show")
def cookies_show_cmd() -> None:
    """Show currently configured cookies files."""
    from skills.neurolearn.config import CONFIG_PATH, load_config
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    if cfg is None:
        _console.print("[dim]config.toml does not exist.[/dim]")
        return
    _console.print(_render_cookies_table(cfg))


@cookies_group.command(name="list")
def cookies_list_cmd() -> None:
    """Alias for `cookies show` — lists configured cookies per platform."""
    cookies_show_cmd.callback()


@subscribes_group.group(name="schedule")
def schedule_group() -> None:
    """Generate scheduler snippets (cron/launchd/systemd/Task Scheduler)."""


@schedule_group.command(name="install")
@click.option("--every", default="1h", show_default=True,
              help="Interval: 15m, 1h, 6h, 1d.")
@click.option("--platform", "platform_opt",
              type=click.Choice(["auto", "cron", "launchd",
                                  "systemd", "taskscheduler"]),
              default="auto", show_default=True)
@click.option("--prompt", default=None,
              help="Embedded prompt for the scheduled subscribes update.")
@click.option("--prompt-file", default=None,
              type=click.Path(exists=True, path_type=Path))
@click.option("--group", "group_opt", default=None)
def schedule_install_cmd(every, platform_opt, prompt, prompt_file, group_opt):
    """Print a schedule snippet + install instructions for the current OS."""
    try:
        seconds = parse_interval(every)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)

    plat = detect_platform() if platform_opt == "auto" else platform_opt

    argv = ["neurolearn", "subscribes", "update"]
    if prompt:
        argv.extend(["--prompt", prompt])
    if prompt_file:
        argv.extend(["--prompt-file", str(prompt_file)])
    if group_opt:
        argv.extend(["--group", group_opt])

    if plat == "launchd":
        label = "com.user.neurolearn-subscribes"
        plist = generate_launchd_plist(
            command_argv=argv, every_seconds=seconds, label=label,
        )
        path = f"~/Library/LaunchAgents/{label}.plist"
        _console.print(f"\n[bold]# Save to {path}[/bold]\n")
        click.echo(plist)
        _console.print(
            f"\n[bold]# Then run:[/bold]\n"
            f"  launchctl load {path}\n"
            f"\n[dim]# To remove later:[/dim]\n"
            f"  launchctl unload {path} && rm {path}\n"
        )
    elif plat == "cron":
        line = generate_cron_line(command_argv=argv, every_seconds=seconds)
        _console.print("\n[bold]# Add to crontab via `crontab -e`:[/bold]\n")
        click.echo(line)
        _console.print(
            "\n[dim]# To remove: `crontab -e` and delete the line above.[/dim]\n"
        )
    elif plat == "systemd":
        timer, service = generate_systemd_units(
            command_argv=argv, every_seconds=seconds, label="neurolearn-subscribes",
        )
        _console.print(
            "\n[bold]# Save timer to ~/.config/systemd/user/"
            "neurolearn-subscribes.timer:[/bold]\n"
        )
        click.echo(timer)
        _console.print(
            "\n[bold]# Save service to ~/.config/systemd/user/"
            "neurolearn-subscribes.service:[/bold]\n"
        )
        click.echo(service)
        _console.print(
            "\n[bold]# Then enable + start:[/bold]\n"
            "  systemctl --user daemon-reload\n"
            "  systemctl --user enable --now neurolearn-subscribes.timer\n"
        )
    elif plat == "taskscheduler":
        xml = generate_taskscheduler_xml(
            command_argv=argv, every_seconds=seconds,
            task_name="neurolearn-subscribes",
        )
        _console.print(
            "\n[bold]# Save XML to %TEMP%\\neurolearn-subscribes.xml:[/bold]\n"
        )
        click.echo(xml)
        _console.print(
            "\n[bold]# Then import via schtasks:[/bold]\n"
            "  schtasks /create /tn neurolearn-subscribes /xml "
            "%TEMP%\\neurolearn-subscribes.xml\n"
        )


@schedule_group.command(name="uninstall")
def schedule_uninstall_cmd():
    """Print uninstall instructions for all supported platforms."""
    _console.print(
        "[bold]# macOS (launchd):[/bold]\n"
        "  launchctl unload ~/Library/LaunchAgents/com.user.neurolearn-subscribes.plist\n"
        "  rm ~/Library/LaunchAgents/com.user.neurolearn-subscribes.plist\n\n"
        "[bold]# Linux (cron):[/bold]\n"
        "  crontab -e   # delete the neurolearn-subscribes line\n\n"
        "[bold]# Linux (systemd):[/bold]\n"
        "  systemctl --user disable --now neurolearn-subscribes.timer\n"
        "  rm ~/.config/systemd/user/neurolearn-subscribes.{timer,service}\n\n"
        "[bold]# Windows (Task Scheduler):[/bold]\n"
        "  schtasks /delete /tn neurolearn-subscribes /f\n"
    )
