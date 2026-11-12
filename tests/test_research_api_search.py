"""API-backed research through the command, HTTP and yt-dlp boundaries."""
from datetime import date

import pytest
from click.testing import CliRunner

from skills.neurolearn import youtube_api
from skills.neurolearn.research import pipeline, source
from skills.neurolearn.transcribe import cli


def test_research_uses_exact_search_dates_and_retains_relevance_order(monkeypatch):
    calls = []

    def http(url, params, headers, timeout):
        calls.append((url.rsplit("/", 1)[-1], params))
        if url.endswith("/search"):
            return 200, {"items": [{"id": {"videoId": v}} for v in ["new", "old"]],
                         "nextPageToken": "do-not-follow"}
        return 200, {"items": [
            {"id": vid, "snippet": {"title": vid, "channelTitle": "Creator",
                                    "publishedAt": published},
             "contentDetails": {"duration": "PT45S"}}
            for vid, published in [("old", "2026-10-10T00:00:00Z"),
                                   ("new", "2026-10-24T23:59:59Z")]
        ]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", lambda *a, **kw: pytest.fail("yt-dlp used"))
    targets = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda **kw: targets.extend(kw["targets"]))
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    result = CliRunner().invoke(cli, [
        "research", "query", "--languages", "en", "--since", "2026-10-10",
        "--until", "2026-10-24", "--limit", "80", "--yes", "--no-analyze",
    ])

    assert result.exit_code == 0, result.exception
    assert [(t.video_id, t.upload_date, t.duration_sec, t.channel) for t in targets] == [
        ("new", date(2026, 10, 24), 45, "Creator"),
        ("old", date(2026, 10, 10), 45, "Creator"),
    ]
    assert [name for name, _ in calls] == ["search", "videos"]
    params = calls[0][1]
    assert params["publishedAfter"] == "2026-10-10T00:00:00Z"
    assert params["publishedBefore"] == "2026-10-24T23:59:59.999999Z"
    assert (params["q"], params["relevanceLanguage"], params["order"]) == (
        "query", "en", "relevance",
    )
    assert params["type"] == "video"
    assert params["maxResults"] == 50


@pytest.mark.parametrize("search_cap,expected_searches", [(1, ["en"]), (2, ["en", "fr"])])
def test_language_searches_share_quota_and_keep_first_occurrence(
    monkeypatch, capsys, search_cap, expected_searches,
):
    from dataclasses import replace
    from datetime import timedelta

    from skills.neurolearn import config
    from skills.neurolearn.youtube_quota import DailyQuota

    cfg = replace(config.DEFAULT_CONFIG, youtube_daily_searches=search_cap)
    config.save_config(cfg, config.CONFIG_PATH)
    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    searches = []

    def http(url, params, headers, timeout):
        if url.endswith("/search"):
            lang = params["relevanceLanguage"]
            searches.append(lang)
            start = date.today() - timedelta(days=14)
            assert params["publishedAfter"] == f"{start}T00:00:00Z"
            return 200, {"items": [{"id": {"videoId": v}} for v in ("shared", lang)]}
        return 200, {"items": [{"id": v} for v in params["id"].split(",")]}

    fallbacks = []

    def extract(url, *, full, limit):
        fallbacks.append(url)
        assert full and limit == 2
        return {"entries": [{"id": "shared"}, {"id": "fr"}]}

    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", extract)
    candidates = source.search_multi_language(
        {"en": "hello", "de": " ", "fr": "bonjour"}, limit=2, days=14,
    )

    assert [(v.video_id, v.source_language) for v in candidates] == [
        ("shared", "en"), ("en", "en"), ("fr", "fr"),
    ]
    assert searches == expected_searches
    assert fallbacks == (["https://www.youtube.com/results?search_query=bonjour&sp=EgIIBA%3D%3D"]
                         if search_cap == 1 else [])
    assert capsys.readouterr().err.count("Falling back") == (1 if search_cap == 1 else 0)
    quota = DailyQuota(config.CONFIG_PATH.parent, cfg).snapshot()
    assert quota["search"]["used"] == quota["general"]["used"] == search_cap


@pytest.mark.parametrize("key,reason", [(None, "no key configured"), ("synthetic", "request failed")])
def test_api_unavailable_runs_preset_once_per_language_with_one_notice(
    monkeypatch, capsys, key, reason,
):
    if key:
        monkeypatch.setenv("YOUTUBE_API_KEY", key)
    requests = []
    extracts = []

    def http(url, params, headers, timeout):
        requests.append(url)
        raise youtube_api.TransientFailure("timed out")

    def extract(url, *, full, limit):
        assert not full and limit == 3
        extracts.append(url)
        return {"entries": [{"id": "shared"}]}

    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", extract)
    results = source.search_multi_language({"en": "hello", "fr": "bonjour"}, limit=3, days=7)
    assert [v.video_id for v in results] == ["shared"]
    assert len(requests) == (1 if key else 0)
    assert len(extracts) == 2
    assert all("sp=EgIIAw%3D%3D" in url for url in extracts)
    assert capsys.readouterr().err.splitlines() == [
        f"YouTube Data API: {reason}. Falling back to yt-dlp.",
    ]
