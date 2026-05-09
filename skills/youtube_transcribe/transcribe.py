"""CLI root + `transcribe` sub-command. Bare-URL form routes to `transcribe`.
The `batch` sub-command is added in Task 20B (registered into the same `cli` group)."""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from skills.youtube_transcribe.backends.base import BackendError, BackendNotConfigured
from skills.youtube_transcribe.config import (
    CONFIG_PATH,
    Config,
    load_config,
)
from skills.youtube_transcribe.pipeline import run_pipeline
from skills.youtube_transcribe.utils.downloader import (
    extract_youtube_video_id,
    is_url,
    is_youtube_url,
)
from skills.youtube_transcribe.utils.output_writer import (
    sanitize_filename,
    write_srt,
    write_txt_plain,
    write_txt_with_timestamps,
)
from skills.youtube_transcribe.utils.resolver import (
    ResolvedTarget,
    ResolverFilters,
    resolve,
)
from skills.youtube_transcribe.wizard import run_wizard

console = Console()

BACKEND_CHOICES = [
    "smart", "subtitles", "whisper-local",
    "gemini", "groq", "openai", "deepgram", "assemblyai", "custom",
]


class _BareURLGroup(click.Group):
    """If the first positional looks like a URL or existing file path,
    inject the implicit `transcribe` sub-command in front of it.

    Required to keep base spec §8 UX (`youtube-transcribe <URL>`)
    while exposing `batch` as a separate sub-command."""

    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands:
            first = args[0]
            looks_like_input = (
                is_url(first)
                or first.startswith("/") or first.startswith("./") or first.startswith("../")
                or (len(first) > 1 and first[1:3] == ":\\")    # Windows drive
                or Path(first).exists()
            )
            if looks_like_input:
                args = ["transcribe", *args]
        return super().resolve_command(ctx, args)


@click.group(cls=_BareURLGroup)
@click.version_option()
def cli() -> None:
    """youtube-transcribe — transcribe YouTube and local media via 8 backends.

    Use `transcribe <URL_or_path>` for one input.
    Use `batch <inputs...>` for multiple URLs / a channel / a playlist.
    """
    pass


@cli.command(name="transcribe")
@click.argument("audio_or_url")
@click.option("--backend", type=click.Choice(BACKEND_CHOICES), default=None,
              help="Backend to use (overrides config default).")
@click.option("--whisper-model", type=click.Choice(["turbo", "large", "medium", "small", "distil"]),
              default=None, help="Whisper model (only with --backend whisper-local).")
@click.option("--gemini-model", default=None)
@click.option("--groq-model", default=None)
@click.option("--deepgram-model", default=None)
@click.option("--assemblyai-model", default=None)
@click.option("--language", default=None, help="Language code (ru/en/...) or 'auto'.")
@click.option("--output-dir", default=None, help="Output directory.")
@click.option("--timestamps/--no-timestamps", default=None)
@click.option("--srt/--no-srt", default=None)
@click.option("--keep-audio/--delete-audio", default=None)
@click.option("--cookies-from-browser", "cookies_browser", default=None,
              type=click.Choice(["", "chrome", "firefox", "edge", "safari"]))
