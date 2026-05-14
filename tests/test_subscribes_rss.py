"""Tests for subscribes.rss — fetch + parse YouTube channel RSS feeds."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.subscribes.rss import (
    RssEntry,
    parse_rss,
    fetch_rss,
    rss_url_for_channel,
)


FIXTURE = Path(__file__).parent / "data" / "sample_rss.xml"


def test_rss_url_format():
    url = rss_url_for_channel("UC_abc")
    assert url == "https://www.youtube.com/feeds/videos.xml?channel_id=UC_abc"


def test_parse_rss_three_entries():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert len(entries) == 3
    assert entries[0].video_id == "vid111"
    assert entries[0].title == "First video — newest"


def test_parse_rss_published_as_datetime():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].published == datetime(
        2026, 5, 12, 14, 0, 0, tzinfo=timezone.utc,
    )


def test_parse_rss_channel_id():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].channel_id == "UC_abc123"


def test_parse_rss_url():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].url == "https://www.youtube.com/watch?v=vid111"


def test_parse_empty_feed():
    empty = ('<?xml version="1.0"?><feed '
             'xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
             'xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert parse_rss(empty) == []


def test_parse_malformed_returns_empty():
    """Defensive: malformed XML returns empty rather than crashing."""
    assert parse_rss("<not><proper></xml>") == []


def test_fetch_rss_uses_urllib():
    """fetch_rss should fetch via urllib and pass body to parse_rss."""
    body = FIXTURE.read_text(encoding="utf-8")
    with patch(
        "skills.neurolearn.subscribes.rss._http_get",
        return_value=body,
    ) as mock_get:
        out = fetch_rss("UC_abc")
    mock_get.assert_called_once_with(
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC_abc",
        timeout=10.0,
    )
    assert len(out) == 3


def test_fetch_rss_network_error_returns_empty():
    with patch(
        "skills.neurolearn.subscribes.rss._http_get",
        side_effect=OSError("network down"),
    ):
        assert fetch_rss("UC_x") == []


def test_filter_after_published(tmp_path: Path):
    """Helper used by pipeline: entries newer than a reference timestamp."""
    from skills.neurolearn.subscribes.rss import entries_after
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    cutoff = datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc)
    filtered = entries_after(entries, cutoff)
    assert len(filtered) == 1
    assert filtered[0].video_id == "vid111"
