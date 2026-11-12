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
