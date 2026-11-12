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
