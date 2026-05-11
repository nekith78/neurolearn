"""Tests for shared.match — case-insensitive substring filter."""
from dataclasses import dataclass

from skills.youtube_transcribe.shared.match import match_titles


@dataclass
class _Cand:
    """Minimal test stand-in for any candidate with a `title` attribute."""
    title: str
    extra: str = ""


def test_simple_substring():
    cands = [_Cand(title="Claude features deep dive"),
             _Cand(title="GPT-5 release notes")]
    out = match_titles(cands, "claude")
    assert len(out) == 1
    assert out[0].title.startswith("Claude")


def test_case_insensitive():
    cands = [_Cand(title="CLAUDE FEATURES"),
             _Cand(title="claude features"),
             _Cand(title="Claude Features")]
    assert len(match_titles(cands, "claude")) == 3


def test_empty_match_returns_all():
    cands = [_Cand(title="a"), _Cand(title="b")]
    assert match_titles(cands, "") == cands
    assert match_titles(cands, None) == cands


def test_no_matches_returns_empty():
    cands = [_Cand(title="dogs"), _Cand(title="cats")]
    assert match_titles(cands, "birds") == []


def test_preserves_order():
    cands = [_Cand(title="Z claude one"),
             _Cand(title="A claude two"),
             _Cand(title="M claude three")]
    out = match_titles(cands, "claude")
    assert [c.title for c in out] == [
        "Z claude one", "A claude two", "M claude three",
    ]


def test_whitespace_in_match_kept():
    """'new release' shouldn't match 'newrelease'."""
    cands = [_Cand(title="Newrelease party"),
             _Cand(title="New release announcement")]
    out = match_titles(cands, "new release")
    assert len(out) == 1
    assert out[0].title == "New release announcement"


def test_unicode_works():
    cands = [_Cand(title="Клод новинки"),
             _Cand(title="GPT releases")]
    out = match_titles(cands, "клод")
    assert len(out) == 1
