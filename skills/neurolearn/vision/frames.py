"""Extract keyframes from video via ffmpeg.

Two extraction modes:

  • `extract_keyframes(start, end, count)` — evenly spaced inside a
    window. Used by smart / standard / premium presets (lectures, reviews,
    arbitrary visual moments).

  • `extract_keyframes_asymmetric(event_ts)` — three offsets relative to
    a speech event: `-1.5s` (before), `+0.3s` (the action — accounts for
    motor lag between speech and click), `+2.0s` (UI settled after). Used
    by the tutorial preset where the interesting frame is offset from
    when the speaker says the action word.

JPEG quality is capped at q:3 (~80% — LLMs don't see the difference)
and width is downscaled to 1280px (UI tutorials don't need 4K). For
text-heavy content (IDE / code) callers can pass `max_width=1920`.

Output naming: <video_id>_<seconds>.jpg under out_dir/frames/.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


_FFMPEG_TIMEOUT_S = 120  # seconds — guard a hung ffmpeg keyframe extraction
# JPEG quality in ffmpeg's -q:v scale (1=best, 31=worst). v0.23: q:2
# (~90%, near-lossless) — keyframes get cropped to small tooltip regions and
# embedded in PDFs, where q:3 ringing on text was visible. Still far smaller
# than PNG. Gemini downsamples server-side (media_resolution LOW) so the
# extra detail costs it nothing.
_DEFAULT_JPEG_QUALITY = 2
# v0.23: 1920px (was 1280) so a 1080p source keeps full width — a cropped
# tooltip then has ~50% more pixels and stays sharp when embedded.
_DEFAULT_MAX_WIDTH = 1920


def _tmp_pattern(out_dir: Path) -> Path:
    """Pattern for ffmpeg output files (overridable in tests)."""
    return out_dir / "tmp_%04d.jpg"


def _vf_filter(max_width: int) -> str:
    """Single ffmpeg -vf filter clause that downscales while preserving aspect.
    `-1` height makes ffmpeg compute height to keep aspect ratio."""
    return f"scale='min({max_width},iw)':-2"


def extract_keyframes(
    video_path: Path,
    start: float,
    end: float,
    count: int,
    out_dir: Path,
    video_id: str,
    max_width: int = _DEFAULT_MAX_WIDTH,
    jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
) -> list[Path]:
    """Extract <count> evenly-spaced keyframes from [start, end] window.

    Files named <video_id>_<sec>.jpg in out_dir.
    Returns list of created file paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = max(end - start, 0.1)
    fps = count / duration

    pattern = _tmp_pattern(out_dir)
    # `-ss` BEFORE `-i` = fast input seeking (~50ms precision, 100× faster
    # than output seeking). `-q:v` controls JPEG quality. The scale filter
    # downscales — `min(W,iw)` so we don't accidentally upscale tiny inputs.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(video_path),
        "-vf", f"fps={fps},{_vf_filter(max_width)}",
        "-frames:v", str(count),
        "-q:v", str(jpeg_quality),
        # v0.10.6: force full-range YUV for the mjpeg encoder. Without
        # this, ffmpeg 8.x reports "Non full-range YUV is non-standard"
        # and refuses to encode, intermittently dropping keyframes
        # from the vision pipeline.
        "-pix_fmt", "yuvj420p",
        str(pattern),
    ]
    subprocess.run(cmd, check=True, timeout=_FFMPEG_TIMEOUT_S)

    # Rename tmp_NNNN.jpg → <video_id>_<sec>.jpg
    tmp_files = sorted(out_dir.glob("tmp_*.jpg"))
    out_paths: list[Path] = []
    for idx, tmp in enumerate(tmp_files):
        sec = int(start + idx / fps)
        new_path = out_dir / f"{video_id}_{sec:05d}.jpg"
        tmp.rename(new_path)
        out_paths.append(new_path)
    return out_paths


# Default asymmetric offsets — speech-anchored. -1.5s captures the
# "before" state, +0.3s captures the action moment (motor lag between
# speech and physical click is ~200–400ms), +2.0s captures the UI
# settled response. Sourced from tutorial-pipeline production guidance.
_TUTORIAL_OFFSETS = (-1.5, 0.3, 2.0)


