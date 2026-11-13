"""YouTube subscription discovery through the update command."""
import json
from datetime import date, datetime

import pytest

from click.testing import CliRunner

from skills.neurolearn import youtube_api
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.utils.output_writer import Segment
from skills.neurolearn.subscribes import pipeline
from skills.neurolearn.subscribes.store import Channel, load_subscribes, save_subscribes
from skills.neurolearn.transcribe import cli


def channel(name="example", **kwargs):
    return Channel(f"https://www.youtube.com/@{name}", f"@{name}", f"UC{name}",
                   None, "2026-03-01", **kwargs)


def upload(video_id, timestamp):
    return {
        "contentDetails": {"videoId": video_id, "videoPublishedAt": timestamp},
        "snippet": {"title": f"Title {video_id}", "videoOwnerChannelId": "UCexample"},
    }


def update(*args):
    return CliRunner().invoke(cli, [
        "subscribes", "update", "--yes", "--no-analyze", *args,
    ], catch_exceptions=False)


def test_mixed_update_fetches_durations_only_for_surviving_uploads(tmp_path, monkeypatch):
    path = tmp_path / "subscribes.toml"
    save_subscribes(path, [channel(mode="shorts-and-videos")])
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kwargs: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")
    monkeypatch.setattr(pipeline, "_list_tab_ids", lambda *a, **kw: [])
    captured = []
    def transcribe(target, cfg, **kwargs):
        captured.append(target)
        return TranscriptionResult("Test", [Segment(0, 1, "Test")], "en", "subtitles", 1)
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline", transcribe)

    details_requests = []
    def transport(url, params, headers, timeout):
        if url.endswith("/playlistItems"):
            rows = {
                "UULFexample": [upload("ordinary001", "2026-03-05T11:25:00Z"),
                                upload("oldvideo001", "2026-03-01T15:00:00Z")],
                "UUSHexample": [upload("short000001", "2026-03-05T12:30:00Z"),
                                upload("short000002", "2026-03-04T17:15:00Z")],
            }[params["playlistId"]]
            return 200, {"items": rows, "nextPageToken": "unneeded"}
        assert url.endswith("/videos")
        details_requests.append(set(params["id"].split(",")))
        return 200, {"items": [
            {"id": "short000001", "contentDetails": {"duration": "PT86S"},
             "statistics": {"viewCount": "13"}},
            {"id": "ordinary001", "contentDetails": {"duration": "PT76S"}},
        ]}
    monkeypatch.setattr(youtube_api, "_http_get", transport)

    result = update("--output-dir", str(tmp_path), "--since", "2026-03-05", "--until", "2026-03-05", "--shorts-cap", "1")
    assert result.exit_code == 0
    assert details_requests == [{"ordinary001", "short000001"}]
    assert [(t.url, t.duration_sec, t.upload_date) for t in captured] == [
        ("https://www.youtube.com/shorts/short000001", 86, date(2026, 3, 5)),
        ("https://www.youtube.com/watch?v=ordinary001", 76, date(2026, 3, 5)),
    ]
    manifest = json.loads(next(tmp_path.rglob("manifest.json")).read_text(encoding="utf-8"))
    assert manifest["videos"][0]["statistics"]["view_count"] == 13
    saved, = load_subscribes(path)
    assert (saved.last_seen_video_id, saved.last_seen_published) == (
        "short000001", "2026-03-05T12:30:00+00:00",
    )
    assert "shorts cap of 1 reached" in result.output


def install_tabs(monkeypatch, rows, failure=None):
    """Serve equivalent dated uploads from the API transport and yt-dlp tab seams."""
    tab_calls = []
    if failure != "no-key":
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")

    def transport(url, params, headers, timeout):
        if failure == "no-key":
            pytest.fail("no-key runs must not contact the Data API")
        if url.endswith("/playlistItems"):
            tab = {"UULF": "videos", "UUSH": "shorts"}[params["playlistId"][:4]]
            tab_calls.append(("API", tab))
            return 200, {"items": [upload(vid, stamp) for vid, stamp in rows[tab]]}
        assert url.endswith("/videos")
        if failure == "quota":
            return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        if failure == "invalid":
            return 400, {"error": {"errors": [{"reason": "keyInvalid"}]}}
        if failure == "transient":
            raise youtube_api.TransientFailure("connection timed out")
        if failure == "missing-duration":
            return 200, {"items": []}
        return 200, {"items": [
            {"id": vid, "contentDetails": {"duration": "PT42S"}} for vid in params["id"].split(",")
        ]}

    def list_ids(url, *, tab, **kwargs):
        tab_calls.append(("yt-dlp", tab))
        return [vid for vid, _ in rows[tab]]

    def extract(vid, *, as_short, **kwargs):
        tab = "shorts" if as_short else "videos"
        prefix = "shorts/" if as_short else "watch?v="
        return pipeline._ChannelVideo(
            vid, f"https://www.youtube.com/{prefix}{vid}", f"Title {vid}", 42,
            datetime.fromisoformat(dict(rows[tab])[vid]),
        )

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    monkeypatch.setattr(pipeline, "_list_tab_ids", list_ids)
    monkeypatch.setattr(pipeline, "_extract_tab_metadata", extract)
    return tab_calls


