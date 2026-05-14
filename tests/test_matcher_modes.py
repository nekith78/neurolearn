"""Tests for match_segment mode parameter (spec §5 composition table).

Each detect_method should activate a specific subset of matchers:
- keywords_only: raw + per-lang strict + per-lang soft (NO universal embeddings)
- semantic: raw + universal (NO per-lang)
- hybrid: all four
- llm_full_pass: all four (LLM-classify added separately)
"""
import numpy as np
import pytest

from skills.neurolearn.detection.triggers import LanguageTriggers, TriggerConfig
from skills.neurolearn.detection import matcher
from skills.neurolearn.detection.matcher import match_segment


class FakeEncoder:
    """Deterministic stub: any text → vector close to first phrase embedding."""

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            rng = np.random.default_rng(hash(t.lower()) % (2**32))
            v = rng.standard_normal(384).astype(np.float32)
            v /= np.linalg.norm(v) + 1e-9
            out.append(v)
        return np.array(out)


@pytest.fixture(autouse=True)
def patch_encoder(monkeypatch):
    monkeypatch.setattr(matcher, "_get_encoder", lambda: FakeEncoder())
    # Clear LRU caches between tests so re-patched encoder takes effect
    matcher._get_universal_embeddings_cached.cache_clear()


def _full_cfg() -> TriggerConfig:
    """Config with raw, per-language strict/soft, and universal triggers."""
    cfg = TriggerConfig()
    cfg.raw = {"TODO": 2.0}
    cfg.universal = {"hello world": 1.0}
    cfg.universal_match_threshold = -1.0  # always match
    cfg.languages["en"] = LanguageTriggers(
        strict={"function": 1.0},
        soft={"the class call": 1.0},
    )
    return cfg


# === keywords_only ===

def test_keywords_only_does_not_use_universal():
    """In keywords_only mode, universal triggers should NOT fire even if
    they semantically match. Only raw / per-lang strict / per-lang soft."""
    cfg = TriggerConfig()
    cfg.universal = {"hello world": 1.0}
    cfg.universal_match_threshold = -1.0

    m = match_segment("totally unrelated text", cfg, mode="keywords_only")
    assert m is None, f"universal should NOT fire in keywords_only, got {m}"


def test_keywords_only_uses_raw():
    cfg = _full_cfg()
    m = match_segment("we have a TODO here", cfg, mode="keywords_only")
    assert m is not None
    assert m.reason == "raw"


def test_keywords_only_uses_per_lang_strict():
    cfg = _full_cfg()
    m = match_segment("see this function call", cfg, mode="keywords_only")
    assert m is not None
    assert m.reason.startswith("strict:")


# === semantic ===

def test_semantic_does_not_use_per_lang():
    """semantic mode should skip per-language strict/soft."""
    cfg = TriggerConfig()
    cfg.languages["en"] = LanguageTriggers(strict={"baguette": 1.0})

    m = match_segment("a fresh baguette", cfg, mode="semantic")
    assert m is None, f"per-lang should NOT fire in semantic, got {m}"


def test_semantic_uses_raw():
    cfg = _full_cfg()
    m = match_segment("we have a TODO here", cfg, mode="semantic")
    assert m is not None
    assert m.reason == "raw"


def test_semantic_uses_universal():
    cfg = TriggerConfig()
    cfg.universal = {"hello world": 1.0}
    cfg.universal_match_threshold = -1.0  # always match

    m = match_segment("any text", cfg, mode="semantic")
    assert m is not None
    assert m.reason == "universal"


# === hybrid ===

def test_hybrid_uses_all_matchers_raw_first():
    cfg = _full_cfg()
    m = match_segment("we have a TODO here", cfg, mode="hybrid")
    assert m is not None
    assert m.reason == "raw"


def test_hybrid_falls_through_to_universal():
    """If no raw / per-lang match, hybrid still tries universal."""
    cfg = TriggerConfig()
    cfg.universal = {"hello": 1.5}
    cfg.universal_match_threshold = -1.0
    m = match_segment("totally unrelated", cfg, mode="hybrid")
    assert m is not None
    assert m.reason == "universal"


# === llm_full_pass ===

def test_llm_full_pass_behaves_like_hybrid_for_keyword_matchers():
    """LLM-classify is added in pipeline_v02; here we just check matcher
    runs all 4 brick types."""
    cfg = _full_cfg()
    m = match_segment("we have a TODO here", cfg, mode="llm_full_pass")
    assert m is not None
    assert m.reason == "raw"


# === default mode ===

def test_default_mode_is_hybrid():
    """match_segment(text, cfg) without mode defaults to hybrid."""
    cfg = TriggerConfig()
    cfg.universal = {"hello": 1.0}
    cfg.universal_match_threshold = -1.0
    m = match_segment("anything", cfg)  # default
    assert m is not None
    assert m.reason == "universal"


# === encoder lazy-load: keywords_only must NOT call encoder ===

def test_keywords_only_does_not_call_encoder(monkeypatch):
    """Verify encoder is never called in keywords_only mode (perf invariant)."""
    cfg = TriggerConfig()
    cfg.raw = {"TODO": 1.0}
    cfg.universal = {"x": 1.0}

    encoder_calls = {"n": 0}

    def fake_get_encoder():
        encoder_calls["n"] += 1
        return FakeEncoder()

    monkeypatch.setattr(matcher, "_get_encoder", fake_get_encoder)
    matcher._get_universal_embeddings_cached.cache_clear()

    match_segment("hello there", cfg, mode="keywords_only")
    assert encoder_calls["n"] == 0, \
        f"encoder must not be called in keywords_only, was called {encoder_calls['n']}x"


def test_semantic_does_call_encoder(monkeypatch):
    """Sanity check the inverse: semantic DOES load encoder."""
    cfg = TriggerConfig()
    cfg.universal = {"x": 1.0}
    cfg.universal_match_threshold = -1.0

    encoder_calls = {"n": 0}

    def fake_get_encoder():
        encoder_calls["n"] += 1
        return FakeEncoder()

    monkeypatch.setattr(matcher, "_get_encoder", fake_get_encoder)
    matcher._get_universal_embeddings_cached.cache_clear()

    match_segment("hello there", cfg, mode="semantic")
    assert encoder_calls["n"] >= 1