def extract_keyframes_asymmetric(
    video_path: Path,
    event_ts: float,
    out_dir: Path,
    video_id: str,
    offsets: tuple[float, ...] = _TUTORIAL_OFFSETS,
    max_width: int = _DEFAULT_MAX_WIDTH,
    jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
) -> list[Path]:
    """Extract one frame per offset relative to `event_ts`.

    `event_ts` is the moment in the video when the speaker said the action
    word. Default offsets `-1.5 / +0.3 / +2.0` give the canonical
    "before / action / after" trio for UI tutorials. Frames written to
    out_dir as <video_id>_<sec>.jpg.

    Negative offsets are clamped to 0.0 (don't seek before video start).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for offset in offsets:
        ts = max(0.0, event_ts + offset)
        # One frame at this exact timestamp via output-frame limit.
        # Each call is a separate ffmpeg invocation — three windows is
        # cheap (each takes ~100ms with input seeking).
        out_path = out_dir / f"{video_id}_{int(ts):05d}.jpg"
        # Skip-if-exists: the filename is deterministic for a given
        # (video_id, second), so a non-empty frame already on disk means a
        # prior call extracted it. Reuse it instead of re-running ffmpeg —
        # matters when Claude re-requests overlapping moments on demand.
        if out_path.exists() and out_path.stat().st_size > 0:
            paths.append(out_path)
            continue
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{ts:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", str(jpeg_quality),
            "-vf", _vf_filter(max_width),
            # v0.10.6: see extract_keyframes for rationale on -pix_fmt.
            "-pix_fmt", "yuvj420p",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=_FFMPEG_TIMEOUT_S)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Skip frames we can't extract (e.g. past end of video) —
            # never fail the whole annotation pipeline over one frame.
            continue
        if out_path.exists():
            paths.append(out_path)
    return paths


def frame_sharpness(path: Path) -> float:
    """Variance of the Laplacian — a standard blur/detail metric. Higher means
    sharper / more edge detail. A fully-shown crisp tooltip scores higher than
    a motion-blur transition or a faded-out overlay, so it lets us pick the
    frame where the on-screen info is actually legible."""
    from PIL import Image, ImageFilter, ImageStat
    try:
        with Image.open(path) as im:
            lap = im.convert("L").filter(ImageFilter.Kernel(
                (3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128,
            ))
            return float(ImageStat.Stat(lap).var[0])
    except Exception:
        return 0.0


def extract_sharpest_frame(
    video_path: Path,
    event_ts: float,
    out_dir: Path,
    video_id: str,
    *,
    window: float = 2.0,
    samples: int = 6,
    max_width: int = _DEFAULT_MAX_WIDTH,
    jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
) -> Path | None:
    """Sample several frames in a window around `event_ts` and keep the
    sharpest as `<video_id>_<sec>.jpg`.

    Fixes the "tooltip caught mid-fade / mid-transition" problem: instead of
    one blind offset we look at a few candidates (forward-weighted, because a
    tooltip appears a beat after the speech) and pick the one with the most
    edge detail. Returns the kept frame, or None if nothing extracted.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{video_id}_{int(max(0.0, event_ts)):05d}.jpg"
    if final.exists() and final.stat().st_size > 0:
        return final  # already chosen on a prior call

    start = max(0.0, event_ts - window * 0.4)
    n = max(2, samples)
    cands = [start + window * i / (n - 1) for i in range(n)]
    scored: list[tuple[float, Path]] = []
    for i, ts in enumerate(cands):
        tmp = out_dir / f".cand_{video_id}_{int(ts * 1000):08d}_{i}.jpg"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{ts:.3f}", "-i", str(video_path),
            "-frames:v", "1", "-q:v", str(jpeg_quality),
            "-vf", _vf_filter(max_width), "-pix_fmt", "yuvj420p", str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=_FFMPEG_TIMEOUT_S)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        if tmp.exists() and tmp.stat().st_size > 0:
            scored.append((frame_sharpness(tmp), tmp))
    if not scored:
        return None
    scored.sort(key=lambda s: s[0], reverse=True)
    best = scored[0][1]
    best.replace(final)
    for _, t in scored[1:]:
        try:
            t.unlink()
        except OSError:
            pass
    return final
