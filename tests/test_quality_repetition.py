"""Tests for trigram_repetition_rate and non_speech_marker_ratio."""
from skills.youtube_transcribe.quality.repetition import (
    trigram_repetition_rate,
    non_speech_marker_ratio,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def test_repetition_clean_text():
    text = "hello and welcome to the tutorial today we will discuss python programming concepts"
    assert trigram_repetition_rate(text) < 0.15


def test_repetition_whisper_loop():
    """Classic Whisper hallucination — same phrase repeated many times."""
    text = " ".join(["thank you"] * 40)
    assert trigram_repetition_rate(text) > 0.4


def test_repetition_short_text_returns_zero():
    """Need at least 6 tokens to compute trigrams."""
    assert trigram_repetition_rate("hi there friend") == 0.0


def test_non_speech_marker_zero_when_no_markers():
    segments = [
        Segment(start=0.0, end=5.0, text="hello world"),
        Segment(start=5.0, end=10.0, text="welcome to the show"),
    ]
    assert non_speech_marker_ratio(segments) == 0.0


def test_non_speech_marker_high_when_music_heavy():
    segments = [
        Segment(start=0.0, end=10.0, text="[Music]"),
        Segment(start=10.0, end=20.0, text="♪ ♪ ♪"),
        Segment(start=20.0, end=22.0, text="hello"),
    ]
    ratio = non_speech_marker_ratio(segments)
    assert ratio > 0.8, f"expected mostly music, got {ratio}"


def test_non_speech_marker_empty_returns_zero():
    assert non_speech_marker_ratio([]) == 0.0
