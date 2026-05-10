"""Tests for Bag-of-Hallucinations detection."""
from skills.youtube_transcribe.quality.boh import bag_of_hallucinations_coverage


def test_boh_clean_text_zero():
    assert bag_of_hallucinations_coverage("hello and welcome to today's lesson") == 0.0


def test_boh_thank_you_for_watching_loop():
    text = " ".join(["thank you for watching"] * 10)
    coverage = bag_of_hallucinations_coverage(text)
    assert coverage > 0.5, f"expected high coverage, got {coverage}"


def test_boh_short_clip():
    text = "Today we will learn about Python. Thanks for watching!"
    coverage = bag_of_hallucinations_coverage(text)
    assert 0.0 < coverage < 0.5, f"single mention should give moderate coverage, got {coverage}"


def test_boh_russian_phrases():
    text = "ставьте лайк и подпишитесь на канал"
    coverage = bag_of_hallucinations_coverage(text)
    assert coverage > 0.3
