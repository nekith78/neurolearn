"""Tests for the on-demand frames command core (v0.21 visual-report Pass 2)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.frames_cmd import (
    parse_timestamp, extract_frames_at, resolve_source_video,
)


def test_parse_timestamp_forms():
    assert parse_timestamp("263") == 263.0
    assert parse_timestamp(263) == 263.0
    assert parse_timestamp("4:23") == 263.0
    assert parse_timestamp("1:02:03") == 3723.0
    assert parse_timestamp("0:30") == 30.0
    assert parse_timestamp(12.5) == 12.5


def test_parse_timestamp_rejects_bad():
    for bad in ("", "abc", "4:", ":30", "-5", "1:2:3:4"):
        with pytest.raises(ValueError):
            parse_timestamp(bad)


def _write_manifest(batch: Path, *, url="https://www.youtube.com/watch?v=vid123",
                    video_id="vid123"):
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "manifest.json").write_text(json.dumps({
        "videos": [{"index": 0, "url": url, "video_id": video_id,
                    "title": "T", "files": {}}],
    }), encoding="utf-8")


def test_resolve_source_video_uses_cache(tmp_path):
    batch = tmp_path / "batch"
    _write_manifest(batch)
    src = batch / "source"
    src.mkdir(parents=True)
    cached = src / "video.mp4"
    cached.write_bytes(b"\x00")
    # Cached file present → no download attempted.
    with patch("skills.neurolearn.utils.downloader.download_video") as dl:
        out = resolve_source_video(batch)
    assert out == cached
    dl.assert_not_called()


def test_resolve_source_video_lazy_downloads(tmp_path):
    batch = tmp_path / "batch"
    _write_manifest(batch)
    def fake_dl(url, output_dir, **kw):
        p = Path(output_dir) / "video.mp4"
        p.write_bytes(b"\x00")
        return p
    with patch("skills.neurolearn.utils.downloader.download_video",
               side_effect=fake_dl) as dl:
        out = resolve_source_video(batch)
    dl.assert_called_once()
    assert out.name == "video.mp4"


def test_resolve_source_video_no_url_errors(tmp_path):
    batch = tmp_path / "batch"
    _write_manifest(batch, url="")
    with pytest.raises(ValueError):
        resolve_source_video(batch)


def test_extract_frames_at_dedups_and_returns_relative_paths(tmp_path):
    batch = tmp_path / "batch"
    _write_manifest(batch)
    (batch / "source").mkdir(parents=True)
    (batch / "source" / "video.mp4").write_bytes(b"\x00")

    def fake_extract(*, video_path, event_ts, out_dir, video_id, offsets):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{video_id}_{int(event_ts):05d}.jpg"
        p.write_bytes(b"\x00")
        return [p]

    with patch(
        "skills.neurolearn.vision.frames.extract_keyframes_asymmetric",
        side_effect=fake_extract,
    ) as ex:
        out = extract_frames_at(batch, [263.0, 263.0, 842.0])  # dup 263

    assert ex.call_count == 2  # dedup collapsed the repeated 263
    assert set(out) == {263.0, 842.0}
    # Paths are relative to batch_dir and live under frames/
    for paths in out.values():
        for rel in paths:
            assert rel.startswith("frames/")
            assert (batch / rel).exists()


def test_resolve_source_video_cache_matches_ytdlp_naming(tmp_path):
    """Regression: yt-dlp names the file by its own template (e.g.
    '<id>.mp4'), not 'video.mp4' — cache must still find it, else we
    re-download on every call."""
    batch = tmp_path / "batch"
    _write_manifest(batch, video_id="fUjfRa93BiE")
    src = batch / "source"
    src.mkdir(parents=True)
    (src / "fUjfRa93BiE.mp4").write_bytes(b"\x00")  # realistic yt-dlp name
    with patch("skills.neurolearn.utils.downloader.download_video") as dl:
        out = resolve_source_video(batch)
    assert out.name == "fUjfRa93BiE.mp4"
    dl.assert_not_called()


def test_extract_keyframes_asymmetric_skips_existing(tmp_path):
    """Optimization: if the deterministic frame files already exist, reuse
    them — ffmpeg must NOT run again (avoids redundant re-extraction when
    Claude re-requests overlapping moments)."""
    from unittest.mock import patch as _patch
    from skills.neurolearn.vision import frames as fr
    out = tmp_path / "frames"
    out.mkdir()
    # event_ts=100 with default offsets (-1.5, 0.3, 2.0) -> secs 98, 100, 102
    for sec in (98, 100, 102):
        (out / f"vid_{sec:05d}.jpg").write_bytes(b"\xff\xd8\xff\xe0")  # non-empty JPEG-ish
    with _patch.object(fr.subprocess, "run") as run:
        paths = fr.extract_keyframes_asymmetric(
            video_path=tmp_path / "v.mp4", event_ts=100.0,
            out_dir=out, video_id="vid",
        )
    run.assert_not_called()
    assert len(paths) == 3
