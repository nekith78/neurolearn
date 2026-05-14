"""Tests for HeuristicChecker.enable_perplexity integration."""
from unittest.mock import patch

from skills.neurolearn.quality.heuristic_checker import HeuristicChecker
from skills.neurolearn.utils.output_writer import Segment


def _seg(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_perplexity_disabled_by_default():
    """Default checker should NOT trigger perplexity computation."""
    checker = HeuristicChecker()
    assert checker.enable_perplexity is False
    text = "Hello and welcome to today's tutorial about Python basics"
    report = checker.check([_seg(0, 5, text)], "en", source="youtube_auto")
    assert "perplexity" not in report.breakdown


def test_perplexity_enabled_calls_brick(monkeypatch):
    """When enable_perplexity=True, brick is invoked and breakdown gets entry."""
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.is_perplexity_available_for_lang",
        lambda lang: True,
    )
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.perplexity_anomaly_score",
        lambda segs, lang: 0.1,  # normal text
    )
    checker = HeuristicChecker(enable_perplexity=True)
    text = "Hello and welcome to today's tutorial about Python basics"
    report = checker.check([_seg(0, 5, text)], "en", source="youtube_auto")
    assert report.breakdown.get("perplexity") == 0.1


def test_high_perplexity_lowers_score(monkeypatch):
    """ppl=1.0 should subtract 0.25 from score and add high_perplexity flag."""
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.is_perplexity_available_for_lang",
        lambda lang: True,
    )
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.perplexity_anomaly_score",
        lambda segs, lang: 1.0,  # totally garbled
    )

    text = "Hello and welcome to today's tutorial about Python basics"
    base_checker = HeuristicChecker(enable_perplexity=False)
    base_report = base_checker.check([_seg(0, 5, text)], "en", source="youtube_auto")

    ppl_checker = HeuristicChecker(enable_perplexity=True)
    ppl_report = ppl_checker.check([_seg(0, 5, text)], "en", source="youtube_auto")

    # Score with perplexity penalty must be lower
    assert ppl_report.score < base_report.score
    # Difference roughly 0.25 (penalty multiplier)
    assert abs((base_report.score - ppl_report.score) - 0.25) < 0.05
    assert "high_perplexity" in ppl_report.flags


def test_perplexity_unavailable_silently_skipped(monkeypatch):
    """If lmppl unavailable / lang unsupported → score unaffected."""
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.is_perplexity_available_for_lang",
        lambda lang: False,  # not available
    )
    text = "Hello and welcome to today's tutorial"
    a = HeuristicChecker(enable_perplexity=False).check(
        [_seg(0, 5, text)], "en", source="youtube_auto",
    )
    b = HeuristicChecker(enable_perplexity=True).check(
        [_seg(0, 5, text)], "en", source="youtube_auto",
    )
    assert a.score == b.score
    assert "perplexity" not in b.breakdown


def test_negative_perplexity_does_not_penalize(monkeypatch):
    """ppl_score returning -1.0 (sentinel for failure) should not change score."""
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.is_perplexity_available_for_lang",
        lambda lang: True,
    )
    monkeypatch.setattr(
        "skills.neurolearn.quality.perplexity.perplexity_anomaly_score",
        lambda segs, lang: -1.0,
    )
    text = "Hello and welcome to today's tutorial"
    a = HeuristicChecker(enable_perplexity=False).check(
        [_seg(0, 5, text)], "en", source="youtube_auto",
    )
    b = HeuristicChecker(enable_perplexity=True).check(
        [_seg(0, 5, text)], "en", source="youtube_auto",
    )
    assert a.score == b.score
