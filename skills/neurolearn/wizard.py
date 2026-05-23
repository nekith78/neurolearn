"""First-run interactive setup wizard.

v0.12.1: rebuilt as a 3-stage flow (audio + vision + analyze) with
tier-aware branching. Free-tier users see only the constrained
recommended cascade; paid-tier users unlock model-override prompts.

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
# Menu data — Stage 1: audio backend
# ---------------------------------------------------------------------------

_AUDIO_CHOICES = [
    ("smart",         "Subtitles fast-path → Groq → whisper-local fallback. RECOMMENDED."),
    ("groq",          "Groq Whisper-large-v3-turbo — fastest cloud backend (~12 s per 17-min video).  [free tier 8 h/day]  Key required."),
    ("whisper-local", "Local Whisper — offline, private, no API key.  [free]  Slower than groq."),
    ("subtitles",     "YouTube subtitles only. Instant, YouTube-only.  [free, no API]"),
    ("gemini",        "Google AI Studio — paired with vision/analyze options.  [free tier limited]  Key required.  Audio uses gemini-3.5-flash; 2.5-flash has +63% timestamp drift."),
    ("openai",        "OpenAI Whisper API.  [paid ~$0.006/min]  Key required."),
    ("deepgram",      "Deepgram Nova-3.  [starter credit $200 ≈ 750 h]  Key required."),
    ("assemblyai",    "AssemblyAI — good for long interviews.  [free tier ~5 h/month]  Key required."),
    ("custom",        "OpenAI-compatible API. For advanced setups.  [depends on provider]"),
]

_FALLBACK_OPTIONS: dict[str, str] = {
    "1": "groq",
    "2": "whisper-local",
    "3": "gemini",
}

# Stage 2: vision backend
_VISION_CHOICES = [
    ("groq",   "Groq Llama-4-Scout — fast per-frame, 1000 RPD free, accurate Cyrillic OCR.  RECOMMENDED."),
    ("gemini", "Gemini 2.5-flash — better Russian OCR but 250 RPD free tier.  Key required."),
    ("off",    "Skip vision pipeline (audio-only transcripts).  No vision API calls."),
]

# Stage 3: analyze backend (LLM that processes transcripts via `analyze`/
# `--then-analyze`/`research --filter`).
_ANALYZE_CHOICES = [
    ("groq",   "Groq Llama-3.3-70b — 14,400 RPD free tier (720× more than Gemini's 20).  RECOMMENDED."),
    ("gemini", "Gemini 3.5-flash — 20 RPD free tier, fine for occasional analyze.  Key required."),
    ("ollama", "Local Ollama (llama3.2:3b) — fully offline. Requires `ollama serve` running."),
    ("skip",   "Skip analyze: when running through Claude Code, Claude itself reads combined.md in chat."),
]

# Cloud backends that require a key — used to decide when to prompt.
_KEY_GUIDE: dict[str, str] = {
    "gemini":     "https://aistudio.google.com/apikey",
    "groq":       "https://console.groq.com/keys",
    "openai":     "https://platform.openai.com/api-keys",
    "deepgram":   "https://console.deepgram.com/",
    "assemblyai": "https://www.assemblyai.com/dashboard/signup",
    "custom":     "(specify your base URL and key in config.toml)",
}
_CLOUD_BACKENDS = set(_KEY_GUIDE.keys())

# Backends usable in each stage that need an API key.
_VISION_NEEDS_KEY = {"groq", "gemini"}
_ANALYZE_NEEDS_KEY = {"groq", "gemini"}

# v0.12.1: tier choices per provider
_TIER_OPTIONS_GEMINI: dict[str, str] = {
    "1": "free",         # default (limited RPD, no explicit caching)
    "2": "paid",         # paid-tier1
    "3": "paid-tier2",
    "4": "paid-tier3",
}
_TIER_OPTIONS_GROQ: dict[str, str] = {
    "1": "free",
    "2": "paid",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the interactive 4-stage setup wizard.

    Stages:
      1. Audio backend (always asked)
      2. Vision backend
      3. Analyze backend
      4. Online video sources — which platforms (YouTube / Instagram /
         TikTok / local-only), per-platform cookies file, per-platform
         research volume. Drives the v0.15.0 anti-block cascade.
      5. Tier per provider (when a cloud backend was chosen)
      6. Paid-tier model overrides (only if tier != "free")
      7. API keys for all chosen backends
    """
    # v0.12.2: hard-fail on non-TTY stdin. The wizard uses rich.Prompt.ask
    # which hangs/EOFs on a closed stdin (e.g. when Claude Code invokes
    # this as a subprocess). Instead of dying mid-prompt, refuse early
    # with a clear message pointing at the non-interactive config tools.
    import sys
    if not sys.stdin.isatty():
        sys.stderr.write(
            "[neurolearn] `config wizard` is interactive and requires a TTY.\n"
            "  When running from Claude Code or another non-interactive\n"
            "  context, configure via:\n"
            "    neurolearn config set-key groq <KEY>      # paste pasted key as positional\n"
            "    neurolearn config set backend smart       # audio default\n"
            "    neurolearn config set fallback groq       # smart cascade fallback\n"
            "    neurolearn config set-key gemini <KEY>    # optional fallback\n"
            "  See SKILL.md or commands/setup.md for the Claude-driven onboarding flow.\n"
        )
        sys.exit(2)

    console = make_console()
    info = detect_platform()
    vram_str = f"{info.vram_mb} MiB" if info.vram_mb is not None else "n/a"
    console.print(Panel.fit(
        f"[bold]neurolearn — first-run setup (v0.12.1)[/bold]\n\n"
        f"Detected: [cyan]{info.label}[/cyan]  "
        f"(device={info.device}, VRAM={vram_str})\n"
        f"[green]Recommendation:[/green] smart cascade for audio, Groq for vision,\n"
        f"Groq for analyze. One free Groq key (https://console.groq.com/keys)\n"
        f"covers all three.\n\n"
        f"[dim]Cloud backends send data to provider servers. Make sure that's\n"
        f"acceptable. Reconfigure anytime with `neurolearn config wizard`.[/dim]",
        title="neurolearn",
    ))

    cfg = load_config(CONFIG_PATH)

    # === Stage 1: audio backend ===
    audio_backend = _ask_choice(
        console, "\n[bold]Step 1 / 4:[/bold] Audio transcription backend?",
        _AUDIO_CHOICES, default_idx=1,
    )
    cfg.default_backend = audio_backend  # type: ignore[assignment]

    if audio_backend == "smart":
        console.print(
            "\n[dim]Smart cascade fallback backend (used after subtitles miss):\n"
            "  1) groq (recommended — fastest, free 8 h/day)\n"
            "  2) whisper-local\n"
            "  3) gemini[/dim]"
        )
        fb_choice = Prompt.ask(
            "Fallback", choices=list(_FALLBACK_OPTIONS.keys()), default="1",
        )
        cfg.fallback_backend = _FALLBACK_OPTIONS[fb_choice]  # type: ignore[assignment]

    # === Stage 2: vision backend ===
    vision_backend = _ask_choice(
        console,
        "\n[bold]Step 2 / 4:[/bold] Vision backend for `--with-visuals` (keyframe descriptions)?",
        _VISION_CHOICES, default_idx=1,
    )
    cfg.vision_backend = vision_backend

    # === Stage 3: analyze backend ===
    analyze_backend = _ask_choice(
        console,
        "\n[bold]Step 3 / 4:[/bold] LLM for transcript analysis (`analyze`, `--then-analyze`)?",
        _ANALYZE_CHOICES, default_idx=1,
    )
    cfg.analyze_backend = analyze_backend if analyze_backend != "skip" else None

    # === Stage 4 (v0.15.0): platform-aware anti-block setup ===
    _ask_research_platforms_and_cookies(console, cfg)

    # === Stage 5 + 6: tier-aware paid-model overrides ===
    chosen_providers = _collect_providers(audio_backend, vision_backend, analyze_backend)
    if "gemini" in chosen_providers:
        _ask_gemini_tier_and_models(console, cfg, vision_backend, analyze_backend)
    if "groq" in chosen_providers:
        _ask_groq_tier_and_models(console, cfg, vision_backend, analyze_backend)

    # v0.13.0: mark onboarding complete so work-commands stop refusing.
    cfg.onboarding_complete = True
    save_config(cfg, CONFIG_PATH)

    # === Stage 6: API keys for any cloud backend we just selected ===
    _collect_keys(console, chosen_providers)

    # === Done ===
    console.print("\n[green]✓ Configured.[/green]")
    console.print(
        f"  audio:    [bold]{audio_backend}[/bold]"
        + (f" (→ fallback {cfg.fallback_backend})" if audio_backend == "smart" else "")
    )
    console.print(f"  vision:   [bold]{vision_backend}[/bold]")
    console.print(f"  analyze:  [bold]{analyze_backend}[/bold]")
    if cfg.selected_platforms:
        console.print(
            f"  sources:  [bold]{', '.join(cfg.selected_platforms)}[/bold]"
        )
    console.print(
        "\nChange anytime:    [cyan]neurolearn config wizard[/cyan]\n"
        "Per-call override: [cyan]neurolearn <URL> --backend gemini[/cyan]"
    )


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _ask_choice(console, header: str, choices: list[tuple[str, str]],
                default_idx: int = 1) -> str:
    """Print a numbered menu and return the picked backend key."""
    console.print(header)
    for idx, (name, desc) in enumerate(choices, start=1):
        star = " [yellow]⭐[/yellow]" if idx == default_idx else ""
        console.print(f"  [cyan]{idx})[/cyan] [bold]{name}[/bold]{star} — {desc}")
    pick = Prompt.ask(
        "Choice",
        choices=[str(i) for i in range(1, len(choices) + 1)],
        default=str(default_idx),
    )
    return choices[int(pick) - 1][0]


