"""Tests for keyframe extraction. ffmpeg subprocess mocked."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.neurolearn.vision.frames import extract_keyframes


def test_extract_keyframes_calls_ffmpeg(tmp_path):
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    # Pre-create tmp_NNNN.jpg files matching the impl pattern
    for i in range(1, 4):
        (out_dir / f"tmp_{i:04d}.jpg").write_bytes(b"fake jpeg")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = extract_keyframes(
            video_path=Path("input.mp4"),
            start=10.0,
            end=15.0,
            count=3,
            out_dir=out_dir,
            video_id="abc",
        )

    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert "ffmpeg" in cmd[0]
    assert "-ss" in cmd
    assert "10.0" in cmd
    # Returns paths to extracted frames
    assert len(result) == 3


def test_extract_keyframes_sets_pix_fmt_for_mjpeg(tmp_path):
    """v0.10.6: ffmpeg 8.x mjpeg encoder errors on non-full-range YUV
    sources ("Non full-range YUV is non-standard"). We pass
    `-pix_fmt yuvj420p` so the encoder accepts whatever the source
    provides without strict-compliance complaints."""
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    (out_dir / "tmp_0001.jpg").write_bytes(b"fake")

    with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        extract_keyframes(
            video_path=Path("v.mp4"),
            start=1.0, end=2.0, count=1,
            out_dir=out_dir, video_id="x",
        )

    cmd = mock_run.call_args[0][0]
    # The pix_fmt flag must be present, set to the full-range mjpeg variant.
    assert "-pix_fmt" in cmd, f"missing -pix_fmt in ffmpeg call: {cmd}"
    pix_fmt_idx = cmd.index("-pix_fmt")
    assert cmd[pix_fmt_idx + 1] == "yuvj420p", \
        f"expected yuvj420p, got {cmd[pix_fmt_idx + 1]}"


def test_extract_keyframes_asymmetric_sets_pix_fmt(tmp_path):
    """Same pix_fmt fix applies to the asymmetric (per-offset) path
    used by the tutorial preset."""
    from skills.neurolearn.vision.frames import extract_keyframes_asymmetric

    out_dir = tmp_path / "frames"
    out_dir.mkdir()

    captured: list[list[str]] = []
    def fake_run(cmd, **kw):
        captured.append(cmd)
        # Simulate the output file being created so the function moves on.
        for i, arg in enumerate(cmd):
            if arg.endswith(".jpg"):
                Path(arg).write_bytes(b"fake")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        extract_keyframes_asymmetric(
            video_path=Path("v.mp4"),
            event_ts=10.0,
            out_dir=out_dir,
            video_id="x",
        )

    assert captured, "no ffmpeg calls made"
    for cmd in captured:
        assert "-pix_fmt" in cmd
        idx = cmd.index("-pix_fmt")
        assert cmd[idx + 1] == "yuvj420p"


def test_extract_keyframes_renames_with_video_id(tmp_path):
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    (out_dir / "tmp_0001.jpg").write_bytes(b"fake")

    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        paths = extract_keyframes(
            video_path=Path("v.mp4"),
            start=5.0,
            end=10.0,
            count=1,
            out_dir=out_dir,
            video_id="vid123",
        )
    # Renamed files should follow <video_id>_<sec>.jpg pattern
    for p in paths:
        assert p.name.startswith("vid123_")
        assert p.exists()
