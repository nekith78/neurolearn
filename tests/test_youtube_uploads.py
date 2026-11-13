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


def test_batch_window_applies_before_duration_and_shorts_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if url.endswith("/playlistItems"):
            # A date window is filled from eligible uploads, so the page is not cut to --limit.
            assert params["playlistId"] == "UULFcreator" and params["maxResults"] == 50
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


@pytest.mark.parametrize(("path", "duration", "keep"), [
    ("@creator", 40, True), ("@creator/videos", 40, True), ("@creator/streams", 40, True),
    ("c/creator/shorts", 90, False), ("channel/UCcreator/shorts", 90, False),
    ("playlist?list=PLcustom", 40, False),
])
def test_batch_no_shorts_fallback_uses_channel_tab_before_duration(monkeypatch, tmp_path, path, duration, keep):
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *args, **kwargs: {
        "_type": "playlist", "entries": [{"id": "the-video", "duration": duration}],
    })
    rows, _ = run_batch(monkeypatch, tmp_path, f"https://youtube.com/{path}", "--no-shorts")
    assert [r.video_id for r in rows] == (["the-video"] if keep else [])


def _channel_transport(pages, calls):
    def transport(url, params, headers, timeout):
        if url.endswith("/channels"):
            return 200, {"items": [{"id": "UCcreator", "snippet": {"title": "Creator"}}]}
        if url.endswith("/playlistItems"):
            calls.append(dict(params))
            return 200, pages[params.get("pageToken", "")]
        if url.endswith("/videos"):
            return 200, {"items": [{"id": vid, "contentDetails": {"duration": "PT5M"}}
                                   for vid in params["id"].split(",")]}
        pytest.fail(url)
    return transport


def test_batch_limit_counts_uploads_inside_the_until_window(monkeypatch, tmp_path):
    """"2 videos up to 15 May" is the 2 newest eligible uploads, read past newer ones."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    calls = []
    pages = {
        "": {"items": [playlist_item("jul", "2026-07-01"), playlist_item("jun", "2026-06-01")],
             "nextPageToken": "p2"},
        "p2": {"items": [playlist_item("may15", "2026-05-15"), playlist_item("may01", "2026-05-01"),
                         playlist_item("apr", "2026-04-01")], "nextPageToken": "never"},
    }
    monkeypatch.setattr(api, "_http_get", _channel_transport(pages, calls))
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: pytest.fail("yt-dlp"))
    rows, output = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/@creator",
                             "--limit", "2", "--until", "2026-05-15")
    assert [r.video_id for r in rows] == ["may15", "may01"]
    assert [c.get("pageToken") for c in calls] == [None, "p2"]
    assert "Falling back" not in output


def test_batch_window_scan_stops_at_the_first_upload_before_since(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    calls = []
    pages = {"": {"items": [playlist_item("jun", "2026-06-01"), playlist_item("may", "2026-05-10"),
                            playlist_item("apr", "2026-04-01")], "nextPageToken": "never"}}
    monkeypatch.setattr(api, "_http_get", _channel_transport(pages, calls))
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: pytest.fail("yt-dlp"))
    rows, _ = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/@creator",
                        "--limit", "5", "--since", "2026-05-01", "--until", "2026-05-31")
    assert [r.video_id for r in rows] == ["may"]
    assert len(calls) == 1


def test_batch_without_dates_still_requests_only_the_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    calls = []
    pages = {"": {"items": [playlist_item("a"), playlist_item("b"), playlist_item("c")],
                  "nextPageToken": "never"}}
    monkeypatch.setattr(api, "_http_get", _channel_transport(pages, calls))
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat", lambda *a, **kw: pytest.fail("yt-dlp"))
    rows, _ = run_batch(monkeypatch, tmp_path, "https://www.youtube.com/@creator", "--limit", "3")
    assert [r.video_id for r in rows] == ["a", "b", "c"]
    assert [c["maxResults"] for c in calls] == [3]


def _video_item(video_id, duration="PT5M", **extra):
    return {"id": video_id, "contentDetails": {"duration": duration},
            "snippet": {"title": f"Title {video_id}", "channelTitle": "Creator",
                        "publishedAt": "2026-05-01T12:00:00Z", **extra},
            "statistics": {"viewCount": "7"}}


def _resolve_links(monkeypatch, links, items, *, status=200, key=True):
    from skills.neurolearn.utils import resolver

    calls, probed = [], []
    if key:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    def transport(url, params, headers, timeout):
        calls.append((url.rsplit("/", 1)[1], params["id"].split(",")))
        return status, {"items": items} if status == 200 else {"error": {"errors": [{"reason": "backendError"}]}}
    monkeypatch.setattr(api, "_http_get", transport)
    def probe(url):
        probed.append(url)
        return "video", {"id": resolver.extract_youtube_video_id(url), "title": "from yt-dlp", "duration": 9}
    monkeypatch.setattr(resolver, "probe_input", probe)
    targets, failures = resolver.resolve(links, None, resolver.ResolverFilters())
    assert not failures
    return targets, calls, probed


def test_single_video_links_resolve_in_one_details_request(monkeypatch):
    links = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb",
             "https://www.youtube.com/shorts/ccccccccccc"]
    targets, calls, probed = _resolve_links(
        monkeypatch, links, [_video_item(v) for v in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")])
    assert calls == [("videos", ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])] and probed == []
    assert [(t.url, t.title, t.duration_sec, t.channel, t.source, t.statistics["view_count"])
            for t in targets] == [(link, f"Title {vid}", 300, "Creator", "inline", 7)
                                  for link, vid in zip(links, ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"))]
    assert targets[0].upload_date.isoformat() == "2026-05-01"


def test_links_the_api_cannot_describe_go_through_the_probe(monkeypatch):
    links = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=private0000",
             "https://www.youtube.com/live/livenow0000"]
    targets, calls, probed = _resolve_links(monkeypatch, links, [
        _video_item("aaaaaaaaaaa"), _video_item("livenow0000", "P0D", liveBroadcastContent="live")])
    assert len(calls) == 1 and probed == links[1:]
    assert [t.title for t in targets] == ["Title aaaaaaaaaaa", "from yt-dlp", "from yt-dlp"]


def test_single_links_without_a_key_probe_silently(monkeypatch, capsys):
    links = ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
    targets, calls, probed = _resolve_links(monkeypatch, links, [], key=False)
    assert calls == [] and probed == links and targets[0].title == "from yt-dlp"
    assert capsys.readouterr().err == ""


def test_failed_single_link_lookup_falls_back_with_one_notice(monkeypatch, capsys):
    links = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=bbbbbbbbbbb"]
    targets, calls, probed = _resolve_links(monkeypatch, links, [], status=500)
    assert len(calls) == 1 and sorted(probed) == links
    assert capsys.readouterr().err.count("Falling back to yt-dlp") == 1
