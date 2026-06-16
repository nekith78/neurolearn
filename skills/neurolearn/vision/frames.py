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


# --- content-aware candidate ranking (Phase A) ---------------------------
# Variance-of-Laplacian alone favours faces / photos / memes over flat
# diagrams (they carry more high-frequency detail), so a sharpness-only picker
# lands on talking-heads and spliced clips. We instead rank candidates by
# content-type (slide-likeness) and stability (a settled diagram is static; a
# moving head / camera-pan / mid-draw is not), with a face penalty, and use
# sharpness only as a TIE-BREAKER. Every signal is computed on the already-
# decoded candidate JPEGs with the bundled OpenCV toolkit — fully offline, no
# model, no download. Any failure degrades to sharpness-only (returns None) so
# the pipeline never breaks.

_FACE_CASCADE = None


def _face_cascade():
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        import cv2
        _FACE_CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _FACE_CASCADE


def _slide_likeness(bgr) -> float:
    """1.0 = slide-like (few flat colours, low entropy), 0.0 = photographic.
    Colour-discreteness is the strongest single separator of diagram/slide from
    photo/face; intensity entropy backs it up. Edge density is deliberately NOT
    used — text-heavy slides are edge-dense and would be misread as photos."""
    import cv2
    import numpy as np
    small = cv2.resize(bgr, (96, 96), interpolation=cv2.INTER_AREA)
    q = (small // 32).reshape(-1, 3)            # 8 levels / channel
    uniq = int(np.unique(q, axis=0).shape[0])
    colour = max(0.0, 1.0 - uniq / 200.0)       # slide: tens; photo: hundreds
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hist = np.bincount(gray.reshape(-1), minlength=256).astype(float)
    p = hist[hist > 0] / float(gray.size)
    entropy = float(-(p * np.log2(p)).sum())    # 0..8 bits
    flatness = max(0.0, 1.0 - entropy / 8.0)
    return 0.7 * colour + 0.3 * flatness


def _has_large_face(gray) -> bool:
    """A frontal face filling a meaningful share of the frame — the talking-
    head signal. Bundled Haar cascade (offline); minSize gates out tiny
    face-like patterns in diagrams. Used as a penalty, not a hard gate."""
    try:
        h, w = gray.shape[:2]
        faces = _face_cascade().detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=6,
            minSize=(max(1, w // 8), max(1, h // 8)),
        )
        return len(faces) > 0
    except Exception:
        return False


def _stability(grays: list) -> list[float]:
    """Per-candidate 1 - mean|Δ| against neighbouring candidates (on a common
    small grid). A settled diagram barely changes between samples; a moving
    head or a mid-draw diagram does. Returns [0,1], 1 = most static."""
    import cv2
    import numpy as np
    smalls = [
        None if g is None else cv2.resize(g, (64, 64)).astype(np.float32)
        for g in grays
    ]
    out: list[float] = []
    for i, s in enumerate(smalls):
        if s is None:
            out.append(0.0)
            continue
        diffs = [
            float(np.abs(s - smalls[j]).mean()) / 255.0
            for j in (i - 1, i + 1)
            if 0 <= j < len(smalls) and smalls[j] is not None
        ]
        out.append(1.0 - (sum(diffs) / len(diffs) if diffs else 0.0))
    return out


def _rank_candidates(paths: list[Path]) -> list[float] | None:
    """Composite content-aware score per candidate (higher = better). Returns
    None if the CV toolkit is unavailable, so the caller falls back to
    sharpness-only ranking."""
    try:
        import cv2
    except Exception:
        return None
    try:
        bgrs = [cv2.imread(str(p)) for p in paths]
        grays = [None if b is None else cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
                 for b in bgrs]
        stab = _stability(grays)
        sharps = [frame_sharpness(p) for p in paths]
        smax = max(sharps) or 1.0
        scores: list[float] = []
        for i, b in enumerate(bgrs):
            if b is None:
                scores.append(-1e9)
                continue
            slide = _slide_likeness(b)
            face = 1.0 if _has_large_face(grays[i]) else 0.0
            scores.append(
                slide + 0.5 * stab[i] - 1.0 * face + 0.15 * (sharps[i] / smax)
            )
        return scores
    except Exception:
        return None


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
    cand_paths: list[Path] = []
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
            cand_paths.append(tmp)
    if not cand_paths:
        return None
    # Content-aware ranking (slide-likeness + stability − face, sharpness as
    # tie-breaker); falls back to sharpness-only if the CV toolkit is absent.
    scores = _rank_candidates(cand_paths)
    if scores is None:
        scores = [frame_sharpness(p) for p in cand_paths]
    best_idx = max(range(len(cand_paths)), key=lambda k: scores[k])
    cand_paths[best_idx].replace(final)
    for k, t in enumerate(cand_paths):
        if k == best_idx:
            continue
        try:
            t.unlink()
        except OSError:
            pass
    return final
