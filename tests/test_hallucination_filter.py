"""Unit tests for utils.hallucination_filter."""
from __future__ import annotations

from skills.neurolearn.utils.hallucination_filter import (
    filter_hallucinations,
    is_hallucination,
)
from skills.neurolearn.utils.output_writer import Segment


# ---------------------------------------------------------------------------
# Density filter
# ---------------------------------------------------------------------------

def test_long_segment_with_few_chars_is_hallucination():
    """The Дудь-video v0.14.1 finding: 30 s for 21 chars (0.7 cps) =
    silence-fill, not real speech."""
    seg = Segment(start=14254.0, end=14284.0, text="Продолжение следует...")
    assert is_hallucination(seg) is True


def test_thirty_second_subscribe_segment_is_hallucination():
    seg = Segment(start=600.0, end=630.0, text="Subscribe to my channel.")
    assert is_hallucination(seg) is True


def test_real_long_sentence_is_not_hallucination():
    """A natural long sentence with dense text must NOT be dropped."""
    text = (
        "И вот работает только на такую вторую категорию. "
        "На сознательных реально и прошаренных маркетологов это "
        "не работает. Насколько эта концепция близка к правде?"
    )
    seg = Segment(start=7045.0, end=7060.0, text=text)
    # 15s for 175 chars = 11.6 cps — normal speech
    assert is_hallucination(seg) is False


def test_v0_15_1_low_cps_with_word_variety_is_kept():
    """v0.15.1 word-variety fix: a real lyric that Whisper stretched
    across an instrumental intro has low cps BUT high word variety.
    The Rick Astley music-intro case: 'We're no strangers to love'
    spanning 21.88s = 1.19 cps. v0.14.2 dropped this; v0.15.1 keeps
    it because the 6 distinct word stems mean it's real speech with
    mistimed bounds, not a Whisper invention."""
    seg = Segment(
        start=0.0, end=21.88,
        text="We're no strangers to love",
    )
    # 6 distinct stems: were / no / stra / to / love (with stripping)
    # — all above the ≤2 threshold for "looks repetitive"
    assert is_hallucination(seg) is False


def test_real_fast_short_phrase_is_not_hallucination():
    """Short phrases below the density-check threshold pass through —
    even if cps would be low, we don't apply the filter to short
    segments."""
    seg = Segment(start=10.0, end=12.0, text="Да.")
    # 2s for 3 chars = 1.5 cps; would fail density check, but
    # duration < 5s threshold means we don't apply density check
    assert is_hallucination(seg) is False


def test_dense_short_speech_passes():
    seg = Segment(start=10.0, end=11.0, text="Спасибо.")
    assert is_hallucination(seg) is False


def test_boundary_density_just_above_threshold():
    """5.0s × 10 chars = 2.0 cps exactly — at boundary, kept."""
    seg = Segment(start=0.0, end=5.0, text="abcdefghij")
    assert is_hallucination(seg) is False


def test_boundary_density_just_below_threshold_with_repetition():
    """5.0s × 9 chars = 1.8 cps + only 1 distinct stem ('xxxx xxxx') — dropped."""
    seg = Segment(start=0.0, end=5.0, text="abcd abcd")
    assert is_hallucination(seg) is True


def test_v0_15_1_boundary_density_with_word_variety_kept():
    """5.0s × 14 chars = 2.8 cps (above threshold) OR low cps + variety:
    new v0.15.1 logic requires BOTH low cps AND low variety to drop.
    A short fragment with several distinct words survives even at low cps."""
    # 5s, 9 chars but 3 distinct stems → keep
    seg = Segment(start=0.0, end=5.0, text="and yes ok")
    assert is_hallucination(seg) is False


def test_empty_segment_is_hallucination():
    """Empty-text segments carry no information; drop them."""
    seg = Segment(start=100.0, end=105.0, text="")
    assert is_hallucination(seg) is True


def test_whitespace_only_segment_is_hallucination():
    seg = Segment(start=100.0, end=105.0, text="   ")
    assert is_hallucination(seg) is True


