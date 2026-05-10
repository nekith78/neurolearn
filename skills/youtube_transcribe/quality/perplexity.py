"""Perplexity-based anomaly detection for transcripts (spec §3 brick F).

Uses [lmppl](https://github.com/asahi417/lmppl) to compute per-segment
perplexity via a small causal LM (GPT-2 default for English). Garbled ASR
output gives perplexity 5-10x normal text — we detect that signal.

Opt-in: requires `pip install youtube-transcribe[perplexity]` AND triggers
~500 MB GPT-2 download on first call. Currently English-only — other
languages return -1.0 sentinel and the brick is skipped.

Default lang→model map can be extended by editing _LANG_MODELS below.
"""
from __future__ import annotations

from functools import lru_cache

from skills.youtube_transcribe.utils.output_writer import Segment

_LANG_MODELS: dict[str, str] = {
    "en": "gpt2",
    # Add more entries when models proven to work cross-platform without
    # heavy GPU. (mGPT/XGLM are 1.4 GB+ — too big for opt-in default.)
}


def is_perplexity_available_for_lang(lang: str) -> bool:
    """True if a model is configured for this language AND lmppl importable."""
    if lang not in _LANG_MODELS:
        return False
    try:
        import lmppl  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=2)
def _get_lm(lang: str):
    """Lazy-load lmppl LM for the given language. Returns None if unavailable."""
    model_name = _LANG_MODELS.get(lang)
    if model_name is None:
        return None
    try:
        from lmppl import LM
        return LM(model_name)
    except Exception:
        return None


def perplexity_anomaly_score(segments: list[Segment], lang: str) -> float:
    """Returns 0.0..1.0 (lower is better) or -1.0 if unsupported.

    Strategy:
      - Compute mean per-segment perplexity via lmppl.
      - Normal English speech transcripts: GPT-2 PPL roughly 30-150.
      - Garbled ASR (looped/garbled words): >500.
      - Return min(mean_ppl / 500, 1.0) — bounded score where 1.0 = very bad.
    """
    if lang not in _LANG_MODELS:
        return -1.0
    lm = _get_lm(lang)
    if lm is None:
        return -1.0

    texts = [s.text.strip() for s in segments if s.text.strip()]
    if not texts:
        return 0.0

    try:
        perps = lm.get_perplexity(texts)
    except Exception:
        return -1.0
    if not perps:
        return 0.0

    mean_ppl = sum(perps) / len(perps)
    return min(mean_ppl / 500.0, 1.0)
