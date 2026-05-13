"""Tests for analyze.backend_resolver — onboarding flow + persistence."""
from pathlib import Path
from unittest.mock import patch

import tomllib


def _read_config_field(p: Path, *, section: str, key: str):
    if not p.exists():
        return None
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    return raw.get(section, {}).get(key) or None


def test_no_analyze_short_circuits(tmp_path: Path):
    """`--no-analyze` always wins, even with a saved config preference."""
    from skills.youtube_transcribe.analyze.backend_resolver import (
        resolve_analyze_backend,
    )
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_preset = "smart"\n\n[analyze]\nbackend = "gemini"\n',
        encoding="utf-8",
    )
    assert resolve_analyze_backend(
        cli_flag=None, no_analyze=True, config_path=cfg, is_tty=False,
    ) is None


def test_cli_flag_wins_over_config(tmp_path: Path):
    from skills.youtube_transcribe.analyze.backend_resolver import (
        resolve_analyze_backend,
    )
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_preset = "smart"\n\n[analyze]\nbackend = "gemini"\n',
        encoding="utf-8",
    )
    assert resolve_analyze_backend(
        cli_flag="claude", no_analyze=False, config_path=cfg, is_tty=False,
    ) == "claude"


def test_config_skip_returns_none(tmp_path: Path):
    """`analyze.backend = "skip"` in config → never auto-analyze."""
    from skills.youtube_transcribe.analyze.backend_resolver import (
        resolve_analyze_backend,
    )
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_preset = "smart"\n\n[analyze]\nbackend = "skip"\n',
        encoding="utf-8",
    )
    assert resolve_analyze_backend(
        cli_flag=None, no_analyze=False, config_path=cfg, is_tty=True,
    ) is None


def test_config_named_backend_used(tmp_path: Path):
    from skills.youtube_transcribe.analyze.backend_resolver import (
        resolve_analyze_backend,
    )
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_preset = "smart"\n\n[analyze]\nbackend = "ollama"\n',
        encoding="utf-8",
    )
    assert resolve_analyze_backend(
        cli_flag=None, no_analyze=False, config_path=cfg, is_tty=False,
    ) == "ollama"


def test_non_tty_no_config_returns_none(tmp_path: Path):
    """Non-TTY + no preference saved → silent skip (Claude Code path)."""
    from skills.youtube_transcribe.analyze.backend_resolver import (
        resolve_analyze_backend,
    )
    cfg = tmp_path / "config.toml"  # doesn't exist
    assert resolve_analyze_backend(
        cli_flag=None, no_analyze=False, config_path=cfg, is_tty=False,
    ) is None
    # And nothing was created
    assert not cfg.exists()


def test_tty_prompt_skip_saves_and_returns_none(tmp_path: Path):
    """TTY + no preference + user picks `skip` → save 'skip', return None."""
    from skills.youtube_transcribe.analyze import backend_resolver
    cfg = tmp_path / "config.toml"

    with patch("click.prompt", return_value="1"):
        result = backend_resolver.resolve_analyze_backend(
            cli_flag=None, no_analyze=False, config_path=cfg, is_tty=True,
        )
    assert result is None
    assert _read_config_field(cfg, section="analyze", key="backend") == "skip"


def test_tty_prompt_gemini_saves_and_returns(tmp_path: Path):
    from skills.youtube_transcribe.analyze import backend_resolver
    cfg = tmp_path / "config.toml"

    with patch("click.prompt", return_value="2"):
        result = backend_resolver.resolve_analyze_backend(
            cli_flag=None, no_analyze=False, config_path=cfg, is_tty=True,
        )
    assert result == "gemini"
    assert _read_config_field(cfg, section="analyze", key="backend") == "gemini"


def test_tty_prompt_options_cover_all_four_backends(tmp_path: Path):
    """Each numeric choice maps to the correct backend. We reset the config
    between iterations because a saved preference short-circuits the prompt
    on subsequent calls (that's the test_saved_preference_persists case)."""
    from skills.youtube_transcribe.analyze import backend_resolver

    table = {"3": "claude", "4": "openai", "5": "ollama"}
    for choice_num, backend in table.items():
        cfg = tmp_path / f"config-{choice_num}.toml"
        with patch("click.prompt", return_value=choice_num):
            result = backend_resolver.resolve_analyze_backend(
                cli_flag=None, no_analyze=False,
                config_path=cfg, is_tty=True,
            )
        assert result == backend, f"choice {choice_num} → expected {backend}"
        assert _read_config_field(
            cfg, section="analyze", key="backend"
        ) == backend


def test_saved_preference_persists_across_calls(tmp_path: Path):
    """Once saved, no more prompts on subsequent invocations."""
    from skills.youtube_transcribe.analyze import backend_resolver
    cfg = tmp_path / "config.toml"

    # First call: prompts and saves.
    with patch("click.prompt", return_value="2"):
        backend_resolver.resolve_analyze_backend(
            cli_flag=None, no_analyze=False, config_path=cfg, is_tty=True,
        )

    # Second call: no prompt expected. If `click.prompt` got called → fail.
    with patch(
        "click.prompt", side_effect=AssertionError("should not prompt"),
    ):
        result = backend_resolver.resolve_analyze_backend(
            cli_flag=None, no_analyze=False, config_path=cfg, is_tty=True,
        )
    assert result == "gemini"
