"""Exercise the fallback through the CLI and yt-dlp's no-download boundary."""
import json

import pytest
import yt_dlp
from click.testing import CliRunner

from skills.neurolearn import config, youtube_api
from skills.neurolearn.transcribe import cli


VIDEO_ID = "abcdefghijk"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def fake_ytdlp(monkeypatch, outcomes):
    calls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def extract_info(self, url, *, download, process):
            calls.append(self.options)
            assert url.startswith("https://www.youtube.com/watch?v=")
            assert not download and not process
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return {
                "comment_count": 912,
                "__post_extractor": lambda: {
                    "comment_count": len(outcome) if outcome is not None else None,
                    "comments": outcome,
                },
            }

        post_extract = staticmethod(yt_dlp.YoutubeDL.post_extract)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return calls


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "no-key")
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", config_path)
    return config_path


@pytest.mark.parametrize(("status", "reason", "notice"), [
    (None, "", "no key configured"),
    (403, "quotaExceeded", "quota exhausted"),
    (503, "backendError", "request failed"),
    (400, "keyInvalid", "key rejected"),
])
def test_unavailable_api_writes_bounded_approximate_sample(
    monkeypatch, tmp_path, isolated, status, reason, notice,
):
    def transport(*_):
        assert status is not None, "Anonymous runs must not call the API"
        return status, {"error": {"errors": [{"reason": reason}]}}

    if status is not None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-credential")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    calls = fake_ytdlp(monkeypatch, iter([[
        {"id": "A", "parent": "root", "text": "one", "like_count": 1230,
         "timestamp": 86400, "author": "Author", "author_is_uploader": True},
    ]]))
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.output.count("Falling back to yt-dlp") == 1
    assert notice in result.output
    assert "test-credential" not in result.output
    options, = calls
    assert options["getcomments"] and options["skip_download"]
    assert "cookiefile" not in options
    yt_args = options["extractor_args"]["youtube"]
    assert yt_args["comment_sort"] == ["top"]
    assert int(yt_args["max_comments"][1]) == 100
    assert int(yt_args["max_comments"][0]) == 100
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert data["source"] == "yt-dlp"
    assert data["approximate_fields"] == ["like_count", "published_at"]
    assert data["fetched"] == 1 and data["total"] == 912
    parent, = data["comments"]
    assert parent["like_count"] == 1230
    assert parent["published_at"] == "1970-01-02T00:00:00Z"
    assert parent["is_channel_owner"] is True
    header = (tmp_path / f"{VIDEO_ID}.comments.txt").read_text("utf-8").splitlines()[0]
    assert "source=yt-dlp" in header and "approximate" in header


@pytest.mark.parametrize(("error", "retry"), [
    ("Sign in to confirm you're not a bot", True),
    ("Sign in to confirm you’re not a bot", True),
    ("HTTP Error 429: Too Many Requests", True),
    ("Video unavailable", False),
    ("Connection timed out", False),
])
def test_only_site_blocks_retry_with_registered_cookies(monkeypatch, tmp_path, isolated, error, retry):
    cookies = tmp_path / "youtube-cookies.txt"
    cookies.touch()
    config.save_config(config.Config(youtube_cookies_file=str(cookies)), isolated)
    calls = fake_ytdlp(monkeypatch, iter([yt_dlp.utils.DownloadError(error), []]))
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])
    assert [opts.get("cookiefile") for opts in calls] == ([None, str(cookies)] if retry else [None])
    if retry:
        assert result.exit_code == 0, result.output
        assert (tmp_path / f"{VIDEO_ID}.comments.txt").is_file()
    else:
        assert result.exit_code == 1
        assert "Could not fetch comments" in result.output
        assert not (tmp_path / f"{VIDEO_ID}.comments.txt").exists()


def test_shared_run_reports_rejected_key_once_across_videos(monkeypatch, isolated, capsys):
    from skills.neurolearn.comments import fetch_comments
    from skills.neurolearn.youtube_fallback import fallback_notice_for_run

    monkeypatch.setenv("YOUTUBE_API_KEY", "rejected-key")
    monkeypatch.setattr(youtube_api, "_http_get", lambda *_: (401, {}))
    calls = fake_ytdlp(monkeypatch, iter([[], []]))
    notice = fallback_notice_for_run()
    for video_id in (VIDEO_ID, "secondvideo"):
        assert fetch_comments(video_id, notice=notice).source == "yt-dlp"
    output = capsys.readouterr().err
    assert output.count("Falling back to yt-dlp") == 1
    assert output.count("key rejected") == 1
    assert len(calls) == 2


