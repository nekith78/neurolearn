"""Click subcommands for the `memory` command group.

Mounted on the top-level CLI from transcribe.py as `memory`:

    neurolearn memory create <name> [--description "..."]
    neurolearn memory list
    neurolearn memory show <name>
    neurolearn memory rename <old> <new>
    neurolearn memory delete <name>
    neurolearn memory learn <name> <URL_or_path> [<URL_or_path> ...]
    neurolearn memory append-facts <name> --from-file <approved.json>

v0.16.2: `memory learn` inside Claude Code (`CLAUDE_PLUGIN_ROOT` set) no
longer calls Groq — it writes a briefing for Claude in chat, then the
user runs `memory append-facts` to persist Claude-approved candidates.
Override with `--no-claude-extract` to force the Groq path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skills.neurolearn.config import CONFIG_PATH, load_config
from skills.neurolearn.memory.store import (
    MemoryFile, delete_memory, list_memories, memory_path,
    read_memory, rename_memory, write_memory,
)


_console = Console()


@click.group(name="memory")
def memory_group() -> None:
    """Manage memory files — curated knowledge bases that grow over time."""


@memory_group.command(name="create")
@click.argument("name")
@click.option(
    "--description", "-d", default="",
    help="Short description of what belongs in this memory. If omitted, "
         "neurolearn will auto-generate one after the first `learn` run."
)
def memory_create_cmd(name: str, description: str) -> None:
    """Create a new memory file."""
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    p = memory_path(name, cfg=cfg)
    if p.exists():
        _console.print(f"[yellow]Memory already exists:[/yellow] {p}")
        sys.exit(2)
    memory = MemoryFile(name=name, description=description.strip())
    write_memory(memory, cfg=cfg)
    _console.print(
        f"[green]✓[/green] Created memory [bold]{memory.name}[/bold] at {p}\n"
        + (f"  Description: {description.strip()}\n" if description.strip()
           else "  No description set — will be auto-generated on first `learn`.\n")
        + f"  Use: [cyan]neurolearn memory learn {memory.name} <URL>[/cyan] to add knowledge."
    )


@memory_group.command(name="list")
def memory_list_cmd() -> None:
    """List all memory files."""
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    memories = list_memories(cfg=cfg)
    if not memories:
        _console.print(
            "[dim]No memory files yet. Create one with:[/dim]\n"
            "  [cyan]neurolearn memory create <name>[/cyan]"
        )
        return
    table = Table(title="Memory files")
    table.add_column("Name", style="bold")
    table.add_column("Sources", justify="right")
    table.add_column("Last updated", style="dim")
    table.add_column("Description", overflow="fold")
    for m in memories:
        desc = (m.description or "[dim](pending — will auto-generate on next learn)[/dim]").strip()
        if len(desc) > 80:
            desc = desc[:77] + "…"
        last = m.last_updated[:10] if m.last_updated else "—"
        table.add_row(m.name, str(m.sources), last, desc)
    _console.print(table)


@memory_group.command(name="show")
@click.argument("name")
def memory_show_cmd(name: str) -> None:
    """Print the full memory file."""
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    try:
        m = read_memory(name, cfg=cfg)
    except FileNotFoundError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(3)
    p = memory_path(name, cfg=cfg)
    _console.print(f"[dim]{p}[/dim]\n")
    _console.print(Panel.fit(
        f"[bold]{m.name}[/bold]  "
        f"[dim]({m.sources} sources, last_updated {m.last_updated[:19]})[/dim]\n\n"
        f"{m.description or '[dim](no description yet)[/dim]'}",
        title="Memory metadata",
    ))
    _console.print()
    if m.body.strip():
        _console.print(m.body)
    else:
        _console.print("[dim](empty body — run `memory learn` to add facts)[/dim]")


@memory_group.command(name="rename")
@click.argument("old")
@click.argument("new")
def memory_rename_cmd(old: str, new: str) -> None:
    """Rename a memory file. Updates both the on-disk filename and
    the `name:` field inside the file's frontmatter."""
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    try:
        new_path = rename_memory(old, new, cfg=cfg)
    except FileNotFoundError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(3)
    except FileExistsError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
    _console.print(f"[green]✓[/green] Renamed → {new_path}")