@click.option("--no-fast-path", is_flag=True, help="Disable subtitles fast-path in smart mode.")
@click.option("--device", default=None)
@click.option("--compute-type", default=None)
@click.option("--beam-size", type=int, default=None)
@click.option("--vad/--no-vad", default=None)
@click.option("--verbose", is_flag=True)
def transcribe_cmd(audio_or_url: str, **opts) -> None:
    """Transcribe a YouTube URL, supported video URL, or local audio/video file."""
    if not CONFIG_PATH.exists():
        run_wizard()

    cfg = load_config(CONFIG_PATH)
    cfg = _override_config(cfg, opts)
    if opts.get("no_fast_path"):
        cfg.fast_path_enabled = False

    targets = resolve([audio_or_url], None, ResolverFilters())
    if len(targets) != 1:
        # Bare URL/file should always resolve to exactly one target.
        # If user passed a channel here, they should use `batch` instead.
        console.print("[red]Этот URL развернулся в несколько видео.[/red] "
                      "Для каналов/плейлистов используй: youtube-transcribe batch <URL> --limit N")
        sys.exit(2)
    target = targets[0]

    output_dir = Path(opts.get("output_dir") or cfg.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = run_pipeline(target, cfg, backend_override=opts.get("backend"))
    except BackendNotConfigured as e:
        console.print(f"[red]Бэкенд не настроен:[/red] {e}")
        sys.exit(3)
    except BackendError as e:
        console.print(f"[red]Ошибка транскрипции:[/red] {e}")
        sys.exit(4)

    base_name = sanitize_filename(_derive_basename(target))
    txt_path = output_dir / f"{base_name}.txt"
    srt_path = output_dir / f"{base_name}.srt"

    timestamps = cfg.timestamps if opts.get("timestamps") is None else opts["timestamps"]
    write_srt_flag = cfg.srt if opts.get("srt") is None else opts["srt"]

    if timestamps:
        write_txt_with_timestamps(result.segments, txt_path)
    else:
        write_txt_plain(result.segments, txt_path)
    if write_srt_flag:
        write_srt(result.segments, srt_path)

    console.print(f"[green]✓[/green] {result.backend_name} | "
                  f"язык={result.language_detected or 'auto'} | "
                  f"длительность={result.duration_seconds:.1f}s")
    console.print(f"  [bold]{txt_path}[/bold]")
    if write_srt_flag:
        console.print(f"  [bold]{srt_path}[/bold]")


def _derive_basename(target: ResolvedTarget) -> str:
    if is_youtube_url(target.url):
        vid = extract_youtube_video_id(target.url)
        return f"yt_{vid}" if vid else "url_transcript"
    if is_url(target.url):
        return "url_transcript"
    return Path(target.url).stem


def _override_config(cfg: Config, opts: dict) -> Config:
    """Apply CLI overrides to a Config copy."""
    if opts.get("whisper_model"): cfg.whisper_model = opts["whisper_model"]
    if opts.get("gemini_model"): cfg.gemini_model = opts["gemini_model"]
    if opts.get("groq_model"): cfg.groq_model = opts["groq_model"]
    if opts.get("deepgram_model"): cfg.deepgram_model = opts["deepgram_model"]
    if opts.get("assemblyai_model"): cfg.assemblyai_model = opts["assemblyai_model"]
    if opts.get("device"): cfg.whisper_device = opts["device"]
    if opts.get("compute_type"): cfg.whisper_compute_type = opts["compute_type"]
    if opts.get("beam_size"): cfg.beam_size = opts["beam_size"]
    if opts.get("vad") is not None: cfg.vad = opts["vad"]
    if opts.get("cookies_browser") is not None: cfg.cookies_browser = opts["cookies_browser"]
    if opts.get("keep_audio") is not None: cfg.keep_audio = opts["keep_audio"]
    return cfg


# ---------------------------------------------------------------------------
# Task 20B stub — batch sub-command placeholder.
# Full implementation (Resolver loop, combined.md) added in Task 20B.
# ---------------------------------------------------------------------------
@cli.command(name="batch")
@click.argument("inputs", nargs=-1, required=True)
@click.pass_context
def batch_cmd(ctx: click.Context, inputs: tuple) -> None:
    """Transcribe multiple URLs, a channel, or a playlist. [Added in Task 20B]"""
    console.print("[yellow]batch sub-command will be fully implemented in Task 20B.[/yellow]")
    sys.exit(1)


# Task 21 will register `config` sub-group.
# Keeping that explicit in __all__ to make the module-level extension contract obvious.
__all__ = ["cli", "transcribe_cmd", "batch_cmd"]


if __name__ == "__main__":
    cli()
