"""Tests for v0.18.1 self-throttle: yt-dlp presets + config round-trip."""
from pathlib import Path

from skills.neurolearn.utils.downloader import (
    THROTTLE_PRESETS, DEFAULT_THROTTLE, throttle_flags, build_ytdlp_command,
)
from skills.neurolearn.config import Config, _to_toml_dict, _from_toml_dict


def test_throttle_off_is_empty():
    assert throttle_flags("off") == []


def test_throttle_light_has_sleep_and_capped_retries():
    flags = throttle_flags("light")
    assert "--sleep-interval" in flags and "--max-sleep-interval" in flags
    assert "--sleep-subtitles" in flags
    # fragment-retries lowered from yt-dlp's default 10
    i = flags.index("--fragment-retries")
    assert flags[i + 1] == "3"


def test_throttle_unknown_tier_falls_back_to_default():
    assert throttle_flags("bogus") == THROTTLE_PRESETS[DEFAULT_THROTTLE]


def test_throttle_heavy_limits_rate():
    flags = throttle_flags("heavy")
    assert "--limit-rate" in flags
    i = flags.index("--max-sleep-interval")
    assert flags[i + 1] == "90"


def test_build_command_default_off_has_no_sleep(tmp_path: Path):
    cmd = build_ytdlp_command(
        url="https://youtu.be/abc", output_template=str(tmp_path / "a.%(ext)s"),
    )
    assert "--sleep-interval" not in cmd  # default throttle="off"
    assert "-x" in cmd and "https://youtu.be/abc" in cmd


def test_build_command_light_injects_throttle(tmp_path: Path):
    cmd = build_ytdlp_command(
        url="https://youtu.be/abc", output_template=str(tmp_path / "a.%(ext)s"),
        throttle="light",
    )
    assert "--sleep-interval" in cmd
    # core flags still present
    assert "--audio-format" in cmd and "-x" in cmd


def test_config_default_throttle_is_light():
    assert Config().throttle == "light"


def test_config_throttle_roundtrip():
    cfg = Config(throttle="polite")
    loaded = _from_toml_dict(_to_toml_dict(cfg))
    assert loaded.throttle == "polite"


def test_config_invalid_throttle_falls_back_to_light():
    cfg = Config(throttle="garbage")
    loaded = _from_toml_dict(_to_toml_dict(cfg))
    assert loaded.throttle == "light"


def test_subtitle_flags_drop_download_only_flags():
    from skills.neurolearn.utils.downloader import throttle_subtitle_flags
    flags = throttle_subtitle_flags("light")
    # request pacing kept
    assert "--sleep-requests" in flags and "--sleep-subtitles" in flags
    assert "--fragment-retries" in flags
    # per-download flags dropped (no media downloaded for subtitles)
    assert "--sleep-interval" not in flags
    assert "--max-sleep-interval" not in flags
    # heavy drops the rate cap too
    assert "--limit-rate" not in throttle_subtitle_flags("heavy")


def test_download_audio_threads_cfg_throttle(tmp_path):
    """download_audio must hand cfg.throttle down to the per-attempt builder."""
    from unittest.mock import patch
    from skills.neurolearn.utils import downloader
    captured = {}

    def _fake_once(url, output_dir, *, cookies_file, timeout_seconds, throttle):
        captured["throttle"] = throttle
        return tmp_path / "audio.m4a"

    with patch.object(downloader, "_download_audio_once", side_effect=_fake_once):
        downloader.download_audio(
            "https://www.youtube.com/watch?v=abc", tmp_path,
            cfg=Config(throttle="polite"),
        )
    assert captured["throttle"] == "polite"


def test_factory_subtitles_backend_gets_throttle():
    from skills.neurolearn.backends.factory import build_backend
    be = build_backend("subtitles", Config(throttle="polite"))
    assert be.throttle == "polite"
