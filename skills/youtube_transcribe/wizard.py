"""First-run interactive setup wizard.

Invoked when ``~/.youtube-transcribe/config.toml`` does not exist (first run)
or explicitly via ``youtube-transcribe config wizard``.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from skills.youtube_transcribe.config import (
    CONFIG_PATH,
    ENV_PATH,
    load_config,
    save_config,
    set_api_key,
)
from skills.youtube_transcribe.utils.platform_detect import detect_platform

# ---------------------------------------------------------------------------
# Menu data
# ---------------------------------------------------------------------------

_BACKEND_CHOICES = [
    ("whisper-local", "Локальный Whisper — оффлайн, приватно, лучшее качество.  [бесплатно]"),
    ("smart",         "Субтитры YouTube → fallback. Быстро и надёжно."),
    ("subtitles",     "Только субтитры YouTube. Мгновенно, только YouTube.  [бесплатно, без API]"),
    ("gemini",        "Google AI Studio.  [free tier ~часы/день]  Нужен ключ."),
    ("groq",          "Groq Whisper API — самый быстрый облачный.  [free tier ~8 ч/день]  Нужен ключ."),
    ("openai",        "OpenAI Whisper API.  [платно ~$0.006/мин]  Нужен ключ."),
    ("deepgram",      "Deepgram Nova-3.  [starter-кредит $200 ≈ 750 ч]  Нужен ключ."),
    ("assemblyai",    "AssemblyAI — хорош для длинных интервью.  [free tier ~5 ч/мес]  Нужен ключ."),
    ("custom",        "OpenAI-совместимый API. Для продвинутых.  [зависит от провайдера]"),
]
# NOTE: free-tier quotas above — ориентир на момент Jan 2026.
# Реальные числа меняются провайдером; точные лимиты — на странице получения ключа.

# Map backend name → URL where the user can get an API key
_KEY_GUIDE: dict[str, str] = {
    "gemini":     "https://aistudio.google.com/apikey",
    "groq":       "https://console.groq.com/keys",
    "openai":     "https://platform.openai.com/api-keys",
    "deepgram":   "https://console.deepgram.com/",
    "assemblyai": "https://www.assemblyai.com/dashboard/signup",
    "custom":     "(укажи свой base URL и ключ в config.toml)",
}

# Backends that require an API key
_CLOUD_BACKENDS = set(_KEY_GUIDE.keys())

# Choices offered for smart-mode fallback
_FALLBACK_OPTIONS: dict[str, str] = {
    "1": "whisper-local",
    "2": "gemini",
    "3": "groq",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the interactive first-run setup wizard.

    Detects hardware, shows a numbered menu of backend choices, optionally
    asks for an API key (cloud backends), and saves config + .env.
    """
    console = Console()

    # --- Greeting + hardware detection ---
    info = detect_platform()
    vram_str = f"{info.vram_mb} MiB" if info.vram_mb is not None else "n/a"
    console.print(Panel.fit(
        f"[bold]youtube-transcribe — first-run setup[/bold]\n\n"
        f"Detected: [cyan]{info.label}[/cyan]  "
        f"(device={info.device}, VRAM={vram_str})\n"
        f"Recommendation: [green]whisper-local[/green] — offline, private, best quality\n\n"
        f"[dim]Cloud backends (gemini, groq, openai, deepgram, assemblyai, custom)\n"
        f"send audio to the provider's servers. Make sure that's acceptable.[/dim]",
        title="youtube-transcribe",
    ))

    # --- Backend menu ---
    console.print("\nWhich backend to use by default?\n")
    for idx, (name, desc) in enumerate(_BACKEND_CHOICES, start=1):
        star = " [yellow]⭐[/yellow]" if idx == 1 else ""
        console.print(f"  [cyan]{idx})[/cyan] [bold]{name}[/bold]{star} — {desc}")

    choice_str = Prompt.ask(
        "\nChoice number",
        choices=[str(i) for i in range(1, len(_BACKEND_CHOICES) + 1)],
        default="1",
    )
    backend = _BACKEND_CHOICES[int(choice_str) - 1][0]

    # --- Load / mutate / save config ---
    cfg = load_config(CONFIG_PATH)
    cfg.default_backend = backend  # type: ignore[assignment]

    if backend == "smart":
        console.print(
            "\n[dim]Which backend to use as fallback in smart mode?\n"
            "  1) whisper-local  2) gemini  3) groq[/dim]"
        )
        fb_choice = Prompt.ask(
            "Fallback",
            choices=list(_FALLBACK_OPTIONS.keys()),
            default="1",
        )
        cfg.fallback_backend = _FALLBACK_OPTIONS[fb_choice]  # type: ignore[assignment]

    save_config(cfg, CONFIG_PATH)

    # --- API key prompt for cloud backends ---
    if backend in _CLOUD_BACKENDS:
        guide = _KEY_GUIDE[backend]
        console.print(
            f"\n[yellow]API key required.[/yellow]  Get one at: [link={guide}]{guide}[/link]"
        )
        key = Prompt.ask(
            f"Enter {backend.upper()}_API_KEY  (Enter — skip)",
            default="",
            password=True,
        )
        if key.strip():
            set_api_key(backend, key.strip(), env_path=ENV_PATH)
            console.print(f"[green]✓[/green] Key saved to {ENV_PATH}")
        else:
            console.print("[dim]Skipped. Add the key later to ~/.youtube-transcribe/.env[/dim]")

    # --- Done ---
    console.print(f"\n[green]✓ Configured.[/green]  Default backend: [bold]{backend}[/bold]")
    console.print(
        "Change choice:    [cyan]youtube-transcribe config wizard[/cyan]\n"
        "One-off use:      [cyan]youtube-transcribe <URL> --backend gemini[/cyan]\n"
    )