def _collect_providers(audio: str, vision: str, analyze: str) -> set[str]:
    """Return the set of cloud providers we need keys/tier info for."""
    out: set[str] = set()
    for choice in (audio, vision, analyze):
        if choice in _CLOUD_BACKENDS:
            out.add(choice)
        # smart cascade implicitly uses Groq as fallback by default; that's
        # captured in the fallback step. No extra add needed here.
    return out


def _ask_gemini_tier_and_models(
    console, cfg, vision_backend: str, analyze_backend: str,
) -> None:
    console.print(
        "\n[bold]Gemini API tier?[/bold]\n"
        "  1) free (default — 20 RPD on 3.5-flash, no explicit caching)\n"
        "  2) paid (Tier 1)\n"
        "  3) paid-tier2\n"
        "  4) paid-tier3"
    )
    pick = Prompt.ask("Choice", choices=list(_TIER_OPTIONS_GEMINI.keys()), default="1")
    cfg.gemini_tier = _TIER_OPTIONS_GEMINI[pick]

    if cfg.gemini_tier == "free":
        return  # constrained flow — no override prompts

    console.print(
        "\n[dim]Paid Gemini tier detected — you can override the model used at\n"
        "each stage. Press Enter to keep the recommended default.\n"
        "⚠ Do NOT use gemini-2.5-flash for audio — it has a +63% timestamp drift bug.[/dim]"
    )
    cfg.gemini_model = _ask_model_override(
        "Gemini model for AUDIO fallback",
        default="gemini-3.5-flash",
        suggestions="gemini-3.5-flash, gemini-3.5-pro, gemini-3-pro-preview",
    )
    if vision_backend == "gemini":
        cfg.gemini_vision_model = _ask_model_override(
            "Gemini model for VISION",
            default="gemini-2.5-flash",
            suggestions="gemini-2.5-flash, gemini-2.5-pro, gemini-3.5-flash",
        )
    if analyze_backend == "gemini":
        cfg.gemini_analyze_model = _ask_model_override(
            "Gemini model for ANALYZE",
            default="gemini-3.5-flash",
            suggestions="gemini-3.5-flash, gemini-3.5-pro (better for long-form synthesis)",
        )

    yn = Prompt.ask(
        "\nEnable URL fast-path for YouTube audio (zero-download, 3.5-flash only)? [y/N]",
        choices=["y", "n", "Y", "N", ""], default="n", show_choices=False,
    )
    cfg.gemini_url_fastpath = yn.lower() == "y"


