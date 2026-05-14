"""Tests for v0.3 --search via yt-dlp ytsearchN:query."""
from datetime import date
from unittest.mock import patch

from skills.neurolearn.utils.downloader import ChannelEntry, search_videos
from skills.neurolearn.utils.resolver import (
    ResolverFilters,
    resolve,
)


def _ce(vid: str, title: str = "T") -> ChannelEntry:
    return ChannelEntry(
        video_id=vid, url=f"https://youtu.be/{vid}",
        title=title, duration_sec=300, upload_date=date(2026, 1, 1),
        channel="C",
    )


def test_search_videos_calls_extract_flat_with_ytsearch_url():
    fake_info = {
        "entries": [
            {"id": "aaa11111111", "title": "Result 1", "duration": 100,
             "upload_date": "20260101", "channel": "Ch1"},
            {"id": "bbb22222222", "title": "Result 2", "duration": 200,
             "upload_date": None, "uploader": "Ch2"},
        ],
    }
    with patch(
        "skills.neurolearn.utils.downloader._extract_flat",
        return_value=fake_info,
    ) as mock_extract:
        out = search_videos("claude tutorial", limit=5)

    # Verify it was called with proper ytsearch URL
    mock_extract.assert_called_once_with("ytsearch5:claude tutorial")
    assert len(out) == 2
    assert out[0].video_id == "aaa11111111"
    assert out[0].title == "Result 1"
    assert out[0].duration_sec == 100
    assert out[0].upload_date == date(2026, 1, 1)
    assert out[0].channel == "Ch1"
    assert out[1].channel == "Ch2"  # uploader fallback


def test_search_videos_empty_query_raises():
    from skills.neurolearn.utils.downloader import DownloadError
    import pytest
    with pytest.raises(DownloadError):
        search_videos("   ", limit=5)
    with pytest.raises(DownloadError):
        search_videos("", limit=5)


def test_search_videos_caps_at_limit():
    fake_info = {
        "entries": [{"id": f"vid{i:08d}", "title": str(i)} for i in range(20)],
    }
    with patch(
        "skills.neurolearn.utils.downloader._extract_flat",
        return_value=fake_info,
    ):
        out = search_videos("query", limit=5)
    assert len(out) == 5


def test_search_videos_skips_entries_without_id():
    fake_info = {
        "entries": [
            {"id": "good"},
            None,
            {"title": "no id"},
            {"id": "good2"},
        ],
    }
    with patch(
        "skills.neurolearn.utils.downloader._extract_flat",
        return_value=fake_info,
    ):
        out = search_videos("query", limit=10)
    assert [e.video_id for e in out] == ["good", "good2"]


def test_resolver_search_query_expands_to_targets(tmp_path):
    """resolve() with filters.search_query=X should call search_videos."""
    fake_entries = [_ce("aaa11111111", "From search")]
    with patch(
        "skills.neurolearn.utils.downloader.search_videos",
        return_value=fake_entries,
    ):
        targets, failures = resolve(
            inputs=[],
            from_file=None,
            filters=ResolverFilters(search_query="claude tutorial", limit=5),
        )
    assert len(targets) == 1
    assert targets[0].video_id == "aaa11111111"
    assert targets[0].source == "search"


def test_resolver_search_with_inline_inputs_combines():
    """Inline URLs + --search → both contribute."""
    fake_entries = [_ce("search1234567")]
    fake_video_info = {
        "id": "inline123456",
        "title": "Inline video",
        "duration": 100,
        "upload_date": "20260101",
        "channel": "Ch",
    }
    with patch(
        "skills.neurolearn.utils.downloader.search_videos",
        return_value=fake_entries,
    ), patch(
        "skills.neurolearn.utils.resolver.probe_input",
        return_value=("video", fake_video_info),
    ):
        targets, _ = resolve(
            inputs=["https://youtu.be/inline123456"],
            from_file=None,
            filters=ResolverFilters(search_query="x", limit=5),
        )
    video_ids = sorted(t.video_id for t in targets if t.video_id)
    assert "search1234567" in video_ids
    assert "inline123456" in video_ids


def test_resolver_search_failure_recorded_as_resolve_failure():
    """If search_videos raises, failure goes into ResolveFailure list."""
    with patch(
        "skills.neurolearn.utils.downloader.search_videos",
        side_effect=RuntimeError("network down"),
    ):
        targets, failures = resolve(
            inputs=[],
            from_file=None,
            filters=ResolverFilters(search_query="x", limit=5),
        )
    assert len(targets) == 0
    assert len(failures) == 1
    assert "network down" in failures[0].error


def test_resolver_no_inputs_no_search_raises():
    """No inputs + no search query → CLIInputError."""
    from skills.neurolearn.utils.resolver import CLIInputError
    import pytest
    with pytest.raises(CLIInputError):
        resolve([], from_file=None, filters=ResolverFilters())


def test_resolver_only_search_no_inline_works():
    """Just --search with no inline URLs is valid (search-only mode)."""
    fake_entries = [_ce("aaa11111111")]
    with patch(
        "skills.neurolearn.utils.downloader.search_videos",
        return_value=fake_entries,
    ):
        targets, _ = resolve(
            inputs=[],
            from_file=None,
            filters=ResolverFilters(search_query="claude", limit=5),
        )
    assert len(targets) == 1