def test_site_reports_disabled_comments_without_artifacts(monkeypatch, tmp_path, isolated):
    fake_ytdlp(monkeypatch, iter([None]))
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Comments are disabled" in result.output
    assert not list(tmp_path.glob("*.comments.*"))


@pytest.mark.parametrize(("order", "site_sort", "first"), [("newest", "new", "A"), ("likes", "top", "B")])
def test_site_options_bound_parents_group_replies_and_keep_marks(monkeypatch, tmp_path, isolated, order, site_sort, first):
    calls = fake_ytdlp(monkeypatch, iter([[
        {"id": "A", "parent": "root", "text": "first", "like_count": 2, "is_pinned": True},
        {"id": "R", "parent": "A", "text": "reply", "is_favorited": True},
        {"id": "B", "parent": "root", "text": "second", "like_count": 9},
    ]]))
    result = CliRunner().invoke(cli, ["comments", URL, "--comment-count", "2", "--comment-order", order,
                                      "--comment-full-replies", "--comment-markers", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    args = calls[0]["extractor_args"]["youtube"]
    assert args["comment_sort"] == [site_sort]
    assert int(args["max_comments"][1]) == 2 and int(args["max_comments"][0]) >= 3
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert (data["cap"], data["fetched"], data["order"]) == (2, 2, order)
    assert data["comments"][0]["id"] == first
    parent = next(c for c in data["comments"] if c["id"] == "A")
    assert parent["is_pinned"] is True
    reply, = parent["replies"]
    assert reply["id"] == "R" and reply["creator_heart"] is True
    assert len(calls) == 1
    compact = (tmp_path / f"{VIDEO_ID}.comments.txt").read_text("utf-8")
    assert "pinned" in compact and "creator-heart" in compact


@pytest.mark.parametrize("site_error", [False, True])
def test_api_markers_preserve_api_sample_and_only_apply_matching_ids(monkeypatch, tmp_path, isolated, site_error):
    def record(comment_id):
        return {"id": comment_id, "snippet": {"textDisplay": "API text", "likeCount": 15}}

    def transport(url, *_):
        if url.endswith("/videos"):
            return 200, {"items": []}
        return 200, {"items": [
            {"snippet": {"topLevelComment": record("A"), "totalReplyCount": 1},
             "replies": {"comments": [record("R")]}},
            {"snippet": {"topLevelComment": record("B"), "totalReplyCount": 0}},
        ]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    outcome = yt_dlp.utils.DownloadError("network unavailable") if site_error else [
        {"id": "A", "parent": "root", "is_pinned": True, "text": "Other text", "like_count": 1},
        {"id": "R", "parent": "A", "is_favorited": True},
        {"id": "C", "parent": "root", "is_pinned": True},
    ]
    calls = fake_ytdlp(monkeypatch, iter([outcome]))
    runner = CliRunner()
    base = ["comments", URL, "--comment-count", "2", "--output-dir", str(tmp_path)]
    assert runner.invoke(cli, base).exit_code == 0
    assert calls == []
    result = runner.invoke(cli, [*base, "--comment-markers"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    a, b = data["comments"]
    assert (a["id"], a["text"], a["like_count"], b["id"]) == ("A", "API text", 15, "B")
    assert data["source"] == "api" and b["is_pinned"] is None
    assert data["markers"] == ("unavailable" if site_error else "partial")
    assert a["is_pinned"] is (None if site_error else True)
    assert a["replies"][0]["creator_heart"] is (None if site_error else True)


def test_site_full_replies_preserves_nested_discussion(monkeypatch, tmp_path, isolated):
    calls = fake_ytdlp(monkeypatch, iter([[
        {"id": "A", "parent": "root", "text": "topic"},
        {"id": "R", "parent": "A", "text": "answer"},
        {"id": "N", "parent": "R", "text": "nested answer"},
    ]]))
    result = CliRunner().invoke(cli, ["comments", URL, "--comment-full-replies", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    root, = data["comments"]
    assert [(reply["id"], reply["parent_id"]) for reply in root["replies"]] == [("R", "A"), ("N", "R")]
    assert int(calls[0]["extractor_args"]["youtube"]["max_comments"][4]) >= 3
    assert "nested answer" in (tmp_path / f"{VIDEO_ID}.comments.txt").read_text("utf-8")
