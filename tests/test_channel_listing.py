import json

import pytest
from click.testing import CliRunner

from skills.neurolearn import youtube_api as api
from skills.neurolearn.transcribe import cli


def listing(*args):
    return CliRunner().invoke(cli, ["channel-list", "@creator", *args])


def test_listing_without_key_explains_setup_and_exits_cleanly(monkeypatch):
    monkeypatch.setattr(api, "_http_get", lambda *args: pytest.fail("unexpected API request"))
    result = listing("--json")
    assert result.exit_code == 0, result.output
    assert "YouTube API key" in result.stderr
    assert "config set-key youtube --from-file" in result.stderr
    assert result.stdout == ""


def upload(video_id, day, title):
    return {
        "contentDetails": {"videoId": video_id, "videoPublishedAt": f"{day}T12:00:00Z"},
        "snippet": {"title": title, "videoOwnerChannelId": "UCcreator"},
    }


def test_listing_merges_types_chronologically_and_limits_after_date_filter(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    playlists = {
        "UULFcreator": [upload("outside", "2026-06-06", "New"), upload("ordinary", "2026-05-01", "Talk")],
        "UUSHcreator": [upload("short", "2026-05-31", "Snippet")],
        "UULVcreator": [upload("stream", "2026-05-11", "Live"), upload("old", "2025-01-01", "Old")],
    }

    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if url.endswith("/playlistItems"):
            return 200, {"items": playlists[params["playlistId"]]}
        if url.endswith("/videos"):
            assert set(params["id"].split(",")) == {"ordinary", "short", "stream"}
            return 200, {"items": [
                {"id": "ordinary", "contentDetails": {"duration": "PT20S"}, "statistics": {"viewCount": "84000"}},
                {"id": "short", "contentDetails": {"duration": "PT2M"}, "statistics": {"viewCount": "10", "likeCount": "0"}},
            ]}
        pytest.fail(url)

    monkeypatch.setattr(api, "_http_get", transport)
    result = listing("--json", "--limit", "3", "--since", "2026-05-01", "--until", "2026-05-31")
    assert result.exit_code == 0, (result.output, result.exception)
    rows = json.loads(result.stdout)
    assert [(row["video_id"], row["publication_type"]) for row in rows] == [
        ("short", "shorts"), ("stream", "streams"), ("ordinary", "videos"),
    ]
    assert rows[0] == {
        "video_id": "short", "url": "https://www.youtube.com/shorts/short", "title": "Snippet",
        "published_at": "2026-05-31T12:00:00+00:00", "publication_type": "shorts",
        "duration_sec": 120, "view_count": 10, "like_count": 0, "comment_count": None,
    }
    assert rows[1]["title"] == "Live" and rows[1]["view_count"] is None


def test_type_filter_pages_only_requested_type_and_hydrates_in_batches(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    calls = []

    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {}}]}
        if url.endswith("/playlistItems"):
            assert params["playlistId"] == "UUSHcreator"
            assert params["maxResults"] == 50
            start = 50 if params.get("pageToken") == "more" else 0
            calls.append(("uploads", start))
            return 200, {"items": [upload(f"v{i}", "2026-05-10", "Short") for i in range(start, start + 50)],
                         "nextPageToken": "unused" if start else "more"}
        if url.endswith("/videos"):
            ids = params["id"].split(",")
            calls.append(("details", len(ids)))
            return 200, {"items": [{"id": video_id} for video_id in ids]}
        pytest.fail(url)

    monkeypatch.setattr(api, "_http_get", transport)
    result = listing("--type", "shorts", "--limit", "51", "--json")
    assert result.exit_code == 0, (result.output, result.exception)
    assert [r["video_id"] for r in json.loads(result.stdout)] == [f"v{i}" for i in range(51)]
    assert sorted(calls) == [("details", 1), ("details", 50), ("uploads", 0), ("uploads", 50)]


def test_table_keeps_visible_title_and_statistics_and_stops_at_start_date(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")

    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {}}]}
        if url.endswith("/playlistItems"):
            assert params["playlistId"] == "UULFcreator" and "pageToken" not in params
            return 200, {"items": [upload("one", "2026-02-01", "[bold]"),
                                    upload("old", "2025-01-01", "Too old")],
                         "nextPageToken": "outside-window"}
        assert url.endswith("/videos") and params["id"] == "one"
        return 200, {"items": [{"id": "one", "statistics": {"viewCount": "100", "commentCount": "0"},
                                "contentDetails": {"duration": "PT76S"}}]}

    monkeypatch.setattr(api, "_http_get", transport)
    result = listing("--publication-type", "videos", "--since", "2026-02-01")
    assert result.exit_code == 0, (result.output, result.exception)
    for label in ("Title", "Published", "Type", "Duration", "Views", "Likes", "Comments"):
        assert label in result.stdout
    for cell in ("[bold]", "2026-02-01", "videos", "76", "100", "-", "0"):
        assert cell in result.stdout


@pytest.mark.parametrize(("status", "body", "message"), [
    (200, {"items": []}, "Channel not found"),
    (403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}, "quota exhausted"),
    (400, {"error": {"errors": [{"reason": "keyInvalid"}]}}, "key rejected"),
    (503, {"error": {}}, "request failed"),
])
def test_api_failures_are_reported_without_partial_json(monkeypatch, status, body, message):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    monkeypatch.setattr(api, "_http_get", lambda *args: (status, body))
    result = listing("--json")
    assert result.exit_code == 1
    assert message in result.stderr
    assert result.stdout == ""


def test_reversed_date_window_rejected_before_spending_quota(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    monkeypatch.setattr(api, "_http_get", lambda *args: pytest.fail("invalid window spent quota"))
    result = listing("--since", "2026-05-02", "--until", "2026-05-01")
    assert result.exit_code == 2
    assert "--since" in result.stderr and "--until" in result.stderr
