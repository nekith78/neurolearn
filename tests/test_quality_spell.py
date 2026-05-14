"""Tests for out_of_vocab_ratio."""
from skills.youtube_transcribe.quality.spell import (
    out_of_vocab_ratio,
    is_language_supported,
)


def test_oov_clean_english_text():
    text = "Hello and welcome to the tutorial about Python programming"
    ratio = out_of_vocab_ratio(text, "en")
    assert ratio < 0.1, f"clean text should have low OOV, got {ratio}"


def test_oov_garbled_text():
    text = "prveит и пддеа кгдре прив тмаета пвоиет"
    ratio = out_of_vocab_ratio(text, "ru")
    assert ratio > 0.5, f"garbled text should have high OOV, got {ratio}"


def test_oov_empty_text_returns_one():
    """Empty text — treat as fully OOV (worst case)."""
    assert out_of_vocab_ratio("", "en") == 1.0
    assert out_of_vocab_ratio("   ", "en") == 1.0


def test_unsupported_language_returns_none_via_helper():
    assert is_language_supported("en") is True
    assert is_language_supported("ru") is True
    assert is_language_supported("kk") is False  # Kazakh not in pyspellchecker


def test_oov_unsupported_language_returns_neg_one():
    """Sentinel value — caller must skip this metric."""
    ratio = out_of_vocab_ratio("қазақ тілі", "kk")
    assert ratio == -1.0
