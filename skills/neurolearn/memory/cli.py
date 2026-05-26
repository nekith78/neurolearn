"""Click subcommands for the `memory` command group.

Mounted on the top-level CLI from transcribe.py as `memory`:

    neurolearn memory create <name> [--description "..."]
    neurolearn memory list
    neurolearn memory show <name>
    neurolearn memory rename <old> <new>
    neurolearn memory delete <name>
    neurolearn memory learn <name> <URL_or_path> [<URL_or_path> ...]
"""
from __future__ import annotations

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
         "configured analyze_backend.",
)
@click.option(
    "--yes", "auto_yes", is_flag=True,
    help="Approve all candidates without prompting. Use with caution — "
         "the LLM occasionally proposes weak duplicates.",
)
def memory_learn_cmd(
    name: str, sources: tuple[str, ...], backend: str, auto_yes: bool,
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
    )

    _console.print(
        f"\n[green]✓ Learn complete[/green] for memory [bold]{name}[/bold]:\n"
        f"  transcripts processed: {summary['transcripts_processed']}\n"
        f"  candidates proposed:   {summary['candidates_proposed']}\n"
        f"  candidates approved:   {summary['candidates_approved']}\n"
        f"  total sources:         {summary['sources_total']}"
    )


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
