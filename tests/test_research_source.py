"""Tests for research.source — multi-language yt-dlp search + dedup."""
from datetime import date
from unittest.mock import patch

from skills.youtube_transcribe.research.source import (
    SearchCandidate,
    search_multi_language,
)


def _entry(vid, title, channel="ch", duration=300, upload="20260501"):
    return {
        "id": vid, "title": title, "channel": channel,
        "duration": duration, "upload_date": upload,
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def test_search_single_language():
    """Single language → one yt-dlp call, candidates returned in order."""
    fake_results = {"entries": [_entry("v1", "First"), _entry("v2", "Second")]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake_results,
    ) as mock:
        out = search_multi_language(
            {"en": "Claude features"}, limit=10,
        )
    mock.assert_called_once_with("ytsearch10:Claude features")
    assert len(out) == 2
    assert out[0].video_id == "v1"
    assert out[0].title == "First"


def test_search_multi_language_dedup():
    """Same video_id across languages — dedup keeps first occurrence."""
    def fake_extract(url):
        if "Claude features" in url:
            return {"entries": [_entry("dup", "Claude features"),
                                _entry("en1", "EN only")]}
        elif "Клод" in url:
            return {"entries": [_entry("dup", "Клод фичи"),
                                _entry("ru1", "RU only")]}
        return {"entries": []}

    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
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
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=10)
    assert len(out) == 1
    assert out[0].video_id == "v1"


def test_search_parses_upload_date():
    fake = {"entries": [_entry("v1", "T", upload="20240115")]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].upload_date == date(2024, 1, 15)


def test_search_handles_missing_upload_date():
    fake = {"entries": [{"id": "v1", "title": "T", "url": "u", "channel": "c",
                          "duration": 100}]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
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
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].source_language == "en"