def _ask_groq_tier_and_models(
    console, cfg, vision_backend: str, analyze_backend: str,
) -> None:
    console.print(
        "\n[bold]Groq API tier?[/bold]\n"
        "  1) free (default — 8 h audio/day, 1000 RPD vision)\n"
        "  2) paid (developer / production tier)"
    )
    pick = Prompt.ask("Choice", choices=list(_TIER_OPTIONS_GROQ.keys()), default="1")
    cfg.groq_tier = _TIER_OPTIONS_GROQ[pick]

    if cfg.groq_tier == "free":
        return

    console.print(
        "\n[dim]Paid Groq tier — you can override models per stage. Press Enter\n"
        "to keep the recommended default.[/dim]"
    )
    cfg.groq_model = _ask_model_override(
        "Groq model for AUDIO",
        default="whisper-large-v3-turbo",
        suggestions="whisper-large-v3-turbo, whisper-large-v3, distil-whisper-large-v3-en",
    )
    if vision_backend == "groq":
        cfg.groq_vision_model = _ask_model_override(
            "Groq model for VISION",
            default="meta-llama/llama-4-scout-17b-16e-instruct",
            suggestions="meta-llama/llama-4-scout-17b-16e-instruct, meta-llama/llama-4-maverick-17b-128e-instruct",
        )
    if analyze_backend == "groq":
        cfg.groq_analyze_model = _ask_model_override(
            "Groq model for ANALYZE",
            default="llama-3.3-70b-versatile",
            suggestions="llama-3.3-70b-versatile, llama-4-maverick-17b-128e-instruct, deepseek-r1-distill-llama-70b",
        )


