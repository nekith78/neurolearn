"""Tests for v0.1.x → v0.2 config migration."""
import textwrap
from pathlib import Path

from skills.youtube_transcribe.config import migrate_v01_to_v02


def test_v01_config_gets_default_preset_added(tmp_path):
    old_config = tmp_path / "config.toml"
    old_config.write_text(textwrap.dedent("""\
        default_backend = "whisper-local"
        fallback_backend = "whisper-local"

        [whisper-local]
        model = "turbo"

        [output]
        language = "auto"
    """), encoding="utf-8")

    migrate_v01_to_v02(old_config)

    content = old_config.read_text(encoding="utf-8")
    assert "default_preset" in content
    assert "[presets.custom_legacy]" in content


def test_v01_config_preserves_user_settings(tmp_path):
    old_config = tmp_path / "config.toml"
    old_config.write_text(textwrap.dedent("""\
        default_backend = "groq"
        [whisper-local]
        model = "large"
    """), encoding="utf-8")

    migrate_v01_to_v02(old_config)
    content = old_config.read_text(encoding="utf-8")
    # User backend choice preserved in legacy preset
    assert "groq" in content
    # whisper model preserved
    assert "large" in content


def test_v02_config_idempotent(tmp_path):
    """If config already has default_preset, migration is no-op."""
    config = tmp_path / "config.toml"
    config.write_text("default_preset = \"smart\"\n", encoding="utf-8")
    migrate_v01_to_v02(config)
    assert config.read_text("utf-8") == "default_preset = \"smart\"\n"


def test_no_config_file_does_nothing(tmp_path):
    """No-op if file doesn't exist."""
    nonexistent = tmp_path / "missing.toml"
    migrate_v01_to_v02(nonexistent)
    assert not nonexistent.exists()
