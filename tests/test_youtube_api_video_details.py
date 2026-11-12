"""Tests for `youtube_api.fetch_video_details`.

Only the module's single HTTP transport (`_http_get`) is replaced. Response
bodies follow the `videos.list` shape recorded in
`docs/specs/draft-youtube-data-api.md`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skills.neurolearn import youtube_api
from skills.neurolearn.youtube_api import NotConfigured, QuotaExhausted

FAKE_KEY = "AIzaFAKE-not-a-real-key-0123456789"


def _item(video_id: str, **overrides) -> dict:
    item = {
        "kind": "youtube#video",
        "id": video_id,
        "snippet": {
            "publishedAt": "2026-03-04T15:30:00Z",
            "title": f"Title {video_id}",
            "liveBroadcastContent": "none",
        },
        "contentDetails": {"duration": "PT1H2M3S"},
        "statistics": {
            "viewCount": "1234567",
            "likeCount": "8901",
            "favoriteCount": "0",
            "commentCount": "234",
        },
    }
    item.update(overrides)
    return item


class VideosTransport:
    """Stands in for `_http_get`: answers `videos.list` from a catalogue."""

    def __init__(self, catalogue: dict[str, dict]):
        self.catalogue = catalogue
        self.calls: list[dict] = []

    def __call__(self, url, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params)})
        ids = params["id"].split(",")
        return 200, {"items": [self.catalogue[i] for i in ids if i in self.catalogue]}


@pytest.fixture
def transport(monkeypatch):
    def install(catalogue):
        fake = VideosTransport(catalogue)
        monkeypatch.setattr(youtube_api, "_http_get", fake)
        return fake
    return install


def test_returns_duration_publish_date_and_statistics(transport):
    transport({"vid00000001": _item("vid00000001")})

    details = youtube_api.fetch_video_details(["vid00000001"], api_key=FAKE_KEY)

    d = details["vid00000001"]
    assert d.video_id == "vid00000001"
    assert d.duration_sec == 3723
    assert d.published_at == datetime(2026, 3, 4, 15, 30, tzinfo=timezone.utc)
    assert d.is_live_stream is False
    assert (d.view_count, d.like_count, d.comment_count) == (1234567, 8901, 234)


def test_statistic_the_api_omits_is_none_not_zero(transport):
    # Comments disabled -> no commentCount; likes hidden -> no likeCount.
    transport({"vid00000001": _item("vid00000001", statistics={"viewCount": "0"})})

    d = youtube_api.fetch_video_details(["vid00000001"], api_key=FAKE_KEY)["vid00000001"]

    assert d.view_count == 0
    assert d.like_count is None
    assert d.comment_count is None


def test_missing_sections_stay_absent(transport):
    transport({"vid00000001": {"kind": "youtube#video", "id": "vid00000001"}})

    d = youtube_api.fetch_video_details(["vid00000001"], api_key=FAKE_KEY)["vid00000001"]

    assert d.duration_sec is None
    assert d.published_at is None
    assert (d.view_count, d.like_count, d.comment_count) == (None, None, None)


def test_live_stream_is_flagged(transport):
    transport({
        "vid00000001": _item(
            "vid00000001",
            liveStreamingDetails={"actualStartTime": "2026-03-04T15:30:00Z"},
        ),
    })

    d = youtube_api.fetch_video_details(["vid00000001"], api_key=FAKE_KEY)["vid00000001"]

    assert d.is_live_stream is True


def test_unknown_id_is_left_out(transport):
    transport({"vid00000001": _item("vid00000001")})

    details = youtube_api.fetch_video_details(
        ["vid00000001", "gone0000000"], api_key=FAKE_KEY
    )

    assert set(details) == {"vid00000001"}


def test_ids_are_requested_in_groups_of_50(transport):
    ids = [f"v{n:010d}" for n in range(120)]
    fake = transport({i: _item(i) for i in ids})

    details = youtube_api.fetch_video_details(ids, api_key=FAKE_KEY)

    assert [len(c["params"]["id"].split(",")) for c in fake.calls] == [50, 50, 20]
    assert all(c["url"].endswith("/videos") for c in fake.calls)
    assert list(details) == ids


def test_duplicate_ids_are_requested_once(transport):
    fake = transport({"vid00000001": _item("vid00000001")})

    youtube_api.fetch_video_details(["vid00000001", "vid00000001"], api_key=FAKE_KEY)

    assert [c["params"]["id"] for c in fake.calls] == ["vid00000001"]


def test_no_ids_makes_no_request(transport):
    fake = transport({})

    assert youtube_api.fetch_video_details([], api_key=FAKE_KEY) == {}
    assert fake.calls == []


def test_api_failure_propagates_as_typed_error(monkeypatch):
    body = {"error": {"code": 403, "message": "quota", "errors": [
        {"reason": "quotaExceeded", "domain": "youtube.quota"}]}}
    monkeypatch.setattr(youtube_api, "_http_get", lambda *a, **k: (403, body))

    with pytest.raises(QuotaExhausted):
        youtube_api.fetch_video_details(["vid00000001"], api_key=FAKE_KEY)


def test_without_a_key_raises_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")

    with pytest.raises(NotConfigured):
        youtube_api.fetch_video_details(["vid00000001"])


@pytest.mark.parametrize("text, seconds", [
    ("PT1H2M3S", 3723),
    ("PT45S", 45),
    ("PT10M", 600),
    ("PT2H", 7200),
    ("P1DT1H", 90000),
    ("P0D", 0),
    ("PT0S", 0),
])
def test_parse_iso8601_duration(text, seconds):
    assert youtube_api.parse_iso8601_duration(text) == seconds


@pytest.mark.parametrize("text", ["", None, "garbage", "P", "PT", "1:02:03"])
def test_parse_iso8601_duration_rejects_non_durations(text):
    assert youtube_api.parse_iso8601_duration(text) is None