def _ask_research_platforms_and_cookies(console, cfg) -> None:
    """v0.15.0 Step 4: figure out which platforms the user will fetch
    videos from, walk them through cookies registration for each, and
    capture per-platform research volume.

    This isn't optional gating — we never block the wizard if the user
    skips cookies. We just make sure that when their first request gets
    blocked by YouTube / Instagram / TikTok, the cascade has the right
    auth available OR the right per-platform fix instruction is shown.
    """
    console.print("\n[bold]Step 4 / 4:[/bold] Online video sources")
    console.print(
        "  [dim]Which platforms will you fetch from? Cookies make transcription\n"
        "  much more reliable: YouTube rate-limits anonymous requests aggressively,\n"
        "  Instagram/TikTok need a logged-in session beyond a single public post.[/dim]"
    )
    console.print(
        "    1) YouTube\n"
        "    2) Instagram (posts / reels / IGTV)\n"
        "    3) TikTok\n"
        "    4) Local files only (skip cookies setup)"
    )
    picked = Prompt.ask(
        "Platforms (comma-separated, default 1)",
        default="1",
    )
    selected_keys = {p.strip() for p in picked.split(",") if p.strip()}
    if "4" in selected_keys:
        cfg.selected_platforms = []
        console.print("  [dim]No cookies registered — fully-online research isn't expected.[/dim]")
        return

    name_map = {"1": "youtube", "2": "instagram", "3": "tiktok"}
    platforms = [name_map[k] for k in ("1", "2", "3") if k in selected_keys]
    if not platforms:
        # Defensive fallback — user entered something we couldn't parse
        platforms = ["youtube"]
    cfg.selected_platforms = platforms

    for platform in platforms:
        console.print(f"\n  [bold cyan]{platform}[/bold cyan]")
        path_prompt = (
            f"    Path to {platform} cookies.txt "
            f"(Enter = skip — register later via "
            f"{'config set-cookies --from-file' if platform == 'youtube' else f'subscribes cookies set {platform} --from-file'})"
        )
        cookies_path = Prompt.ask(path_prompt, default="").strip()
        if cookies_path:
            try:
                _register_platform_cookies(platform, cookies_path, cfg, console)
            except Exception as e:
                console.print(
                    f"    [yellow]⚠ Could not register cookies ({e}). "
                    f"Skipping — run set-cookies manually later.[/yellow]"
                )

        # Volume — drives whether cascade tries anonymous first or
        # goes straight to cookies. Light is the safe default.
        console.print(
            f"    [dim]How much {platform} content per week?\n"
            f"      1) light — < 20 videos\n"
            f"      2) heavy — 20+ videos / channels / batch'es[/dim]"
        )
        volume_choice = Prompt.ask("    Volume", choices=["1", "2"], default="1")
        volume = "light" if volume_choice == "1" else "heavy"
        if platform == "youtube":
            cfg.youtube_research_volume = volume
        elif platform == "instagram":
            cfg.instagram_research_volume = volume
        elif platform == "tiktok":
            cfg.tiktok_research_volume = volume

    console.print()


