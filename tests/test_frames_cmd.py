"""Tests for the on-demand frames command core (v0.21 visual-report Pass 2)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.frames_cmd import (
    parse_timestamp, extract_frames_at, resolve_source_video, crop_image,
)


def _make_jpg(path, size=(1000, 500)):
    from PIL import Image
    Image.new("RGB", size, (20, 20, 20)).save(path, "JPEG")


def test_crop_image_keeps_region_and_writes_crop(tmp_path):
    """crop_image crops to a normalized 0-1000 box and writes <stem>_crop.jpg."""
    src = tmp_path / "frame.jpg"
    _make_jpg(src, size=(1000, 500))
    out = crop_image(src, (0, 500, 1000, 1000), pad=0.0)  # right half
    assert out == tmp_path / "frame_crop.jpg"
    from PIL import Image
    w, h = Image.open(out).size
    assert abs(w - 500) <= 2 and abs(h - 500) <= 2  # right half of 1000x500


def test_crop_image_rejects_bad_box(tmp_path):
    src = tmp_path / "frame.jpg"
    _make_jpg(src)
    with pytest.raises(ValueError):
        crop_image(src, (0, 800, 1000, 200))  # xmin > xmax
    with pytest.raises(ValueError):
        crop_image(src, (0, 0, 2000, 1000))  # out of 0-1000 range


def test_frame_sharpness_ranks_sharp_over_blurred(tmp_path):
    """A frame with edges scores higher than a flat/blurred one."""
    from PIL import Image, ImageDraw, ImageFilter
    from skills.neurolearn.vision.frames import frame_sharpness

    sharp = tmp_path / "sharp.jpg"
    im = Image.new("RGB", (400, 300), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in range(0, 400, 12):
        d.line([(x, 0), (x, 300)], fill=(255, 255, 255), width=2)
    im.save(sharp, "JPEG", quality=95)

    blurred = tmp_path / "blur.jpg"
    im.filter(ImageFilter.GaussianBlur(6)).save(blurred, "JPEG", quality=95)

    # The property we rely on: a crisp frame outranks a blurred/faded one.
    assert frame_sharpness(sharp) > frame_sharpness(blurred)


def test_extract_sharpest_frame_picks_best_and_cleans_temps(tmp_path, monkeypatch):
    """extract_sharpest_frame samples candidates, keeps the sharpest as
    <id>_<sec>.jpg, and removes the temp candidates."""
    import skills.neurolearn.vision.frames as fm
    from PIL import Image, ImageDraw

    out = tmp_path / "frames"

    def fake_run(cmd, check=True, **kw):
        # The output path is the last arg; write a frame whose sharpness
        # depends on the seek time so one candidate clearly wins.
        ss = float(cmd[cmd.index("-ss") + 1])
        p = Path(cmd[-1]); p.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (200, 150), (0, 0, 0))
        if abs(ss - 10.0) < 0.05:  # the "best" candidate — lots of edges
            d = ImageDraw.Draw(im)
            for x in range(0, 200, 6):
                d.line([(x, 0), (x, 150)], fill=(255, 255, 255), width=1)
        im.save(p, "JPEG", quality=90)
        return __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(returncode=0)

    monkeypatch.setattr(fm.subprocess, "run", fake_run)
    best = fm.extract_sharpest_frame(
        Path("v.mp4"), 10.0, out, "vid", window=2.0, samples=5,
    )
    assert best is not None and best.name == "vid_00010.jpg"
    assert best.exists()
    # No leftover temp candidates.
    assert not list(out.glob(".cand_*"))


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
