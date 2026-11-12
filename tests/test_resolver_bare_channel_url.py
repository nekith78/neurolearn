"""A bare YouTube channel URL (`youtube.com/@handle`, no tab) means the
channel's Ordinary Videos.

yt-dlp answers a bare channel URL with the channel's *tabs* (Videos / Live /
Shorts), each carrying the channel id as its `id`. Expanding that as if it
were a video list produced one bogus target whose video id was the channel
id. Tests drive `resolve()` / `batch` and fake only the yt-dlp wrapper.
"""
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from skills.neurolearn.utils.resolver import ResolverFilters, resolve

CHANNEL_ID = "UCrDwWp7EBBv4NwvScIpBDOA"
SEAM = "skills.neurolearn.utils.downloader._extract_flat"


def _tabs_listing() -> dict:
    """What yt-dlp returns for a bare channel URL."""
    return {
        "_type": "playlist", "id": "@anth", "title": "Anth",
        "entries": [
            {"_type": "playlist", "id": CHANNEL_ID, "title": f"Anth - {tab}"}
            for tab in ("Videos", "Live", "Shorts")
        ],
    }


def _video_listing(ids: list[str]) -> dict:
    return {
        "_type": "playlist", "id": CHANNEL_ID, "title": "Anth - Videos",
        "entries": [
            {"id": v, "title": f"Video {v}",
             "url": f"https://www.youtube.com/watch?v={v}"}
            for v in ids
        ],
    }


class FakeYtDlp:
    """Stands in for the yt-dlp wrapper: a URL that names a tab or a
    playlist → a newest-first video list; a bare channel URL → the tabs.
    Records every requested URL."""

    def __init__(self, video_ids: list[str]):
        self.video_ids = video_ids
        self.requested: list[str] = []

    def __call__(self, url: str, *, cookies_file: str | None = None) -> dict:
        self.requested.append(url)
        tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if tail in ("videos", "shorts", "streams") or "list=" in url:
            return _video_listing(self.video_ids)
        return _tabs_listing()


NEWEST_FIRST = ["new3", "new2", "new1", "old0"]


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/@anth",
    "https://youtube.com/@anth/",
    "https://m.youtube.com/@anth",
    "https://www.youtube.com/@anth?si=abc",
    f"https://www.youtube.com/channel/{CHANNEL_ID}",
    "https://www.youtube.com/c/anth",
    "https://www.youtube.com/user/anth",
])
def test_bare_channel_url_yields_ordinary_videos_newest_first(url):
    fake = FakeYtDlp(NEWEST_FIRST)
    with patch(SEAM, side_effect=fake):
        targets, failures = resolve([url], None, ResolverFilters(limit=3))

    assert failures == []
    assert [t.video_id for t in targets] == ["new3", "new2", "new1"]
    assert all(t.source == "channel" for t in targets)
    assert CHANNEL_ID not in {t.video_id for t in targets}
    assert all(CHANNEL_ID not in t.url for t in targets)


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/@anth/videos",
    "https://www.youtube.com/@anth/shorts",
    "https://www.youtube.com/@anth/streams",
    f"https://www.youtube.com/channel/{CHANNEL_ID}/videos",
    "https://www.youtube.com/playlist?list=PLabc",
])
def test_explicit_tab_and_playlist_urls_reach_ytdlp_unchanged(url):
    fake = FakeYtDlp(NEWEST_FIRST)
    with patch(SEAM, side_effect=fake):
        targets, failures = resolve([url], None, ResolverFilters(limit=10))

    assert failures == []
    assert set(fake.requested) == {url}
    assert [t.video_id for t in targets] == NEWEST_FIRST


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/anth/",
    "https://www.tiktok.com/@anth",
    "https://vimeo.com/user/anth",
])
def test_other_platform_profile_urls_reach_ytdlp_unchanged(url):
    fake = FakeYtDlp(NEWEST_FIRST)
    with patch(SEAM, side_effect=fake):
        resolve([url], None, ResolverFilters(limit=10))

    assert set(fake.requested) == {url}


def test_single_video_url_reaches_ytdlp_unchanged():
    url = "https://www.youtube.com/watch?v=abc123"
    video = {"_type": "video", "id": "abc123", "title": "One"}
    with patch(SEAM, return_value=video) as seam:
        targets, failures = resolve([url], None, ResolverFilters())

    assert failures == []
    assert [c.args[0] for c in seam.call_args_list] == [url]
    assert [t.video_id for t in targets] == ["abc123"]


def test_bare_channel_failure_is_reported_against_the_url_the_user_gave():
    from skills.neurolearn.utils.downloader import DownloadError

    url = "https://www.youtube.com/@shorts-only"
    with patch(SEAM, side_effect=DownloadError("no videos tab")):
        targets, failures = resolve([url], None, ResolverFilters())

    assert targets == []
    assert [(f.url, f.error) for f in failures] == [(url, "no videos tab")]


def test_batch_on_bare_channel_url_processes_ordinary_videos(tmp_path):
    """Through the `batch` command: the pipeline receives the channel's
    Ordinary Videos, capped by --limit, never the channel id."""
    from skills.neurolearn.transcribe import cli

    cfg = MagicMock(default_backend="subtitles", language="auto",
                    output_dir=str(tmp_path), keep_audio=False,
                    timestamps=True, srt=True)
    with patch("skills.neurolearn.transcribe.run_wizard"), \
         patch("skills.neurolearn.transcribe.CONFIG_PATH") as cp, \
         patch("skills.neurolearn.transcribe.load_config", return_value=cfg), \
         patch("skills.neurolearn.transcribe._run_batch_pipeline",
               return_value=None) as pipeline, \
         patch(SEAM, side_effect=FakeYtDlp(NEWEST_FIRST)):
        cp.exists.return_value = True
        result = CliRunner().invoke(cli, [
            "batch", "https://www.youtube.com/@anth",
            "--limit", "2", "--backend", "subtitles",
            "--output-dir", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    targets = pipeline.call_args.kwargs["targets"]
    assert [t.video_id for t in targets] == ["new3", "new2"]
    assert [t.url for t in targets] == [
        "https://www.youtube.com/watch?v=new3",
        "https://www.youtube.com/watch?v=new2",
    ]
