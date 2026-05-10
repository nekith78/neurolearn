"""Tests for perplexity brick (opt-in). lmppl import mocked."""
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.quality import perplexity
from skills.youtube_transcribe.quality.perplexity import (
    _LANG_MODELS,
    is_perplexity_available_for_lang,
    perplexity_anomaly_score,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def _seg(text: str) -> Segment:
    return Segment(start=0.0, end=1.0, text=text)


def test_unsupported_language_returns_neg_one():
    assert perplexity_anomaly_score([_seg("hello")], "kk") == -1.0


def test_unsupported_lang_via_helper():
    assert is_perplexity_available_for_lang("kk") is False


def test_supported_lang_when_lmppl_missing(monkeypatch):
    """English IS in _LANG_MODELS but lmppl might not be installed."""
    # Force lmppl import to fail
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "lmppl":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    perplexity._get_lm.cache_clear()

    assert is_perplexity_available_for_lang("en") is False
    assert perplexity_anomaly_score([_seg("hello")], "en") == -1.0


def test_normal_text_low_score(monkeypatch):
    """Normal English text: PPL ~50 → score ~0.1."""
    fake_lm = MagicMock()
    fake_lm.get_perplexity = MagicMock(return_value=[50.0, 60.0, 45.0])

    monkeypatch.setattr(perplexity, "_get_lm", lambda lang: fake_lm)
    score = perplexity_anomaly_score(
        [_seg("hello"), _seg("world"), _seg("today")],
        "en",
    )
    # mean(50+60+45)/3 = 51.67; score = 51.67/500 = 0.103
    assert 0.0 < score < 0.2


def test_garbled_text_high_score(monkeypatch):
    """Garbled text: PPL >500 → score 1.0."""
    fake_lm = MagicMock()
    fake_lm.get_perplexity = MagicMock(return_value=[800.0, 1200.0, 900.0])

    monkeypatch.setattr(perplexity, "_get_lm", lambda lang: fake_lm)
    score = perplexity_anomaly_score(
        [_seg("garbage")] * 3,
        "en",
    )
    assert score == 1.0  # capped


def test_empty_segments_zero():
    assert perplexity_anomaly_score([], "en") in (0.0, -1.0)
    # If lmppl absent: -1.0; if present: 0.0 (no segments).


def test_lm_failure_returns_neg_one(monkeypatch):
    """If lmppl call raises, return -1.0 sentinel."""
    fake_lm = MagicMock()
    fake_lm.get_perplexity = MagicMock(side_effect=RuntimeError("CUDA OOM"))

    monkeypatch.setattr(perplexity, "_get_lm", lambda lang: fake_lm)
    score = perplexity_anomaly_score([_seg("hi")], "en")
    assert score == -1.0


def test_only_whitespace_segments_zero(monkeypatch):
    """All-whitespace segments → 0.0 (nothing to score, treat as fine)."""
    fake_lm = MagicMock()
    monkeypatch.setattr(perplexity, "_get_lm", lambda lang: fake_lm)
    # Mock should NOT be called because no real text
    score = perplexity_anomaly_score([_seg("   "), _seg("\n")], "en")
    assert score == 0.0
    fake_lm.get_perplexity.assert_not_called()


def test_lang_models_includes_english():
    """English must be supported (default model is gpt2)."""
    assert "en" in _LANG_MODELS
    assert _LANG_MODELS["en"] == "gpt2"
