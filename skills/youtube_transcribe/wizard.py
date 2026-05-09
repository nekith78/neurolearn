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
    ("whisper-local", "Локальный Whisper. Оффлайн, приватно, лучшее качество."),
    ("smart",         "Субтитры YouTube → fallback. Быстро и надёжно."),
    ("subtitles",     "Только субтитры YouTube. Мгновенно, среднее качество, только YouTube."),
    ("gemini",        "Google AI Studio. Бесплатный free tier. Нужен ключ."),
    ("groq",          "Groq Whisper API. Самый быстрый облачный. Free tier. Нужен ключ."),
    ("openai",        "OpenAI Whisper API. Платно (~$0.006/мин). Нужен ключ."),
    ("deepgram",      "Deepgram Nova-3. $200 стартовый кредит. Нужен ключ."),
    ("assemblyai",    "AssemblyAI. Free tier. Хорош для длинных интервью. Нужен ключ."),
    ("custom",        "OpenAI-совместимый API. Для продвинутых."),
]

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
        f"[bold]youtube-transcribe — первая настройка[/bold]\n\n"
        f"Обнаружил: [cyan]{info.label}[/cyan]  "
        f"(device={info.device}, VRAM={vram_str})\n"
        f"Рекомендация: [green]whisper-local[/green] — оффлайн, приватно, лучшее качество\n\n"
        f"[dim]Облачные бэкенды (gemini, groq, openai, deepgram, assemblyai, custom)\n"
        f"отправляют аудио на серверы провайдера. Убедись, что это тебя устраивает.[/dim]",
        title="youtube-transcribe",
    ))

    # --- Backend menu ---
    console.print("\nКакой движок использовать по умолчанию?\n")
    for idx, (name, desc) in enumerate(_BACKEND_CHOICES, start=1):
        star = " [yellow]⭐[/yellow]" if idx == 1 else ""
        console.print(f"  [cyan]{idx})[/cyan] [bold]{name}[/bold]{star} — {desc}")

    choice_str = Prompt.ask(
        "\nНомер варианта",
        choices=[str(i) for i in range(1, len(_BACKEND_CHOICES) + 1)],
        default="1",
    )
    backend = _BACKEND_CHOICES[int(choice_str) - 1][0]

    # --- Load / mutate / save config ---
    cfg = load_config(CONFIG_PATH)
    cfg.default_backend = backend  # type: ignore[assignment]

    if backend == "smart":
        console.print(
            "\n[dim]Какой движок использовать как fallback в smart-режиме?\n"
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
            f"\n[yellow]Нужен API-ключ.[/yellow]  Получить: [link={guide}]{guide}[/link]"
        )
        key = Prompt.ask(
            f"Введи {backend.upper()}_API_KEY  (Enter — пропустить)",
            default="",
        )
        if key.strip():
            set_api_key(backend, key.strip(), env_path=ENV_PATH)
            console.print(f"[green]✓[/green] Ключ сохранён в {ENV_PATH}")
        else:
            console.print("[dim]Пропущено. Добавь ключ позже в ~/.youtube-transcribe/.env[/dim]")

    # --- Done ---
    console.print(f"\n[green]✓ Настроено.[/green]  Дефолтный движок: [bold]{backend}[/bold]")
    console.print(
        "Поменять выбор:          [cyan]youtube-transcribe config wizard[/cyan]\n"
        "Использовать разово:     [cyan]youtube-transcribe <URL> --backend gemini[/cyan]\n"
    )
