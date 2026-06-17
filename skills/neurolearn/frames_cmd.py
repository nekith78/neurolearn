"""On-demand keyframe extraction for the agent-driven visual-report flow.

This is the core of "Pass 2": after a transcript exists, the orchestrating
agent (Claude / Codex / any) decides which moments need a visual look and
calls `neurolearn frames <batch> --at <ts>` for each. The tool extracts a
small bracket of frames around each timestamp from the batch's source video
— lazily downloading and caching that video on first use — and returns the
paths so the agent can open them with its native vision, already holding the
transcript context.

No external vision API, no LLM here — pure ffmpeg. Offline except the
one-time lazy video download.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


_SOURCE_DIRNAME = "source"
_FRAMES_DIRNAME = "frames"
# Cache check matches whatever container yt-dlp wrote (it names the file by
# its own template, not always "video.mp4"), so any media file in source/
# counts as a cached download — otherwise we'd re-download every call.
_VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}


def parse_timestamp(value: str | float | int) -> float:
    """Parse `MM:SS`, `HH:MM:SS`, or a bare seconds value into seconds.

    Raises ValueError on a malformed string so the CLI can report it
    instead of silently extracting frame 0.
    """
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError(f"timestamp cannot be negative: {value}")
        return float(value)
    s = str(value).strip()
    if not s:
        raise ValueError("empty timestamp")
    if ":" in s:
        parts = s.split(":")
        if len(parts) > 3 or not all(p.strip() != "" for p in parts):
            raise ValueError(f"malformed timestamp: {value!r}")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"malformed timestamp: {value!r}")
        total = 0.0
        for n in nums:
            total = total * 60 + n
        if total < 0:
            raise ValueError(f"timestamp cannot be negative: {value!r}")
        return total
    try:
        secs = float(s)
    except ValueError:
        raise ValueError(f"malformed timestamp: {value!r}")
    if secs < 0:
        raise ValueError(f"timestamp cannot be negative: {value!r}")
    return secs


def _load_manifest(batch_dir: Path) -> dict:
    mf = batch_dir / "manifest.json"
    if not mf.exists():
        raise FileNotFoundError(
            f"manifest.json not found in {batch_dir}. Point `frames` at a "
            "directory produced by transcribe/batch."
        )
    return json.loads(mf.read_text(encoding="utf-8"))


def _pick_video(manifest: dict, video_index: int) -> dict:
    videos = manifest.get("videos") or []
    if not videos:
        raise ValueError("Manifest contains zero videos.")
    if video_index < 0 or video_index >= len(videos):
        raise IndexError(
            f"video_index={video_index} out of range (batch has "
            f"{len(videos)} videos)."
        )
    return videos[video_index]


def cached_source_path(batch_dir: Path) -> Path | None:
    """Return an already-downloaded source video under `<batch>/source/`, or
    None. Any media file counts (yt-dlp names by its own template)."""
    source_dir = Path(batch_dir) / _SOURCE_DIRNAME
    if source_dir.is_dir():
        for p in sorted(source_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in _VIDEO_SUFFIXES:
                return p
    return None


def download_source_to_cache(batch_dir: Path, url: str, *, cfg=None) -> Path:
    """Download the source video into `<batch>/source/` (the shared cache used
    by `frames --at`), reusing an existing cached file if present. Pulls 1080p
    so cropped tooltip text stays sharp (general transcription stays 720p).

    This is what lets `transcribe --with-visuals` and a later `frames --at`
    share ONE download instead of fetching the same video twice.
    """
    cached = cached_source_path(batch_dir)
    if cached is not None:
        return cached
    source_dir = Path(batch_dir) / _SOURCE_DIRNAME
    source_dir.mkdir(parents=True, exist_ok=True)
    from skills.neurolearn.utils.downloader import download_video
    return download_video(url, source_dir, cfg=cfg, max_height=1080)


def resolve_source_video(
    batch_dir: Path, *, video_index: int = 0, cfg=None,
) -> Path:
    """Return a local path to the batch's source video, downloading+caching
    it under `<batch>/source/` on first use.

    Raises BackendError-style ValueError if the batch has no usable URL
    (e.g. it was built from a local-file input we no longer have).
    """
    batch_dir = Path(batch_dir)
    cached = cached_source_path(batch_dir)
    if cached is not None:
        return cached

    manifest = _load_manifest(batch_dir)
    video = _pick_video(manifest, video_index)
    url = video.get("url") or ""
    if not url:
        raise ValueError(
            "This batch has no source URL recorded (likely a local-file "
            "input). Cannot fetch frames on demand — re-run with the "
            "original video available."
        )
    return download_source_to_cache(batch_dir, url, cfg=cfg)


def extract_frames_at(
    batch_dir: Path,
    timestamps: list[float],
    *,
    video_index: int = 0,
    cfg=None,
    offsets: tuple[float, ...] = (-1.5, 0.3, 2.0),
    best: bool = False,
) -> dict[float, list[str]]:
    """Extract frames around each timestamp.

    Default: a small bracket (-1.5 / +0.3 / +2.0 s) — the "before / action /
    settled" trio. With `best=True`, sample several frames in a window per
    moment and keep only the SHARPEST one (avoids catching a tooltip mid-fade
    or mid-transition) — ideal when you want a single clean screenshot to crop.
    Returns {timestamp: [relative frame paths]}; paths are relative to
    `batch_dir` so they're portable in an agent's chat context.
    """
    from skills.neurolearn.vision.frames import (
        extract_keyframes_asymmetric, extract_sharpest_frame,
    )

    batch_dir = Path(batch_dir)
    video_path = resolve_source_video(
        batch_dir, video_index=video_index, cfg=cfg,
    )
    manifest = _load_manifest(batch_dir)
    video = _pick_video(manifest, video_index)
    video_id = video.get("video_id") or "video"
    frames_dir = batch_dir / _FRAMES_DIRNAME

    out: dict[float, list[str]] = {}
    seen: set[float] = set()
    for ts in timestamps:
        ts = round(float(ts), 3)
        if ts in seen:
            continue
        seen.add(ts)
        if best:
            p = extract_sharpest_frame(
                video_path=video_path, event_ts=ts,
                out_dir=frames_dir, video_id=video_id,
            )
            out[ts] = [str(p.relative_to(batch_dir))] if p else []
        else:
            paths = extract_keyframes_asymmetric(
                video_path=video_path,
                event_ts=ts,
                out_dir=frames_dir,
                video_id=video_id,
                offsets=offsets,
            )
            out[ts] = [str(p.relative_to(batch_dir)) for p in paths]
    return out


def crop_image(
    image_path: Path | str,
    box: tuple[int, int, int, int],
    *,
    out_path: Path | str | None = None,
    pad: float = 0.02,
) -> Path:
    """Crop a keyframe to a normalized region so the embedded screenshot shows
    the relevant tooltip/panel instead of the whole game screen.

    `box` is `[ymin, xmin, ymax, xmax]` in 0-1000 normalized coordinates — the
    same convention Gemini returns, and resolution-independent so an agent can
    derive it from a frame it viewed at any size. A small `pad` is added on each
    side. Writes `<stem>_crop.jpg` next to the source (or `out_path`).

    Mode-1 usage: the agent reads the full frame with its own vision, decides
    the region worth showing, and calls this to produce the readable crop.
    """
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Pillow is required to crop frames. Install: uv sync --extra report"
        ) from e

    image_path = Path(image_path)
    ymin, xmin, ymax, xmax = box
    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        raise ValueError(
            f"box must be [ymin,xmin,ymax,xmax] in 0-1000 with min<max; got {box}"
        )
    with Image.open(image_path) as im:
        w, h = im.size
        x0 = max(0, int((xmin / 1000 - pad) * w))
        y0 = max(0, int((ymin / 1000 - pad) * h))
        x1 = min(w, int((xmax / 1000 + pad) * w))
        y1 = min(h, int((ymax / 1000 + pad) * h))
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"degenerate crop box {box} for image {w}x{h}")
        out = (
            Path(out_path) if out_path
            else image_path.with_name(image_path.stem + "_crop.jpg")
        )
        im.convert("RGB").crop((x0, y0, x1, y1)).save(out, "JPEG", quality=90)
    return out
