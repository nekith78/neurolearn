"""Tests for research.source — multi-language yt-dlp search + dedup."""
from datetime import date
from unittest.mock import patch

from skills.neurolearn.research.source import (
    SearchCandidate,
    _build_search_url,
    _pick_sp_preset,
    search_multi_language,
)


def _entry(vid, title, channel="ch", duration=300, upload="20260501"):
    return {
        "id": vid, "title": title, "channel": channel,
        "duration": duration, "upload_date": upload,
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def test_search_single_language():
    """Single language, no date filter → uses ytsearchN: shortcut."""
    fake_results = {"entries": [_entry("v1", "First"), _entry("v2", "Second")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake_results,
    ) as mock:
        out = search_multi_language(
            {"en": "Claude features"}, limit=10,
        )
    # No `days` → fast path: ytsearchN: shortcut, flat extract.
    call = mock.call_args
    assert call.args[0] == "ytsearch10:Claude features"
    assert call.kwargs.get("full") is False
    assert len(out) == 2
    assert out[0].video_id == "v1"
    assert out[0].title == "First"


def test_search_multi_language_dedup():
    """Same video_id across languages — dedup keeps first occurrence."""
    def fake_extract(url, **_kw):
        if "Claude features" in url:
            return {"entries": [_entry("dup", "Claude features"),
                                _entry("en1", "EN only")]}
        elif "Клод" in url:
            return {"entries": [_entry("dup", "Клод фичи"),
                                _entry("ru1", "RU only")]}
        return {"entries": []}

    with patch(
        "skills.neurolearn.research.source._extract",
        side_effect=fake_extract,
    ):
        out = search_multi_language(
            {"en": "Claude features", "ru": "Клод фичи"}, limit=10,
        )
    video_ids = [c.video_id for c in out]
    # Dup appears once; en1 and ru1 also present
    assert "dup" in video_ids
    assert video_ids.count("dup") == 1
    assert "en1" in video_ids
    assert "ru1" in video_ids


def test_search_skip_entries_without_id():
    """Some yt-dlp results may have None id — skip them."""
    fake = {"entries": [_entry("v1", "OK"), {"id": None, "title": "broken"},
                        None]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=10)
    assert len(out) == 1
    assert out[0].video_id == "v1"


def test_search_parses_upload_date():
    fake = {"entries": [_entry("v1", "T", upload="20240115")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].upload_date == date(2024, 1, 15)


def test_search_handles_missing_upload_date():
    fake = {"entries": [{"id": "v1", "title": "T", "url": "u", "channel": "c",
                          "duration": 100}]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].upload_date is None


def test_search_empty_queries():
    out = search_multi_language({}, limit=10)
    assert out == []


def test_search_attaches_language_to_candidates():
    """Each candidate remembers which language search produced it (for diagnostics)."""
    fake = {"entries": [_entry("v1", "T")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].source_language == "en"


# ── SP filter (built-in YouTube date filter) ─────────────────────────────


def test_pick_sp_preset_exact_matches():
    """Exact preset matches return the corresponding SP code."""
    assert _pick_sp_preset(1) == ("EgIIAg%3D%3D", 1)
    assert _pick_sp_preset(7) == ("EgIIAw%3D%3D", 7)
    assert _pick_sp_preset(30) == ("EgIIBA%3D%3D", 30)
    assert _pick_sp_preset(365) == ("EgIIBQ%3D%3D", 365)


def test_pick_sp_preset_rounds_up():
    """Non-preset values round UP to the nearest preset."""
    assert _pick_sp_preset(2) == ("EgIIAw%3D%3D", 7)    # 2 → 1 week
    assert _pick_sp_preset(14) == ("EgIIBA%3D%3D", 30)  # 14 → 1 month
    assert _pick_sp_preset(90) == ("EgIIBQ%3D%3D", 365) # 90 → 1 year
    assert _pick_sp_preset(180) == ("EgIIBQ%3D%3D", 365)


def test_pick_sp_preset_too_large_returns_none():
    """Anything beyond 1 year has no SP equivalent."""
    assert _pick_sp_preset(366) is None
    assert _pick_sp_preset(10_000) is None


def test_pick_sp_preset_invalid_inputs_return_none():
    assert _pick_sp_preset(0) is None
    assert _pick_sp_preset(-5) is None


def test_build_search_url_without_sp():
    url = _build_search_url("AI agents", None)
    assert url == "https://www.youtube.com/results?search_query=AI+agents"


def test_build_search_url_with_sp():
    url = _build_search_url("AI agents", "EgIIBA%3D%3D")
    assert "search_query=AI+agents" in url
    assert "sp=EgIIBA%3D%3D" in url
    assert url.startswith("https://www.youtube.com/results?")


def test_build_search_url_encodes_special_chars():
    """Cyrillic / spaces / & must be URL-encoded."""
    url = _build_search_url("Клод & фичи", None)
    assert " " not in url
    assert "%D0%9A" in url  # 'К' encoded
    # Bare ampersand must not survive — it would break the query string.
    assert "& " not in url


def test_search_uses_sp_url_when_days_set_and_exact_preset():
    """--days 30 → exact 1mo preset → SP URL, flat extract (fast path)."""
    fake_results = {"entries": [_entry("v1", "Recent")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake_results,
    ) as mock:
        out = search_multi_language(
            {"en": "Claude features"}, limit=5, days=30,
        )
    url_arg = mock.call_args.args[0]
    assert "youtube.com/results" in url_arg
    assert "sp=EgIIBA%3D%3D" in url_arg
    # Exact preset match → no need to refine → flat extract.
    assert mock.call_args.kwargs.get("full") is False
    assert len(out) == 1


def test_search_uses_full_extract_when_days_not_exact_preset():
    """--days 14 → nearest preset 1mo, but tighter → full extract for upload_date."""
    fake_results = {"entries": [_entry("v1", "Recent")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake_results,
    ) as mock:
        search_multi_language(
            {"en": "Claude"}, limit=5, days=14,
        )
    # Custom days → full extract so upload_date is populated for refinement.
    assert mock.call_args.kwargs.get("full") is True
    assert "sp=EgIIBA%3D%3D" in mock.call_args.args[0]


def test_search_no_days_keeps_ytsearch_shortcut():
    """No days → fast ytsearchN: shortcut, no SP filter."""
    fake_results = {"entries": [_entry("v1", "T")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake_results,
    ) as mock:
        search_multi_language({"en": "x"}, limit=5)
    assert mock.call_args.args[0] == "ytsearch5:x"
    assert mock.call_args.kwargs.get("full") is False


def test_search_days_over_year_falls_back_to_ytsearch():
    """--days 730 has no SP equivalent → use ytsearchN: shortcut."""
    fake_results = {"entries": [_entry("v1", "T")]}
    with patch(
        "skills.neurolearn.research.source._extract",
        return_value=fake_results,
    ) as mock:
        search_multi_language({"en": "x"}, limit=5, days=730)
    url_arg = mock.call_args.args[0]
    assert url_arg.startswith("ytsearch5:")
    assert "sp=" not in url_arg
