"""Tests for HeuristicChecker — composite quality assessment."""
from skills.youtube_transcribe.quality.heuristic_checker import HeuristicChecker
from skills.youtube_transcribe.utils.output_writer import Segment


def _seg(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_manual_subs_get_perfect_score():
    """is_generated=False → score=1.0, no other checks run."""
    checker = HeuristicChecker()
    segments = [_seg(0, 5, "anything"), _seg(5, 10, "even garbled prveит")]
    report = checker.check(segments, "en", source="youtube_manual")
    assert report.score == 1.0
    assert report.recommendation == "use_as_is"
    assert report.breakdown.get("reason") == "manual_captions"


def test_mostly_music_flag_lowers_score():
    checker = HeuristicChecker()
    segments = [
        _seg(0, 30, "[Music]"),
        _seg(30, 60, "♪"),
        _seg(60, 65, "hello"),
    ]
    report = checker.check(segments, "en", source="youtube_auto")
    assert "mostly_music" in report.flags
    assert report.score <= 0.4
    assert report.recommendation == "fallback_recommended"


def test_clean_auto_subs_pass():
    checker = HeuristicChecker()
    text = "Hello and welcome to today's tutorial about Python programming basics"
    segments = [_seg(0, 10, text)]
    report = checker.check(segments, "en", source="youtube_auto")
    assert report.score >= 0.7
    assert report.recommendation == "use_as_is"


def test_garbled_auto_subs_fail():
    checker = HeuristicChecker()
    text = "prveит и пддеа кгдре прив тмаета пвоиет ыклмп длвоп"
    segments = [_seg(0, 10, text)]
    report = checker.check(segments, "ru", source="youtube_auto")
    assert report.score < 0.5
    assert "high_oov" in report.flags
    assert report.recommendation in ("fallback_recommended", "low_quality")


def test_whisper_loop_caught():
    checker = HeuristicChecker()
    text = " ".join(["thank you for watching"] * 25)
    segments = [_seg(0, 60, text)]
    report = checker.check(segments, "en", source="whisper")
    assert "looped" in report.flags or "boilerplate_hallucinations" in report.flags
    assert report.score < 0.5