# ---------------------------------------------------------------------------
# Blocklist filter
# ---------------------------------------------------------------------------

def test_blocklist_продолжение_следует_with_short_duration_still_dropped():
    """The blocklist drops the phrase even when duration is short —
    'Продолжение следует' has no business in an interview transcript."""
    seg = Segment(start=100.0, end=101.5, text="Продолжение следует.")
    assert is_hallucination(seg) is True


def test_blocklist_case_insensitive():
    seg = Segment(start=100.0, end=101.0, text="ПРОДОЛЖЕНИЕ СЛЕДУЕТ")
    assert is_hallucination(seg) is True


def test_blocklist_punctuation_normalized():
    """'Продолжение следует...' and 'Продолжение следует' both match."""
    seg = Segment(start=100.0, end=101.0, text="Продолжение следует...")
    assert is_hallucination(seg) is True


def test_blocklist_does_not_overmatch_substrings():
    """A real sentence CONTAINING a filler-phrase substring must NOT
    be dropped. The blocklist is whole-segment-only."""
    seg = Segment(start=10.0, end=12.0, text="Продолжение следует завтра в эфире.")
    assert is_hallucination(seg) is False


def test_real_спасибо_not_dropped():
    """User's video had real standalone 'Спасибо.' as an interview
    signoff. We intentionally don't blocklist 'спасибо' / 'спасибо
    большое' — too common in real speech."""
    seg = Segment(start=14245.0, end=14246.0, text="Спасибо.")
    assert is_hallucination(seg) is False


def test_real_thanks_for_watching_not_blocklisted():
    """We intentionally don't blocklist 'thanks for watching' — real
    vloggers say it. Only the truly-artificial fillers are listed."""
    seg = Segment(start=1000.0, end=1003.0, text="Thanks for watching")
    # 3s for 19 chars = 6.3 cps — dense, real speech
    assert is_hallucination(seg) is False


def test_blocklist_music_marker():
    """Whisper sometimes returns '(music)' or '[music]' as a
    pseudo-caption during instrumental sections. Drop these."""
    seg = Segment(start=10.0, end=20.0, text="(music)")
    assert is_hallucination(seg) is True


# ---------------------------------------------------------------------------
# filter_hallucinations — full sequence handling
# ---------------------------------------------------------------------------

def test_filter_returns_kept_and_dropped_separately():
    real = Segment(start=10.0, end=12.0, text="Это нормальная фраза.")
    fake = Segment(start=14254.0, end=14284.0, text="Продолжение следует...")
    empty = Segment(start=100.0, end=101.0, text="")

    kept, dropped = filter_hallucinations([real, fake, empty])

    assert kept == [real]
    assert len(dropped) == 2
    assert fake in dropped
    assert empty in dropped


def test_filter_preserves_order_of_kept_segments():
    a = Segment(start=0.0, end=1.0, text="Один.")
    b = Segment(start=1.0, end=2.0, text="Два.")
    c = Segment(start=2.0, end=3.0, text="Три.")

    kept, dropped = filter_hallucinations([a, b, c])

    assert kept == [a, b, c]
    assert dropped == []


def test_filter_pure_function_does_not_mutate_input():
    real = Segment(start=10.0, end=12.0, text="Это речь.")
    fake = Segment(start=20.0, end=50.0, text="Продолжение следует...")
    original = [real, fake]
    original_copy = list(original)

    filter_hallucinations(original)

    assert original == original_copy


def test_user_reported_tail_pattern_dropped_exactly():
    """Reproduce the user's v0.14.1 issue: real last segment kept,
    phantom 'Продолжение следует...' tail dropped."""
    last_real = Segment(start=14242.989, end=14243.369, text="Спасибо.")
    phantom = Segment(start=14254.069, end=14284.049, text="Продолжение следует...")

    kept, dropped = filter_hallucinations([last_real, phantom])

    assert kept == [last_real]
    assert dropped == [phantom]
