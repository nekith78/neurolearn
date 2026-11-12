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
        "--until", "2026-10-24", "--limit", "2", "--yes", "--no-analyze",
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
    assert params["maxResults"] == 2


@pytest.mark.parametrize("search_cap,expected_searches", [(1, ["en"]), (2, ["en", "fr"])])
def test_language_searches_share_quota_and_keep_first_occurrence(
    monkeypatch, capsys, search_cap, expected_searches,
):
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

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
            start = datetime.now(timezone.utc).date() - timedelta(days=14)
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
    assert quota["search"]["used"] == search_cap
    assert quota["general"]["used"] == 2  # Each language supplied one new video.


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


@pytest.mark.parametrize("origin", ["api", "search-quota", "rss"])
def test_search_statistics_reach_picker_and_manifest_from_one_details_request(
    monkeypatch, tmp_path, origin,
):
    import json
    import questionary

    from skills.neurolearn.backends.base import TranscriptionResult
    from skills.neurolearn.utils.output_writer import Segment

    requests = []

    def http(url, params, headers, timeout):
        resource = url.rsplit("/", 1)[-1]
        requests.append(resource)
        if resource == "search":
            return 200, {"items": [{"id": {"videoId": "low"}}]}
        return 200, {"items": [{
            "id": "low", "snippet": {"title": "Demo"},
            "contentDetails": {"duration": "PT41S"},
            "statistics": {"viewCount": "10", "likeCount": "0"},
        }]}

    labels = []

    class Picker:
        def ask(self):
            return [0]

    def checkbox(message, choices):
        labels.extend(choice.title for choice in choices)
        return Picker()

    transcript = TranscriptionResult(
        "Transcript.", [Segment(0, 1, "Transcript.")], "en", "subtitles", 1,
    )
    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    monkeypatch.setattr(youtube_api, "_http_get", http)
    args = ["topic"]
    if origin == "search-quota":
        from dataclasses import replace
        from skills.neurolearn import config
        config.save_config(replace(config.DEFAULT_CONFIG, youtube_daily_searches=0), config.CONFIG_PATH)
        monkeypatch.setattr(source, "_extract", lambda *a, **kw: {"entries": [{"id": "low", "title": "Demo"}]})
    elif origin == "rss":
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from skills.neurolearn.subscribes.rss import RssEntry
        args = ["--in-subscribes"]
        monkeypatch.setattr(pipeline, "load_subscribes", lambda path: [SimpleNamespace(channel_id="UCa", handle="@a")])
        monkeypatch.setattr(pipeline, "fetch_rss", lambda channel: [
            RssEntry("low", "https://youtu.be/low", "Demo", channel, datetime.now(timezone.utc)),
        ])
    monkeypatch.setattr(questionary, "checkbox", checkbox)
    monkeypatch.setattr(pipeline, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline", lambda *a, **kw: transcript)
    result = CliRunner().invoke(cli, [
        "research", *args, "--languages", "en", "--no-analyze", "--backend", "subtitles",
        "--output-dir", str(tmp_path), "--batch-name", "result",
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert all(text in labels[0] for text in ("Views: 10", "Likes: 0", "Comments: —", "41s"))
    manifest = json.loads((tmp_path / "result" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["videos"][0]["statistics"] == {
        "view_count": 10, "like_count": 0, "comment_count": None,
    }
    assert requests == (["search", "videos"] if origin == "api" else ["videos"])


@pytest.mark.parametrize(("flags", "order", "expected"), [
    (["--sort-by-views"], "viewCount", ["popular", "mid", "zero", "hidden"]),
    (["--min-views", "10"], "relevance", ["mid", "popular"]),
    (["--sort-by-views", "--min-views", "0"], "viewCount", ["popular", "mid", "zero"]),
])
def test_view_options_apply_to_all_language_results(monkeypatch, flags, order, expected):
    def http(url, params, headers, timeout):
        if url.endswith("/search"):
            assert params["order"] == order
            ids = ["hidden", "mid"] if params["relevanceLanguage"] == "en" else ["zero", "popular"]
            return 200, {"items": [{"id": {"videoId": vid}} for vid in ids]}
        counts = {"hidden": {}, "mid": {"viewCount": "10"}, "zero": {"viewCount": "0"},
                  "popular": {"viewCount": "100"}}
        return 200, {"items": [{"id": vid, "statistics": counts[vid]}
                               for vid in params["id"].split(",")]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr("skills.neurolearn.research.translator.translate_query",
                        lambda *args, **kwargs: "sujet")
    selected = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda **kw: selected.extend(v.video_id for v in kw["targets"]))
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    result = CliRunner().invoke(cli, [
        "research", "topic", "--languages", "en,fr", "--no-analyze", "--yes", *flags,
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert selected == expected


@pytest.mark.parametrize("flags", [["--sort-by-views"], ["--min-views", "0"]])
def test_popularity_without_key_explains_before_search(monkeypatch, flags):
    monkeypatch.setattr(source, "_extract", lambda *a, **kw: pytest.fail("unexpected search"))
    result = CliRunner().invoke(cli, [
        "research", "topic", "--languages", "en", "--no-analyze", "--yes", *flags,
    ])
    assert result.exit_code == 2
    assert "YouTube API key" in result.output


def test_view_sort_includes_fallback_language_when_search_quota_is_spent(monkeypatch):
    from dataclasses import replace

    from skills.neurolearn import config

    config.save_config(replace(config.DEFAULT_CONFIG, youtube_daily_searches=1), config.CONFIG_PATH)
    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    detail_pages = []

    def http(url, params, headers, timeout):
        if url.endswith("/search"):
            return 200, {"items": [{"id": {"videoId": "first"}}]}
        detail_pages.append(params["id"])
        views = {"first": "10", "fallback": "50"}
        return 200, {"items": [{"id": vid, "statistics": {"viewCount": views[vid]}}
                               for vid in params["id"].split(",")]}

    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", lambda *a, **kw: {"entries": [{"id": "fallback"}]})
    monkeypatch.setattr("skills.neurolearn.research.translator.translate_query",
                        lambda *a, **kw: "sujet")
    selected = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline",
                        lambda **kw: selected.extend(v.video_id for v in kw["targets"]))
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    result = CliRunner().invoke(cli, [
        "research", "topic", "--languages", "en,fr", "--no-analyze", "--yes", "--sort-by-views",
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert selected == ["fallback", "first"]
    assert detail_pages == ["first", "fallback"]


def test_explicit_view_filter_can_use_details_after_search_failure(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    requests = []

    def http(url, params, *_):
        requests.append(url.rsplit("/", 1)[-1])
        if url.endswith("/search"):
            return 503, {"error": {"message": "search unavailable"}}
        return 200, {"items": [{"id": "item", "statistics": {"viewCount": "42"}}]}

    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", lambda *a, **kw: {"entries": [{"id": "item"}]})
    selected = []
    monkeypatch.setattr(pipeline, "_run_batch_pipeline", lambda **kw: selected.extend(kw["targets"]))
    monkeypatch.setattr(pipeline, "_append_history", lambda **kw: None)
    result = CliRunner().invoke(cli, [
        "research", "topic", "--languages", "en", "--no-analyze", "--yes", "--min-views", "20",
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert [v.video_id for v in selected] == ["item"]
    assert requests == ["search", "videos"]


@pytest.mark.parametrize("entry", ["cli", "source"])
def test_relative_api_window_uses_utc_when_the_local_day_is_ahead(monkeypatch, entry):
    from datetime import datetime, timezone

    class LocalDate(date):
        @classmethod
        def today(cls):
            return date(2026, 11, 13)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return datetime(2026, 11, 12, 23, 30, tzinfo=timezone.utc)

    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    for module in (pipeline, source):
        monkeypatch.setattr(module, "date", LocalDate)
        monkeypatch.setattr(module, "datetime", Clock)
    windows = []
    def http(url, params, *_):
        windows.append((params["publishedAfter"], params["publishedBefore"]))
        return 200, {"items": []}
    monkeypatch.setattr(youtube_api, "_http_get", http)
    if entry == "cli":
        result = CliRunner().invoke(cli, [
            "research", "topic", "--languages", "en", "--days", "14", "--yes", "--no-analyze",
        ], catch_exceptions=False)
        assert result.exit_code == 0, result.output
    else:
        source.search_multi_language({"en": "topic"}, days=14, limit=2)
    assert windows == [("2026-10-29T00:00:00Z", "2026-11-12T23:59:59.999999Z")]


def test_search_follows_pages_until_the_limit(monkeypatch):
    """A limit above one page is honoured; each page is one search call."""
    searches = []

    def http(url, params, headers, timeout):
        if url.endswith("/search"):
            searches.append((params["maxResults"], params.get("pageToken")))
            start = 0 if not params.get("pageToken") else 50
            ids = [f"v{n:03d}" for n in range(start, start + params["maxResults"])]
            return 200, {"items": [{"id": {"videoId": v}} for v in ids], "nextPageToken": "page2"}
        return 200, {"items": [{"id": vid, "snippet": {"title": vid}} for vid in params["id"].split(",")]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    monkeypatch.setattr(youtube_api, "_http_get", http)
    monkeypatch.setattr(source, "_extract", lambda *a, **kw: pytest.fail("yt-dlp used"))
    found = source.search_multi_language({"en": "query"}, limit=60)
    assert [c.video_id for c in found] == [f"v{n:03d}" for n in range(60)]
    assert searches == [(50, None), (50, "page2")]


def test_search_within_one_page_makes_one_search_call(monkeypatch):
    searches = []

    def http(url, params, headers, timeout):
        if url.endswith("/search"):
            searches.append(params["maxResults"])
            # A short page with a continuation token must not trigger a second call.
            return 200, {"items": [{"id": {"videoId": f"v{n}"}} for n in range(15)],
                         "nextPageToken": "more"}
        return 200, {"items": [{"id": vid, "snippet": {"title": vid}} for vid in params["id"].split(",")]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "synthetic")
    monkeypatch.setattr(youtube_api, "_http_get", http)
    assert len(source.search_multi_language({"en": "query"}, limit=20)) == 15
    assert searches == [20]
