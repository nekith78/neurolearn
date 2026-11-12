from datetime import datetime, timezone

import pytest

from skills.neurolearn import youtube_api as api


def playlist_item(video_id, published="2026-05-01", channel_id="UCcreator"):
    return {
        "contentDetails": {"videoId": video_id, "videoPublishedAt": published + "T12:00:00Z"},
        "snippet": {"title": video_id, "videoOwnerChannelId": channel_id,
                    "videoOwnerChannelTitle": "Creator", "publishedAt": "2026-10-01T00:00:00Z"},
    }


@pytest.mark.parametrize(("publication_type", "playlist_id"), [
    ("all", "UUcreator"), ("videos", "UULFcreator"),
    ("shorts", "UUSHcreator"), ("streams", "UULVcreator"),
])
def test_uploads_keep_membership_order_and_video_publish_dates(monkeypatch, publication_type, playlist_id):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        assert url.endswith("/playlistItems") and params["playlistId"] == playlist_id
        if not params.get("pageToken"):
            return 200, {"items": [playlist_item("one")], "nextPageToken": "second"}
        assert params["pageToken"] == "second"
        return 200, {"items": [playlist_item("two", "2025-01-01")], "nextPageToken": "unused"}
    monkeypatch.setattr(api, "_http_get", transport)
    rows = list(api.iter_channel_uploads("UCcreator", publication_type, limit=2))
    assert [(row.video_id, row.title, row.channel_id, row.channel_title) for row in rows] == [
        ("one", "one", "UCcreator", "Creator"), ("two", "two", "UCcreator", "Creator"),
    ]
    assert rows[1].published_at == datetime(2025, 1, 1, 12, tzinfo=timezone.utc)


def test_only_missing_per_type_playlist_is_empty(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    monkeypatch.setattr(api, "_http_get", lambda *args: (
        404, {"error": {"errors": [{"reason": "playlistNotFound"}]}},
    ))
    assert list(api.iter_channel_uploads("UCcreator", "streams")) == []
    with pytest.raises(api.NotFound):
        list(api.iter_playlist_videos("PLmissing"))


def run_batch(monkeypatch, tmp_path, *args):
    from click.testing import CliRunner
    from skills.neurolearn import transcribe

    targets = []
    monkeypatch.setattr(transcribe, "CONFIG_PATH", tmp_path / "config.toml")
    transcribe.CONFIG_PATH.touch()
    def pipeline(**kwargs):
        targets.extend(kwargs["targets"])
        assert not kwargs["opts"]["initial_failures"], kwargs["opts"]["initial_failures"]
    monkeypatch.setattr(transcribe, "_run_batch_pipeline", pipeline)
    result = CliRunner().invoke(transcribe.cli, [
        "batch", *args, "--backend", "subtitles", "--output-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    return targets, result.output


def test_batch_window_applies_to_first_n_per_channel_before_duration_and_shorts_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if url.endswith("/playlistItems"):
            assert params["playlistId"] == "UULFcreator" and params["maxResults"] == 4
            return 200, {"items": [
                playlist_item("new", "2026-06-01"), playlist_item("first", "2026-05-15"),
                playlist_item("last", "2026-05-01"), playlist_item("old", "2026-04-01"),
            ], "nextPageToken": "outside-limit"}
        if url.endswith("/videos"):
            return 200, {"items": [
                {"id": "first", "contentDetails": {"duration": "PT30S"}},
                {"id": "last", "contentDetails": {"duration": "PT2M"}},
            ]}
        pytest.fail(url)
    monkeypatch.setattr(api, "_http_get", transport)
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: pytest.fail("yt-dlp"))
    rows, output = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/@creator",
                             "--limit", "4", "--since", "2026-05-01", "--until", "2026-05-15",
                             "--max-duration", "60", "--no-shorts")
    assert [(r.video_id, r.upload_date.isoformat(), r.duration_sec) for r in rows] == [
        ("first", "2026-05-15", 30),
    ]
    assert "Falling back" not in output


def test_batch_playlist_keeps_custom_order_and_uses_owner_membership_for_no_shorts(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        if url.endswith("/playlistItems"):
            if params["playlistId"] == "PLcustom":
                return 200, {"items": [
                    playlist_item("old", "2024-04-01"), playlist_item("regular", "2025-05-01"),
                    playlist_item("tall", "2025-04-01", "UCother"),
                ]}
            if params["playlistId"] == "UUSHother" and params["videoId"] == "tall":
                return 200, {"items": [{"id": "membership"}]}
            assert params["playlistId"] == "UUSHcreator" and params["videoId"] == "regular"
            return 404, {"error": {"errors": [{"reason": "playlistNotFound"}]}}
        if url.endswith("/videos"):
            return 200, {"items": [
                {"id": "regular", "contentDetails": {"duration": "PT40S"}},
                {"id": "tall", "contentDetails": {"duration": "PT86S"}},
            ]}
        pytest.fail(url)
    monkeypatch.setattr(api, "_http_get", transport)
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: pytest.fail("yt-dlp"))
    rows, _ = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/playlist?list=PLcustom",
                        "--since", "2025-01-01", "--no-shorts")
    assert [r.video_id for r in rows] == ["regular"]


