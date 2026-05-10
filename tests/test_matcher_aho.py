"""Tests for raw/strict matching via Aho-Corasick (no language detection yet)."""
from skills.youtube_transcribe.detection.triggers import LanguageTriggers, TriggerConfig
from skills.youtube_transcribe.detection.matcher import (
    TriggerMatch,
    _build_raw_automaton,
    _build_strict_automaton,
    _match_aho,
)


def _make_cfg() -> TriggerConfig:
    cfg = TriggerConfig()
    cfg.raw = {"TODO": 2.0, "FIXME": 1.0}
    cfg.languages["ru"] = LanguageTriggers(strict={"баг": 1.0, "PR": 2.0})
    return cfg


def test_raw_match_finds_TODO():
    cfg = _make_cfg()
    auto = _build_raw_automaton(cfg)
    res = _match_aho("we have a TODO here", auto)
    assert res is not None
    phrase, weight = res
    assert phrase == "todo"  # case-insensitive
    assert weight == 2.0


def test_raw_no_match():
    cfg = _make_cfg()
    auto = _build_raw_automaton(cfg)
    assert _match_aho("hello world", auto) is None


def test_strict_lang_match():
    cfg = _make_cfg()
    auto = _build_strict_automaton(cfg, "ru")
    res = _match_aho("это какой-то баг", auto)
    assert res is not None
    phrase, weight = res
    assert phrase == "баг"
    assert weight == 1.0


def test_strict_lang_no_automaton_for_other_lang():
    cfg = _make_cfg()
    auto = _build_strict_automaton(cfg, "es")  # no es strict triggers
    assert auto is None
