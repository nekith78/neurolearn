"""Standalone comments command with only the YouTube HTTP transport replaced."""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from skills.neurolearn import youtube_api
from skills.neurolearn.transcribe import cli


VIDEO_ID = "abcdefghijk"
URL = f"https://youtu.be/{VIDEO_ID}"


def test_comments_disabled_is_a_normal_outcome(monkeypatch, tmp_path):
    def disabled(url, params, headers, timeout):
        assert url.endswith("/commentThreads")
        return 403, {"error": {"errors": [{"reason": "commentsDisabled"}]}}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", disabled)
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "comments are disabled" in result.output.lower()
    assert not list(tmp_path.iterdir())


def _comment(comment_id, author, channel_id, likes, text):
    return {"id": comment_id, "snippet": {
        "authorDisplayName": author,
        "authorChannelId": {"value": channel_id},
        "likeCount": likes,
        "publishedAt": "2026-01-02T03:04:05Z",
        "textDisplay": text,
    }}


def test_api_relevance_order_and_inline_replies_reach_both_files(monkeypatch, tmp_path):
    threads = [
        {"snippet": {"channelId": "UCowner", "totalReplyCount": 12,
                     "topLevelComment": _comment("A", "@first", "UCa", 1, "one\ntwo")},
         "replies": {"comments": [_comment("R", "@creator", "UCowner", 3, "hello")]}},
        {"snippet": {"channelId": "UCowner", "totalReplyCount": 0,
                     "topLevelComment": _comment("B", "@other", "UCb", 91, "x" * 800)}},
    ]
    thread_calls = []

    def transport(url, params, headers, timeout):
        if url.endswith("/videos"):
            return 200, {"items": [{"id": VIDEO_ID, "statistics": {"commentCount": "312"}}]}
        assert url.endswith("/commentThreads")
        thread_calls.append(params)
        return 200, {"items": threads, "nextPageToken": "ignore-at-default-cap"}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(thread_calls) == 1
    assert thread_calls[0]["maxResults"] == 100
    assert thread_calls[0]["order"] == "relevance"
    assert thread_calls[0]["videoId"] == VIDEO_ID
    assert thread_calls[0]["textFormat"] == "plainText"
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    first, second = data["comments"]
    assert first["id"] == "A"
    assert first["reply_count"] == 12
    assert first["is_channel_owner"] is False
    assert first["published_at"] == "2026-01-02T03:04:05Z"
    assert first["text"] == "one\ntwo"
    assert first["replies"][0]["is_channel_owner"] is True
    assert second["text"] == "x" * 800
    header, line, reply, last = (tmp_path / f"{VIDEO_ID}.comments.txt").read_text("utf-8").splitlines()
    for fragment in ("source=api", "order=relevance", "cap=100", "fetched=2"):
        assert fragment in header
    assert line == "1 | @first | - | one two"
    assert reply == "  3 | @creator | owner | hello"
    assert last.startswith("91 | @other | - | ")
    assert last.endswith("…")
    assert len(last) < 800


@pytest.mark.parametrize(("statistics", "total", "label"), [
    ({"commentCount": "312"}, 312, "312"),
    ({"commentCount": "0"}, 0, "0"),
    ({}, None, "unknown"),
])
def test_video_total_is_reported_in_configured_directory(monkeypatch, tmp_path, statistics, total, label):
    from skills.neurolearn.config import Config, save_config

    def transport(url, params, headers, timeout):
        if url.endswith("/videos"):
            return 200, {"items": [{"id": VIDEO_ID, "statistics": statistics}]}
        return 200, {"items": []}

    output_dir = tmp_path / "configured"
    config_path = tmp_path / "config.toml"
    save_config(Config(output_dir=str(output_dir)), config_path)
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", config_path)
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL])
    assert result.exit_code == 0, result.output
    data = json.loads((output_dir / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert data["total"] == total
    assert data["fetched"] == 0
    assert f"total={label}" in (output_dir / f"{VIDEO_ID}.comments.txt").read_text("utf-8")


def test_unknown_video_is_reported_clearly(monkeypatch, tmp_path):
    def transport(url, params, headers, timeout):
        return 404, {"error": {"errors": [{"reason": "videoNotFound"}]}}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL, "--output-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "video not found" in result.output.lower()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(("order", "api_order", "first"), [
    ("newest", "time", "0"),
    ("likes", "relevance", "100"),
])
def test_custom_order_pages_only_to_top_level_cap(monkeypatch, tmp_path, order, api_order, first):
    pages = []

    def transport(url, params, *_):
        if url.endswith("/videos"):
            return 200, {"items": []}
        assert params["order"] == api_order
        start = 100 if params.get("pageToken") == "more" else 0
        pages.append(params["maxResults"])
        items = [
            {"snippet": {"topLevelComment": _comment(str(i), "a", "UCa", i, "text"),
                         "totalReplyCount": 0}}
            for i in range(start, start + params["maxResults"])
        ]
        return 200, {"items": items, "nextPageToken": "more"}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL, "--comment-count", "101",
                                      "--comment-order", order, "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert (data["order"], data["cap"], data["fetched"]) == (order, 101, 101)
    assert data["comments"][0]["id"] == first
    assert pages == [100, 1]


def test_full_replies_follows_reply_pages_only_for_incomplete_threads(monkeypatch, tmp_path):
    def thread(parent, total):
        return {"snippet": {"topLevelComment": _comment(parent, "Viewer", "UCv", 0, "post"),
                            "totalReplyCount": total},
                "replies": {"comments": [_comment("inline" + parent, "Owner", "UCx", 0, "reply")]}}

    reply_pages = []
    def transport(url, params, *_):
        if url.endswith("/videos"):
            return 200, {"items": []}
        if url.endswith("/commentThreads"):
            return 200, {"items": [thread("A", 2), thread("B", 1)]}
        assert url.endswith("/comments") and params["parentId"] == "A"
        reply_pages.append(params.get("pageToken"))
        if "pageToken" not in params:
            return 200, {"items": [_comment("inlineA", "Owner", "UCx", 0, "reply")],
                         "nextPageToken": "next"}
        return 200, {"items": [_comment("extra", "Viewer", "UCv", 5, "second reply")]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL, "--comment-full-replies", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert [[r["id"] for r in c["replies"]] for c in data["comments"]] == [["inlineA", "extra"], ["inlineB"]]
    assert data["replies_mode"] == "full"
    assert reply_pages == [None, "next"]


def test_disappearing_reply_thread_keeps_sample_and_discloses_missing_replies(monkeypatch, tmp_path):
    def transport(url, params, *_):
        if url.endswith("/commentThreads"):
            return 200, {"items": [{"snippet": {"topLevelComment": _comment("A", "a", "UCa", 1, "post"),
                                                "totalReplyCount": 2}}]}
        if url.endswith("/videos"):
            return 200, {"items": []}
        return 404, {"error": {"errors": [{"reason": "commentNotFound"}]}}

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-credential")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    result = CliRunner().invoke(cli, ["comments", URL, "--comment-full-replies", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / f"{VIDEO_ID}.comments.json").read_text("utf-8"))
    assert data["source"] == "api" and data["replies_mode"] == "partial"
    assert data["comments"][0]["id"] == "A" and data["notes"]