@memory_group.command(name="delete")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def memory_delete_cmd(name: str, yes: bool) -> None:
    """Delete a memory file. Irreversible."""
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    p = memory_path(name, cfg=cfg)
    if not p.exists():
        _console.print(f"[red]Memory not found:[/red] {p}")
        sys.exit(3)
    if not yes:
        if not sys.stdin.isatty():
            _console.print(
                f"[red]Refusing to delete {p} without --yes in non-TTY context.[/red]"
            )
            sys.exit(2)
        confirm = click.confirm(
            f"Delete memory '{name}' ({p})? This cannot be undone.",
            default=False,
        )
        if not confirm:
            _console.print("[dim]Cancelled.[/dim]")
            return
    delete_memory(name, cfg=cfg)
    _console.print(f"[green]✓[/green] Deleted {p}")


@memory_group.command(name="learn")
@click.argument("name")
@click.argument("sources", nargs=-1, required=True)
@click.option(
    "--backend",
    default="",
    help="LLM backend for the diff extraction. Defaults to your "
         "configured analyze_backend. Ignored in Claude-extract mode.",
)
@click.option(
    "--yes", "auto_yes", is_flag=True,
    help="Approve all candidates without prompting. Use with caution — "
         "the LLM occasionally proposes weak duplicates.",
)
@click.option(
    "--claude-extract/--no-claude-extract", "claude_extract", default=None,
    help="When set, write a briefing for Claude in chat to do the diff "
         "natively and skip the external LLM call. Auto-on when "
         "$CLAUDE_PLUGIN_ROOT is set (inside Claude Code).",
)
def memory_learn_cmd(
    name: str, sources: tuple[str, ...], backend: str, auto_yes: bool,
    claude_extract: bool | None,
) -> None:
    """Ingest one or more transcripts into a memory.

    SOURCES can be:
      - YouTube / Instagram / TikTok URLs (will be transcribed)
      - Paths to existing .txt / .srt transcript files
      - Paths to a batch directory (combined.md will be read)
    """
    from skills.neurolearn.memory.learn import learn, TranscriptInput
    from skills.neurolearn.utils.downloader import is_url

    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    if cfg is None:
        _console.print("[red]No config found — run `neurolearn config wizard` first.[/red]")
        sys.exit(2)

    chosen_backend = backend or cfg.analyze_backend or "groq"

    # Build TranscriptInput list from the source arguments
    transcripts: list[TranscriptInput] = []
    for src in sources:
        if is_url(src):
            # Need to transcribe first
            t = _transcribe_url_for_learn(src, cfg=cfg)
            if t is not None:
                transcripts.append(t)
        else:
            p = Path(src).expanduser().resolve()
            t = _load_transcript_from_path(p)
            if t is not None:
                transcripts.append(t)

    if not transcripts:
        _console.print("[red]No transcripts produced — nothing to learn.[/red]")
        sys.exit(2)

    summary = learn(
        memory_name=name,
        transcripts=transcripts,
        analyze_backend=chosen_backend,
        cfg=cfg,
        auto_yes=auto_yes,
        claude_extract=claude_extract,
    )

    if summary.get("mode") == "claude_code_extract_only":
        _console.print(
            f"\n[bold cyan]→ Claude-extract mode[/bold cyan] for memory "
            f"[bold]{name}[/bold]:\n"
            f"  transcripts assembled: {summary['transcripts_processed']}\n"
            f"  briefing:              {summary['briefing_path']}\n\n"
            f"[yellow]Next:[/yellow] Claude reads the briefing in chat, "
            f"proposes candidates, gets your y/n on each, writes "
            f"{summary['approved_json_path']!r}, then either Claude or "
            f"you run:\n"
            f"  [cyan]neurolearn memory append-facts {name} "
            f"--from-file {summary['approved_json_path']}[/cyan]"
        )
        return

    _console.print(
        f"\n[green]✓ Learn complete[/green] for memory [bold]{name}[/bold]:\n"
        f"  transcripts processed: {summary['transcripts_processed']}\n"
        f"  candidates proposed:   {summary['candidates_proposed']}\n"
        f"  candidates approved:   {summary['candidates_approved']}\n"
        f"  total sources:         {summary['sources_total']}"
    )