@pytest.mark.parametrize("mode,videos,shorts,until,expected,tabs", [
    ("auto", [("ordinary001", 5)], [("short000001", 6)], 6,
     ["watch?v=ordinary001"], ["videos"]),
    ("auto", [("oldvideo001", 1)], [("short000001", 4)], 6,
     ["shorts/short000001"], ["videos", "shorts"]),
    ("videos-only", [("ordinary001", 5)], [("short000001", 6)], 6,
     ["watch?v=ordinary001"], ["videos"]),
    ("shorts-only", [("ordinary001", 5)], [("short000001", 6)], 6,
     ["shorts/short000001"], ["shorts"]),
    ("shorts-and-videos", [("shared00001", 5), ("ordinary001", 4)],
     [("shared00001", 5), ("short000001", 3)], 6,
     ["shorts/shared00001", "watch?v=ordinary001", "shorts/short000001"], ["videos", "shorts"]),
    # An upload newer than --until is skipped; the walk continues into the window.
    ("videos-only", [("toonew00001", 7), ("ordinary001", 5)], [], 6,
     ["watch?v=ordinary001"], ["videos"]),
])
def test_equivalent_update_modes_and_override_state(
    tmp_path, monkeypatch, mode, videos, shorts, until, expected, tabs,
):
    rows = {tab: [(vid, f"2026-03-{day:02d}T12:00:00Z") for vid, day in items]
            for tab, items in (("videos", videos), ("shorts", shorts))}
    path = tmp_path / "subscribes.toml"
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    captured = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda *, targets, **kw: captured.extend(t.url for t in targets))
    save_subscribes(path, [channel(mode=mode, last_seen_video_id="prior",
                                   last_seen_published="2026-03-01T12:00:00+00:00")])
    for failure, provider in (("no-key", "yt-dlp"), (None, "API")):
        calls = install_tabs(monkeypatch, rows, failure)
        captured.clear()
        result = update("--since", "2026-03-02", "--until", f"2026-03-{until:02d}", "--shorts-cap", "0")
        assert result.exit_code == 0, result.output
        assert captured == ["https://www.youtube.com/" + item for item in expected]
        assert calls == [(provider, tab) for tab in tabs]
        assert load_subscribes(path)[0].last_seen_video_id == "prior"


@pytest.mark.parametrize("failure,reason", [
    ("no-key", "no key configured"), ("quota", "quota exhausted"),
    ("invalid", "key rejected"), ("transient", "request failed"),
    ("missing-duration", "request failed"),
])
def test_fallback_restarts_each_channel_and_shares_one_notice(tmp_path, monkeypatch, failure, reason):
    path = tmp_path / "subscribes.toml"
    save_subscribes(path, [channel(name, mode="videos-only", last_seen_video_id="old",
                                   last_seen_published="2026-03-05T10:00:00+00:00")
                           for name in ("first", "second")])
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kwargs: None)
    captured = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda *, targets, **kw: captured.extend(t.video_id for t in targets))
    calls = install_tabs(monkeypatch, {
        "videos": [("newvideo001", "2026-03-05T11:00:00Z"), ("old", "2026-03-05T10:00:00Z")],
        "shorts": [],
    }, failure)
    result = update()

    assert result.exit_code == 0, result.output
    assert result.output.count("Falling back to yt-dlp") == 1
    assert reason in result.output
    assert calls.count(("yt-dlp", "videos")) == 2
    assert captured == ["newvideo001", "newvideo001"]
    assert [ch.last_seen_published for ch in load_subscribes(path)] == [
        "2026-03-05T11:00:00+00:00", "2026-03-05T11:00:00+00:00",
    ]