def _register_platform_cookies(platform: str, raw_path: str, cfg, console) -> None:
    """Copy a cookies.txt into ~/.neurolearn/, set 0600, populate cfg.

    Mirrors what `config set-cookies` and `subscribes cookies set` do —
    extracted so the wizard can run the same logic in-process without
    spawning subprocesses."""
    from pathlib import Path as _P
    import os as _os
    src = _P(raw_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"{src} not found")
    dest = ENV_PATH.parent / f"{platform}-cookies.txt"
    dest.write_bytes(src.read_bytes())
    if _os.name != "nt":
        try:
            _os.chmod(dest, 0o600)
        except OSError:
            pass
    if platform == "youtube":
        cfg.cookies_file = str(dest)            # legacy slot (subtitles backend)
        cfg.youtube_cookies_file = str(dest)
    elif platform == "instagram":
        cfg.instagram_cookies_file = str(dest)
    elif platform == "tiktok":
        cfg.tiktok_cookies_file = str(dest)
    console.print(f"    [green]✓[/green] cookies saved → [bold]{dest}[/bold] (mode 0600)")


def _ask_model_override(label: str, *, default: str, suggestions: str) -> str:
    """Prompt for an optional model override. Returns the user's pick, or
    the default when they press Enter."""
    console = make_console()
    console.print(f"\n[dim]{label} (Enter = keep default {default}):\n  options: {suggestions}[/dim]")
    val = Prompt.ask("> ", default=default)
    return val.strip() or default


def _collect_keys(console, providers: set[str]) -> None:
    """For each cloud provider that needs a key and isn't already configured,
    prompt for the key value and write it to .env."""
    from skills.neurolearn.config import get_api_key
    for backend in sorted(providers):
        if backend not in _CLOUD_BACKENDS:
            continue
        if get_api_key(backend, env_path=ENV_PATH):
            # Already configured — don't re-prompt.
            continue
        guide = _KEY_GUIDE[backend]
        console.print(
            f"\n[yellow]{backend.upper()}_API_KEY required.[/yellow]  "
            f"Get one at: [link={guide}]{guide}[/link]"
        )
        key = Prompt.ask(
            f"Enter {backend.upper()}_API_KEY  (Enter = skip)",
            default="", password=True,
        )
        if key.strip():
            set_api_key(backend, key.strip(), env_path=ENV_PATH)
            console.print(f"[green]✓[/green] {backend} key saved to {ENV_PATH}")
        else:
            console.print(f"[dim]Skipped. Add later via `neurolearn config set-key {backend} <KEY>`.[/dim]")