@memory_group.command(name="append-facts")
@click.argument("name")
@click.option(
    "--from-file", "from_file", required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a Claude-produced approved.json with a 'candidates' list.",
)
@click.option(
    "--no-auto-description", "no_auto_description", is_flag=True,
    help="Skip the automatic description generation even if the memory "
         "has no description yet. Useful in non-interactive scripts.",
)
def memory_append_facts_cmd(
    name: str, from_file: str, no_auto_description: bool,
) -> None:
    """Append Claude-approved facts to a memory (no LLM call).

    The companion command to `memory learn` in Claude-extract mode:
    Claude in chat builds the candidates JSON after user approval, then
    this command persists them to disk. Pure write — no provider API
    call, no diff, no inference.
    """
    from skills.neurolearn.memory.learn import append_approved_from_file

    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    approved_path = Path(from_file).expanduser().resolve()

    try:
        summary = append_approved_from_file(
            memory_name=name,
            approved_path=approved_path,
            cfg=cfg,
            autogenerate_description=not no_auto_description,
            analyze_backend=(cfg.analyze_backend if cfg else None),
        )
    except FileNotFoundError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(3)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)

    _console.print(
        f"\n[green]✓ Appended[/green] to memory [bold]{name}[/bold]:\n"
        f"  candidates in file:   {summary['candidates_in_file']}\n"
        f"  facts appended:       {summary['facts_appended']}\n"
        f"  new sources counted:  {summary['sources_added']}\n"
        f"  total sources:        {summary['sources_total']}"
    )


# ---------------------------------------------------------------------------
# Public API: called by batch / research / subscribes update with --learn-into
# ---------------------------------------------------------------------------

def run_learn_into_batch(
    *,
    batch_dir: Path,
    memory_name: str,
    cfg,
    auto_yes: bool = False,
    claude_extract: bool | None = None,
) -> None:
    """Hook called from batch / research / subscribes update after they
    finish writing combined.md + videos/*.txt. Builds TranscriptInput
    from each transcribed video and runs the standard learn flow.

    Silently skips when batch_dir doesn't exist (transcribe failed) or
    has no usable transcripts.

    v0.16.2: when `claude_extract is None` we honor the
    CLAUDE_PLUGIN_ROOT env var auto-detect inside learn(); when True/False
    we force that mode. In Claude-extract mode the briefing is written
    INSIDE batch_dir (so it ships alongside the transcripts) rather than
    in the default `~/.neurolearn/memories/.pending/` location.
    """
    from skills.neurolearn.memory.learn import learn, TranscriptInput

    if batch_dir is None or not batch_dir.exists():
        _console.print(
            f"[dim]--learn-into skipped: no batch dir produced.[/dim]"
        )
        return

    # Prefer per-video transcripts so the LLM sees one transcript at a
    # time (gives cleaner per-video facts). combined.md works but loses
    # per-video boundaries.
    transcripts: list[TranscriptInput] = []
    videos_dir = batch_dir / "videos"
    if videos_dir.exists():
        for txt in sorted(videos_dir.glob("*.txt")):
            # Recover URL from manifest.json if possible
            url = _video_url_from_manifest(batch_dir, txt.stem) or txt.stem
            transcripts.append(TranscriptInput(
                url=url,
                title=txt.stem,
                text=txt.read_text(encoding="utf-8"),
            ))

    if not transcripts:
        # Fall back to combined.md (single batch-level transcript)
        combined = batch_dir / "combined.md"
        if combined.exists():
            transcripts.append(TranscriptInput(
                url=str(batch_dir),
                title=batch_dir.name,
                text=combined.read_text(encoding="utf-8"),
            ))

    if not transcripts:
        _console.print(
            f"[yellow]--learn-into {memory_name!r}: no transcripts found in "
            f"{batch_dir} — skipping.[/yellow]"
        )
        return

    use_claude_extract = (
        claude_extract
        if claude_extract is not None
        else bool(os.environ.get("CLAUDE_PLUGIN_ROOT"))
    )
    pending_dir = (batch_dir / "learn" / memory_name) if use_claude_extract else None

    if use_claude_extract:
        _console.print(
            f"\n[bold cyan]→ --learn-into {memory_name}[/bold cyan] "
            f"(Claude-extract mode): writing briefing for "
            f"{len(transcripts)} transcript(s) — no external LLM call."
        )
    else:
        _console.print(
            f"\n[bold]→ --learn-into {memory_name}[/bold]: "
            f"ingesting {len(transcripts)} transcript(s) "
            f"({'auto-approving via --yes' if auto_yes else 'interactive approval'})..."
        )

    try:
        summary = learn(
            memory_name=memory_name,
            transcripts=transcripts,
            analyze_backend=cfg.analyze_backend or "groq",
            cfg=cfg,
            auto_yes=auto_yes,
            claude_extract=claude_extract,
            pending_dir=pending_dir,
        )
    except Exception as e:
        _console.print(
            f"[red]--learn-into failed:[/red] {type(e).__name__}: {e}\n"
            f"[dim]Transcripts are still in {batch_dir}; "
            f"run `neurolearn memory learn {memory_name} {batch_dir}` manually.[/dim]"
        )
        return

    if summary.get("mode") == "claude_code_extract_only":
        _console.print(
            f"[green]✓ briefing ready[/green] for memory "
            f"[bold]{memory_name}[/bold]:\n"
            f"  briefing:      {summary['briefing_path']}\n"
            f"  approved.json: {summary['approved_json_path']}\n\n"
            f"[yellow]Next:[/yellow] Claude reads the briefing, asks you "
            f"y/n on each candidate, writes approved.json, then run "
            f"[cyan]neurolearn memory append-facts {memory_name} "
            f"--from-file {summary['approved_json_path']}[/cyan]."
        )
        return

    _console.print(
        f"[green]✓ memory {memory_name}[/green]: "
        f"{summary['candidates_approved']}/{summary['candidates_proposed']} "
        f"approved (total sources: {summary['sources_total']})"
    )