@pytest.mark.parametrize(("failure", "reason"), [
    ("no-key", "no key configured"), ("quota", "quota exhausted"),
    ("invalid", "key rejected"), ("timeout", "request failed"),
])
def test_batch_falls_back_and_reports_undated_targets_once(monkeypatch, tmp_path, failure, reason):
    if failure != "no-key":
        monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(*args):
        if failure == "quota":
            return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        if failure == "invalid":
            return 400, {"error": {"errors": [{"reason": "keyInvalid"}]}}
        if failure == "timeout":
            raise api.TransientFailure("timed out")
        pytest.fail("No HTTP request without a key")
    monkeypatch.setattr(api, "_http_get", transport)
    def yt_dlp(url, **kwargs):
        vid = "one" if "@one/" in url else "two"
        return {"_type": "playlist", "entries": [{"id": vid}, {"id": "old", "upload_date": "20240130"}]}
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", yt_dlp)
    rows, output = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/@one",
                             "https://www.youtube.com/@two/videos", "--since", "2025-10-10")
    assert [r.video_id for r in rows] == ["one", "two"]
    assert output.count(reason) == output.count("Falling back") == 1
    assert output.count("date filter") == 1


@pytest.mark.parametrize(("extra", "expected"), [
    ([], ["https://www.youtube.com/shorts/tall"]), (["--no-shorts"], []),
])
def test_batch_explicit_shorts_tab_uses_shorts_urls(monkeypatch, tmp_path, extra, expected):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if url.endswith("/playlistItems"):
            assert params["playlistId"] == "UUSHcreator"
            return 200, {"items": [playlist_item("tall")]}
        if url.endswith("/videos"):
            return 200, {"items": [{"id": "tall", "contentDetails": {"duration": "PT86S"}}]}
        pytest.fail(url)
    monkeypatch.setattr(api, "_http_get", transport)
    rows, _ = run_batch(monkeypatch, tmp_path, "https://youtube.com/@creator/shorts", *extra)
    assert [r.url for r in rows] == expected


def test_batch_discards_partial_api_result_on_later_page_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if "pageToken" in params:
            return 500, {"error": {"message": "try later"}}
        return 200, {"items": [playlist_item("partial")], "nextPageToken": "later"}
    monkeypatch.setattr(api, "_http_get", transport)
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: {
        "_type": "playlist", "entries": [{"id": "fallback", "upload_date": "20260515"}],
    })
    rows, output = run_batch(monkeypatch, tmp_path, "https://youtube.com/@creator",
                             "--since", "2026-05-01", "--until", "2026-05-15")
    assert [r.video_id for r in rows] == ["fallback"]
    assert "Falling back" in output and "date filter" not in output


def test_batch_manifest_reuses_statistics_from_playlist_resolution(monkeypatch, tmp_path):
    import json
    from click.testing import CliRunner
    from skills.neurolearn import transcribe
    from skills.neurolearn.backends.base import TranscriptionResult
    from skills.neurolearn.utils.output_writer import Segment

    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    config = tmp_path / "config.toml"
    config.write_text("onboarding_complete = true\n", encoding="utf-8")
    monkeypatch.setattr(transcribe, "CONFIG_PATH", config)
    transcript = TranscriptionResult("Talk", [Segment(0, 1, "Talk")], "en", "subtitles", 1)
    monkeypatch.setattr(transcribe, "run_pipeline", lambda *args, **kwargs: transcript)
    requests = []

    def transport(url, params, headers, timeout):
        if url.endswith("/playlistItems"):
            return 200, {"items": [playlist_item("abcdefghijk")]}
        assert url.endswith("/videos")
        requests.append(params["id"])
        if len(requests) == 1:
            return 200, {"items": [{"id": "abcdefghijk", "statistics": {"viewCount": "42"}}]}
        return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}

    monkeypatch.setattr(api, "_http_get", transport)
    result = CliRunner().invoke(transcribe.cli, [
        "batch", "https://www.youtube.com/playlist?list=PLdemo", "--backend", "subtitles",
        "--output-dir", str(tmp_path), "--batch-name", "study",
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    video, = json.loads((tmp_path / "study/manifest.json").read_text(encoding="utf-8"))["videos"]
    assert video["statistics"] == {"view_count": 42, "like_count": None, "comment_count": None}
    assert requests == ["abcdefghijk"]
