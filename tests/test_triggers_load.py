"""Tests for TriggerConfig loading and phrase entry parsing."""
import textwrap
from pathlib import Path

import pytest

from skills.neurolearn.detection.triggers import (
    TriggerConfig,
    load_triggers,
    parse_phrase_entry,
)


def test_parse_plain_string():
    phrase, weight = parse_phrase_entry("look here")
    assert phrase == "look here"
    assert weight == 1.0


def test_parse_weighted_array():
    phrase, weight = parse_phrase_entry(["function", 1.5])
    assert phrase == "function"
    assert weight == 1.5


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_phrase_entry(42)
    with pytest.raises(ValueError):
        parse_phrase_entry(["only_phrase"])
    with pytest.raises(ValueError):
        parse_phrase_entry([1, 2])


def test_load_triggers_from_user_file(tmp_path):
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        default_language = "en"
        universal_match_threshold = 0.7

        [triggers.universal]
        phrases = ["look here", ["function", 1.5]]

        [triggers.raw]
        phrases = ["TODO", ["FIXME", 2.0]]

        [triggers.languages.ru]
        soft = ["смотри сюда"]
        strict = ["баг", ["PR", 2.0]]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert cfg.default_language == "en"
    assert cfg.universal_match_threshold == 0.7
    assert cfg.universal["look here"] == 1.0
    assert cfg.universal["function"] == 1.5
    assert cfg.raw["TODO"] == 1.0
    assert cfg.raw["FIXME"] == 2.0
    assert cfg.languages["ru"].soft["смотри сюда"] == 1.0
    assert cfg.languages["ru"].strict["баг"] == 1.0
    assert cfg.languages["ru"].strict["PR"] == 2.0


def test_load_triggers_no_user_file_returns_builtin(tmp_path):
    """When user file doesn't exist, return built-in defaults."""
    cfg = load_triggers(user_path=tmp_path / "nonexistent.toml")
    # Built-in must include at least one universal phrase
    assert len(cfg.universal) > 0


def test_load_triggers_user_extends_builtin(tmp_path):
    """User phrases ADD to built-in, not replace (mode=extend default)."""
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        [triggers.universal]
        phrases = ["my custom phrase"]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert "my custom phrase" in cfg.universal
    # Built-in must still be present
    assert len(cfg.universal) > 1


def test_load_triggers_replace_mode(tmp_path):
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        mode = "replace"

        [triggers.universal]
        phrases = ["only this"]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert list(cfg.universal.keys()) == ["only this"]
