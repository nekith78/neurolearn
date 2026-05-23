"""Drop Whisper hallucinations from a transcript.

Whisper-family models have a well-documented failure mode: on silent,
near-silent, or musical tails they emit phantom segments containing
generic filler phrases ("Subscribe to my channel", "Спасибо за
просмотр", "Продолжение следует..."), often with a duration that's
absurd relative to the text length (30 seconds for three words).

We catch hallucinations with two cheap filters:

1. **Density filter** — segments where `duration > 5s` AND
   `chars_per_second < 2` are flagged. Real speech is 8-20 cps;
   anything below 2 cps on a multi-second segment is silence-fill.

2. **Blocklist** — case-insensitive match against known Whisper
   filler phrases collected from `whisper-WebUI`, `whisperX`, and
   field reports (Russian + English). Filler-only segments are
   dropped regardless of duration.

The two filters compose: a segment dropped by either is excluded
from the output. The filter is conservative (high precision over
recall) — if in doubt we keep the segment, because deleting real
speech is worse than keeping a hallucination.

Cross-backend by design: this runs on the merged TranscriptionResult,
so it benefits Groq, OpenAI, Deepgram (Nova-3 has the same
hallucination class on silence), local Whisper, and AssemblyAI alike.
"""
from __future__ import annotations

import re

from skills.neurolearn.utils.output_writer import Segment


# Known Whisper filler hallucinations on silence. Collected from:
# - https://github.com/jhj0517/Whisper-WebUI/blob/master/modules/utils/blacklist.py
# - https://github.com/m-bain/whisperX/issues/1064 (community list)
# - field reports during v0.14.1 testing
#
# Match is case-insensitive AND whitespace-normalised before lookup;
# trailing punctuation is stripped (so "Продолжение следует..." and
# "Продолжение следует" both match).
#
# Conservative list: only phrases that are essentially NEVER real
# speech in a video transcript. Common signoffs like "спасибо
# большое" / "thanks for watching" are NOT included — they're real
# speech in interview / vlog / podcast endings. The density filter
# (chars-per-second < 2 on segments ≥ 5 s) catches those when they're
# hallucinations and leaves them alone when they're real.
_HALLUCINATION_PHRASES_RU = {
    "продолжение следует",
    "субтитры сделал dimatorzok",
    "субтитры подогнал",
    "субтитры подогнал ник_сэмпай",
    "редактор субтитров а.семкин",
    "корректор а.егорова",
    "субтитры",
}

_HALLUCINATION_PHRASES_EN = {
    "subscribe to my channel",
    "like and subscribe",
    "don't forget to subscribe",
    "music",
    "applause",
    "(music)",
    "[music]",
    "(applause)",
    "[applause]",
    "♪",
    "♫",
}

_HALLUCINATION_PHRASES = _HALLUCINATION_PHRASES_RU | _HALLUCINATION_PHRASES_EN


# Density thresholds. Calibrated against real Russian + English data
# at varying speech rates. Hallucinations sit firmly below 2 cps;
# normal slow speech (a hesitant speaker) is ~5 cps; fast speech tops
# out around 20 cps.
_MIN_DURATION_FOR_DENSITY_CHECK = 5.0
_HALLUCINATION_DENSITY_CPS = 2.0

# v0.15.1: word-variety threshold for the density check. Real speech
# with low cps usually has many distinct words ("We're no strangers
# to love" = 6 stems). Whisper hallucinations on silence are usually
# repetitive (1-2 stems: "Python Python", "Продолжение следует").
# So we drop low-cps segments ONLY when they're also lexically
# repetitive — preserves real speech with mistimed timestamps.
_HALLUCINATION_MAX_DISTINCT_STEMS = 2


_PUNCT_STRIP = re.compile(r"[\.\,\!\?\:\;\-–—…\"\'\(\)\[\]]+")


def _normalize_for_blocklist(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = _PUNCT_STRIP.sub(" ", text)
    text = " ".join(text.split())
    return text


def _distinct_word_stems(text: str) -> int:
    """Count distinct word stems (case-insensitive, punctuation-stripped,
    first 4 chars of each token). Doesn't try to be a real stemmer —
    just enough to collapse "Python" / "python" / "Python's" to one
    bucket and "Skynet" / "sky net" to two."""
    normalized = _normalize_for_blocklist(text)
    if not normalized:
        return 0
    # First 4 chars catches common inflection (e.g. Russian endings
    # in the cases we care about: "продолж/енot/ение/ит" all → "прод").
    stems = {tok[:4] for tok in normalized.split() if tok}
    return len(stems)


def is_hallucination(seg: Segment) -> bool:
    """Return True if this segment is almost certainly a Whisper
    hallucination on silence. Conservative: when in doubt, returns
    False so real speech is never dropped.

    v0.15.1 added word-variety check — see Rick Astley case study:
    "We're no strangers to love" stretched across a 21.88s instrumental
    intro is also low-cps (1.19), but it's REAL Whisper output of the
    correct lyric, just with mistimed bounds. We don't want to drop
    that. Whisper-invented hallucinations on silence are reliably
    repetitive (Python Python / Subscribe Subscribe), so requiring
    ≥ 3 distinct word stems before dropping preserves the
    Rick-Astley-style cases.
    """
    text = (seg.text or "").strip()
    if not text:
        # Empty segments — drop them (they carry no information).
        return True

    duration = max(0.0, seg.end - seg.start)
    normalized = _normalize_for_blocklist(text)

    # Hard blocklist: a known filler phrase as the entire (normalized)
    # segment content. Substring match would over-fire — "ставьте
    # лайки и оставайтесь с нами" is real, "ставьте лайки" alone
    # at the end of a video is filler. We only drop the standalone form.
    if normalized in _HALLUCINATION_PHRASES:
        return True

    # Density filter: long segments with very few characters AND
    # very few distinct word stems are silence-fills. Real speech
    # with mistimed bounds (e.g. song lyric stretched over instrumental
    # intro) typically has many distinct words even at low cps —
    # the variety check spares it.
    if duration >= _MIN_DURATION_FOR_DENSITY_CHECK:
        chars_per_sec = len(text) / duration
        if chars_per_sec < _HALLUCINATION_DENSITY_CPS:
            stems = _distinct_word_stems(text)
            if stems <= _HALLUCINATION_MAX_DISTINCT_STEMS:
                return True

    return False


def filter_hallucinations(segments: list[Segment]) -> tuple[list[Segment], list[Segment]]:
    """Split `segments` into (kept, dropped). Pure function — does
    not mutate the input list.

    The dropped list lets callers log what was removed (useful for
    debugging and for the `--verbose` audit trail)."""
    kept: list[Segment] = []
    dropped: list[Segment] = []
    for seg in segments:
        if is_hallucination(seg):
            dropped.append(seg)
        else:
            kept.append(seg)
    return kept, dropped