def _past_window_update(tmp_path, monkeypatch, *, with_key):
    path = tmp_path / "subscribes.toml"
    save_subscribes(path, [channel(mode="videos-only")])
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kwargs: None)
    captured = []
    def transcribe(target, cfg, **kwargs):
        captured.append(target.video_id)
        return TranscriptionResult("Test", [Segment(0, 1, "Test")], "en", "subtitles", 1)
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline", transcribe)
    dates = {"newest00001": "2026-03-20", "inwindow001": "2026-03-10",
             "inwindow002": "2026-03-06", "tooold00001": "2026-03-01", "neverseen01": "2026-02-01"}
    probed = []
    if with_key:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")
        monkeypatch.setattr(pipeline, "_list_tab_ids", lambda *a, **kw: pytest.fail("yt-dlp"))
        def transport(url, params, headers, timeout):
            if url.endswith("/playlistItems"):
                return 200, {"items": [upload(v, d + "T10:00:00Z") for v, d in dates.items()]}
            return 200, {"items": [{"id": v, "contentDetails": {"duration": "PT5M"}}
                                   for v in params["id"].split(",")]}
        monkeypatch.setattr(youtube_api, "_http_get", transport)
    else:
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        monkeypatch.setattr(pipeline, "_list_video_ids", lambda *a, **kw: list(dates))
        def extract(video_id, *, cookies_file=None):
            probed.append(video_id)
            return pipeline._ChannelVideo(
                video_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}", title=video_id,
                duration_sec=300, published=datetime.fromisoformat(dates[video_id] + "T10:00:00+00:00"),
            )
        monkeypatch.setattr(pipeline, "_extract_video_metadata", extract)
    result = update("--output-dir", str(tmp_path), "--since", "2026-03-05", "--until", "2026-03-15")
    assert result.exit_code == 0, result.output
    return captured, probed


@pytest.mark.parametrize("with_key", [True, False])
def test_past_window_skips_newer_uploads_and_returns_the_window(tmp_path, monkeypatch, with_key):
    captured, probed = _past_window_update(tmp_path, monkeypatch, with_key=with_key)
    assert sorted(captured) == ["inwindow001", "inwindow002"]
    if not with_key:
        # The walk still ends at the first upload older than the window.
        assert probed == ["newest00001", "inwindow001", "inwindow002", "tooold00001"]


def _three_channel_update(tmp_path, monkeypatch, broken=None):
    path = tmp_path / "subscribes.toml"
    names = ("first", "second", "third")
    save_subscribes(path, [channel(name, mode="videos-only", last_seen_video_id="old",
                                   last_seen_published="2026-03-05T10:00:00+00:00") for name in names])
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kwargs: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-only")
    captured, details_requests, site = [], [], []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda *, targets, **kw: captured.extend(t.video_id for t in targets))

    def transport(url, params, headers, timeout):
        if url.endswith("/playlistItems"):
            name = params["playlistId"][4:]
            if name == broken:
                return 500, {"error": {"errors": [{"reason": "backendError"}]}}
            return 200, {"items": [upload(f"new-{name}", "2026-03-05T11:00:00Z"),
                                   upload("old", "2026-03-05T10:00:00Z")]}
        details_requests.append(sorted(params["id"].split(",")))
        return 200, {"items": [{"id": vid, "contentDetails": {"duration": "PT42S"}}
                               for vid in params["id"].split(",")]}

    def list_ids(url, **kwargs):
        site.append(url)
        return ["site-video"]

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    monkeypatch.setattr(pipeline, "_list_tab_ids", list_ids)
    monkeypatch.setattr(pipeline, "_extract_tab_metadata", lambda vid, **kw: pipeline._ChannelVideo(
        vid, f"https://www.youtube.com/watch?v={vid}", vid, 42,
        datetime.fromisoformat("2026-03-05T11:00:00+00:00")))
    result = update()
    assert result.exit_code == 0, result.output
    return captured, details_requests, site, result.output


def test_all_channels_share_one_details_request_and_keep_their_order(tmp_path, monkeypatch):
    captured, details_requests, site, _ = _three_channel_update(tmp_path, monkeypatch)
    assert captured == ["new-first", "new-second", "new-third"]
    assert details_requests == [["new-first", "new-second", "new-third"]]
    assert site == []


def test_one_channel_listing_failure_falls_back_alone(tmp_path, monkeypatch):
    captured, details_requests, site, output = _three_channel_update(tmp_path, monkeypatch, broken="second")
    assert captured == ["new-first", "site-video", "new-third"]
    assert details_requests == [["new-first", "new-third"]]
    assert site == ["https://www.youtube.com/@second"]
    assert output.count("Falling back to yt-dlp") == 1