def _video_url_from_manifest(batch_dir: Path, video_stem: str) -> str | None:
    """Look up the URL for a video file via manifest.json. The stem
    typically encodes the video_id at the end (e.g. `01_Title_aBcDe`),
    and the manifest has the full URL per entry."""
    mf = batch_dir / "manifest.json"
    if not mf.exists():
        return None
    try:
        import json
        data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return None
    # Match by video_id suffix in the filename
    for video in data.get("videos", []):
        vid = video.get("video_id") or ""
        if vid and vid in video_stem:
            return video.get("url")
    # Or by title match
    for video in data.get("videos", []):
        title = video.get("title") or ""
        if title and title.replace(" ", "_") in video_stem:
            return video.get("url")
    return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _transcribe_url_for_learn(url: str, *, cfg) -> "TranscriptInput | None":
    """Transcribe a URL via the main pipeline, then wrap the result in a
    TranscriptInput. Reuses the smart cascade so subtitles fast-path
    happens automatically when possible."""
    from skills.neurolearn.memory.learn import TranscriptInput
    from skills.neurolearn.backends.factory import run_smart

    try:
        result = run_smart(url, cfg, language="auto")
    except Exception as e:
        _console.print(f"[red]Failed to transcribe {url}: {e}[/red]")
        return None
    return TranscriptInput(
        url=url,
        title=getattr(result, "title", "") or url,
        text=result.text,
    )


def _load_transcript_from_path(p: Path) -> "TranscriptInput | None":
    """Load an existing transcript file. Supports .txt, .srt, and
    batch dirs (looks for combined.md or videos/*.txt)."""
    from skills.neurolearn.memory.learn import TranscriptInput
    if not p.exists():
        _console.print(f"[red]Path not found: {p}[/red]")
        return None
    if p.is_dir():
        combined = p / "combined.md"
        if combined.exists():
            return TranscriptInput(
                url=str(p), title=p.name, text=combined.read_text(encoding="utf-8"),
            )
        # Fall back to concatenating videos/*.txt
        txts = sorted(p.glob("videos/*.txt"))
        if not txts:
            _console.print(
                f"[red]No combined.md or videos/*.txt in {p}[/red]"
            )
            return None
        body = "\n\n".join(t.read_text(encoding="utf-8") for t in txts)
        return TranscriptInput(url=str(p), title=p.name, text=body)
    if p.suffix.lower() in (".txt", ".md", ".srt", ".json"):
        return TranscriptInput(url=str(p), title=p.stem, text=p.read_text(encoding="utf-8"))
    _console.print(f"[red]Unsupported file extension: {p.suffix}[/red]")
    return None
