from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from skills.youtube_transcribe.utils.downloader import (
    is_url,
    is_youtube_url,
    extract_youtube_video_id,
    build_ytdlp_command,
    DownloadError,
)


def test_is_url_true_for_http():
    assert is_url("https://youtu.be/dQw4w9WgXcQ")


def test_is_url_false_for_path():
    assert not is_url("C:/videos/file.mp4")
    assert not is_url("/home/user/file.mp3")


def test_is_youtube_url_short():
    assert is_youtube_url("https://youtu.be/abc123")


def test_is_youtube_url_long():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc123")


def test_is_youtube_url_false_for_vimeo():
    assert not is_youtube_url("https://vimeo.com/12345")


def test_extract_video_id_short():
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_long():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "dQw4w9WgXcQ"


def test_build_ytdlp_command_basic(tmp_path: Path):
    cmd = build_ytdlp_command(
        url="https://youtu.be/abc",
        output_template=str(tmp_path / "audio.%(ext)s"),
        cookies_browser="",
    )
    assert "yt-dlp" in cmd[0]
    assert "-x" in cmd
    assert "--audio-format" in cmd
    assert "mp3" in cmd
    assert "https://youtu.be/abc" in cmd
    assert "--cookies-from-browser" not in cmd  # only added when set


def test_build_ytdlp_command_with_cookies(tmp_path: Path):
    cmd = build_ytdlp_command(
        url="https://youtu.be/abc",
        output_template=str(tmp_path / "audio.%(ext)s"),
        cookies_browser="chrome",
    )
    assert "--cookies-from-browser" in cmd
    assert "chrome" in cmd
