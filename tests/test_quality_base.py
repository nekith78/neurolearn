"""Tests for QualityReport dataclass and QualityChecker Protocol."""
from skills.youtube_transcribe.quality.base import (
    QualityReport,
    Recommendation,
)


def test_quality_report_creation():
    r = QualityReport(
        score=0.85,
        breakdown={"oov": 0.05, "repetition": 0.02},
        flags=[],
        recommendation="use_as_is",
    )
    assert r.score == 0.85
    assert r.recommendation == "use_as_is"


def test_recommendation_literal_values():
    valid: list[Recommendation] = ["use_as_is", "fallback_recommended", "low_quality"]
    assert len(valid) == 3
