"""First-run interactive setup wizard.

Invoked when ``~/.neurolearn/config.toml`` does not exist (first run)
or explicitly via ``neurolearn config wizard``.
"""
from __future__ import annotations

from skills.neurolearn.utils.console import make_console
from rich.panel import Panel
from rich.prompt import Prompt

from skills.neurolearn.config import (
    CONFIG_PATH,
    ENV_PATH,
    load_config,
    save_config,
    set_api_key,
)
from skills.neurolearn.utils.platform_detect import detect_platform

# ---------------------------------------------------------------------------
# Menu data
# ---------------------------------------------------------------------------

_BACKEND_CHOICES = [
    ("smart",         "Subtitles fast-path → Groq (fast) → whisper-local fallback. RECOMMENDED."),
    ("groq",          "Groq Whisper-large-v3-turbo — fastest cloud backend (~12 s per 17-min video).  [free tier 8 h/day]  Key required."),
    ("whisper-local", "Local Whisper — offline, private, no API key.  [free]  Slower than groq."),
    ("subtitles",     "YouTube subtitles only. Instant, YouTube-only.  [free, no API]"),
    ("gemini",        "Google AI Studio — also handles vision/analyze tasks.  [free tier ~1500/day]  Key required.  Audio backend has known +63% timestamp drift; prefer groq for transcription."),
    ("openai",        "OpenAI Whisper API.  [paid ~$0.006/min]  Key required."),
    ("deepgram",      "Deepgram Nova-3.  [starter credit $200 ≈ 750 h]  Key required."),
    ("assemblyai",    "AssemblyAI — good for long interviews.  [free tier ~5 h/month]  Key required."),
    ("custom",        "OpenAI-compatible API. For advanced setups.  [depends on provider]"),
]
# NOTE: free-tier quotas above reflect the state in May 2026.
# Providers change them; check the key-issuance page for current limits.

# Map backend name → URL where the user can get an API key
_KEY_GUIDE: dict[str, str] = {
    "gemini":     "https://aistudio.google.com/apikey",
    "groq":       "https://console.groq.com/keys",
    "openai":     "https://platform.openai.com/api-keys",
    "deepgram":   "https://console.deepgram.com/",
    "assemblyai": "https://www.assemblyai.com/dashboard/signup",
    "custom":     "(specify your base URL and key in config.toml)",
}

# Backends that require an API key
_CLOUD_BACKENDS = set(_KEY_GUIDE.keys())

# Choices offered for smart-mode fallback. v0.11.0: groq is the default
# recommendation (1) since it's empirically 4-8x faster than whisper-local
# on a 17-min video and has accurate timestamps (unlike gemini).
_FALLBACK_OPTIONS: dict[str, str] = {
    "1": "groq",
    "2": "whisper-local",
    "3": "gemini",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the interactive first-run setup wizard.

    Detects hardware, shows a numbered menu of backend choices, optionally
    asks for an API key (cloud backends), and saves config + .env.
    """
    console = make_console()

    # --- Greeting + hardware detection ---
    info = detect_platform()
    vram_str = f"{info.vram_mb} MiB" if info.vram_mb is not None else "n/a"
    console.print(Panel.fit(
        f"[bold]neurolearn — first-run setup[/bold]\n\n"
        f"Detected: [cyan]{info.label}[/cyan]  "
        f"(device={info.device}, VRAM={vram_str})\n"
        f"Recommendation: [green]smart[/green] — subtitles fast-path → Groq → whisper-local.\n"
        f"Groq Whisper-large-v3-turbo gives ~12 s per 17-min video with accurate\n"
        f"timestamps. Free tier 8 hours/day; key from https://console.groq.com/keys.\n\n"
        f"[dim]Cloud backends (groq, gemini, openai, deepgram, assemblyai, custom)\n"
        f"send audio to the provider's servers. Make sure that's acceptable.[/dim]",
        title="neurolearn",
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
            "  1) groq (recommended — fastest, free 8 h/day)  2) whisper-local  3) gemini[/dim]"
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
            console.print("[dim]Skipped. Add the key later to ~/.neurolearn/.env[/dim]")

    # --- Done ---
    console.print(f"\n[green]✓ Configured.[/green]  Default backend: [bold]{backend}[/bold]")
    console.print(
        "Change choice:    [cyan]neurolearn config wizard[/cyan]\n"
        "One-off use:      [cyan]neurolearn <URL> --backend gemini[/cyan]\n"
    )
