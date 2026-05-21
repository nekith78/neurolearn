"""Tests for preset loading + merge with user config + CLI overrides."""
import textwrap
from pathlib import Path

import pytest

from skills.neurolearn.presets.loader import (
    load_preset_values,
    list_preset_names,
)


def test_list_presets_includes_4_tiers():
    names = list_preset_names()
    assert {"eco", "smart", "standard", "premium"}.issubset(set(names))


def test_load_smart_preset_defaults():
    vals = load_preset_values("smart", user_config_path=Path("/nonexistent/path.toml"))
    assert vals["transcribe_backend"] == "subtitles"
    # v0.10.6: smart preset has vision OFF by default. Users opt into
    # vision via `--with-visuals` or `--preset standard/premium/tutorial`.
    assert vals["vision_backend"] == "off"
    assert vals["max_windows_per_video"] == 0
    assert vals["detect_method"] == "hybrid"


def test_standard_preset_still_has_vision_on():
    """v0.10.6 sanity (updated for v0.12.0): richer presets (standard /
    premium / tutorial) remain deliberate vision-on opt-ins. The
    tutorial preset now defaults to vision_backend='groq' (Llama-4-Scout
    is faster + has 1000 free RPD vs Gemini's 250); standard/premium
    keep gemini for backwards compat."""
    expected = {
        "standard": "gemini",
        "premium": "gemini",
        "tutorial": "groq",  # v0.12.0: tutorial moved to Groq
    }
    for preset_name, want in expected.items():
        vals = load_preset_values(
            preset_name, user_config_path=Path("/nonexistent/path.toml"),
        )
        assert vals["vision_backend"] == want, (
            f"{preset_name}: expected vision_backend={want}, "
            f"got {vals['vision_backend']}"
        )
        assert vals["max_windows_per_video"] > 0


def test_load_eco_preset_no_visual():
    vals = load_preset_values("eco", user_config_path=Path("/nonexistent/path.toml"))
    assert vals["vision_backend"] == "off"


def test_load_unknown_preset_raises():
    with pytest.raises(KeyError):
        load_preset_values("nonexistent")


def test_user_config_overrides_builtin(tmp_path):
    user_path = tmp_path / "config.toml"
    user_path.write_text(textwrap.dedent("""\
        [presets.smart]
        max_windows_per_video = 50
    """), encoding="utf-8")

    vals = load_preset_values("smart", user_config_path=user_path)
    assert vals["max_windows_per_video"] == 50
    # Other fields remain from built-in
    assert vals["transcribe_backend"] == "subtitles"


def test_cli_overrides_beat_user_and_builtin(tmp_path):
    user_path = tmp_path / "config.toml"
    user_path.write_text(textwrap.dedent("""\
        [presets.smart]
        max_windows_per_video = 50
    """), encoding="utf-8")

    vals = load_preset_values(
        "smart",
        user_config_path=user_path,
        cli_overrides={"max_windows_per_video": 100, "vision_backend": "off"},
    )
    assert vals["max_windows_per_video"] == 100
    assert vals["vision_backend"] == "off"


def test_external_config_path_replaces_user(tmp_path):
    """--config /path/to/file.toml — alternative config file."""
    ext_path = tmp_path / "ext.toml"
    ext_path.write_text(textwrap.dedent("""\
        [presets.smart]
        transcribe_backend = "groq"
    """), encoding="utf-8")

    vals = load_preset_values("smart", external_config_path=ext_path)
    assert vals["transcribe_backend"] == "groq"
