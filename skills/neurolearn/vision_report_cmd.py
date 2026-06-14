"""vision-report — the agent-orchestrated (Mode 1) vision step.

The driving agent (Claude / Codex / any) reads the transcript, picks the
moments worth a visual look, then calls this with those timestamps. For each
moment we extract a keyframe bracket and have Gemini describe what's ON SCREEN,
grounded in the surrounding transcript (so it describes the table/inventory the
speaker refers to, not the webcam). Returns structured results the agent turns
into a Markdown report → `report --from-markdown`.

Timestamps are OURS (from the transcript/SRT) — Gemini never supplies them, so
its known long-video timestamp drift is irrelevant here. If Gemini isn't
configured (or fails), the keyframes are still extracted and the agent is told
to read them with its own vision (the Mode-1 fallback).

Harness-agnostic: nothing here is Claude-specific — any agent can call it.
"""
from __future__ import annotations

import json
from pathlib import Path

from skills.neurolearn.frames_cmd import (
    parse_timestamp, resolve_source_video, _load_manifest, _pick_video,
)

_DEPTH_NOTE = {
    "standard": (
        "Depth STANDARD: be concise — capture the key on-screen content of "
        "this moment (panel/window/table, the values, labels and text shown)."
    ),
    "deep": (
        "Depth DEEP (reader is a beginner who knows nothing): be exhaustive — "
        "name every button / menu / field the user interacts with and read all "
        "relevant on-screen text, so a novice can reproduce this step exactly."
    ),
}


def _load_segments(batch_dir: Path, video: dict) -> list:
    files = video.get("files") or {}
    srt = files.get("srt")
    if srt and (batch_dir / srt).exists():
        from skills.neurolearn.report.orchestrator import _parse_srt
        return _parse_srt(batch_dir / srt)
    return []


def _build_prompt_template(video_type: str, depth: str, ask: str) -> str:
    """Per-video-type vision instructions (reused from prompts_default.toml),
    augmented with the depth tier and — highest priority — the user's own
    focus prompt. Keeps {transcript_snippet}/{start_sec}/{end_sec} placeholders
    the backend fills."""
    from skills.neurolearn.vision.prompts import load_prompt
    base = load_prompt(video_type).template
    parts: list[str] = []
    if ask:
        parts.append(f"USER FOCUS (highest priority — emphasize this): {ask}")
    parts.append(_DEPTH_NOTE.get(depth, _DEPTH_NOTE["standard"]))
    parts.append(base)
    return "\n\n".join(parts)


def build_vision_report(
    batch_dir: Path | str,
    moments: list[float],
    *,
    video_index: int = 0,
    depth: str = "standard",
    ask: str = "",
    cfg=None,
) -> dict:
    """Produce per-moment visual descriptions. See module docstring."""
    batch_dir = Path(batch_dir).resolve()
    manifest = _load_manifest(batch_dir)
    video = _pick_video(manifest, video_index)
    video_id = video.get("video_id") or "video"
    language = (
        video.get("language_detected") or video.get("source_language") or "en"
    )
    segments = _load_segments(batch_dir, video)

    from skills.neurolearn.pipeline_v02 import _window_transcript_context
    from skills.neurolearn.detection.base import DetectionWindow

    moments = [round(float(m), 3) for m in moments]
    windows = []
    start_to_ts: dict[float, float] = {}
    for ts in moments:
        start = round(max(0.0, ts - 1.5), 3)
        start_to_ts[start] = ts
        windows.append(DetectionWindow(
            start=start, end=ts + 2.0, reason="agent_moment", score=1.0,
            transcript_context=_window_transcript_context(segments, ts, ts),
        ))

    from skills.neurolearn.config import get_api_key
    gem_key = get_api_key("gemini")
    out: dict = {
        "video_id": video_id, "language": language, "depth": depth,
        "ask": ask, "vision_engine": None, "moments": [],
    }

    if gem_key:
        from skills.neurolearn.vision.gemini import (
            GeminiVisionBackend, concurrency_for_tier,
        )
        from skills.neurolearn.vision.prompts import DEFAULT_VIDEO_TYPE
        try:
            from skills.neurolearn.detection.video_type_detect import (
                detect_video_type,
            )
            video_type = (
                detect_video_type(segments).video_type
                if segments else DEFAULT_VIDEO_TYPE
            )
        except Exception:
            video_type = DEFAULT_VIDEO_TYPE
        template = _build_prompt_template(video_type, depth, ask)
        model = (getattr(cfg, "gemini_vision_model", "") if cfg else "") \
            or "gemini-3.5-flash"
        tier = (getattr(cfg, "gemini_tier", "free") if cfg else "free") or "free"
        backend = GeminiVisionBackend(
            api_key=gem_key, model=model,
            max_concurrent=concurrency_for_tier(tier),
        )
        video_path = resolve_source_video(
            batch_dir, video_index=video_index, cfg=cfg,
        )
        vsegs = backend.annotate_segments(
            video_path=video_path, windows=windows, prompt_template=template,
            language=language, video_id=video_id, out_dir=batch_dir,
        )
        out["vision_engine"] = f"gemini:{model}"
        out["video_type"] = video_type
        # Map each returned segment back to its moment by window start —
        # annotate_segments may drop windows whose frames failed, so a
        # positional zip would misalign.
        by_moment: dict[float, dict] = {}
        for vs in vsegs:
            ts = start_to_ts.get(round(float(vs.start), 3))
            if ts is None:
                continue
            by_moment[ts] = {
                "timestamp": ts,
                "frames": list(vs.keyframes),
                "description": vs.description,
                "key_objects": list(vs.detected_objects),
                "importance": vs.importance,
            }
        for ts in moments:
            out["moments"].append(by_moment.get(ts, {
                "timestamp": ts, "frames": [], "description": None,
                "note": "no frame extracted (past end of video?)",
            }))
    else:
        # Fallback: extract frames only, hand them to the agent to read.
        from skills.neurolearn.frames_cmd import extract_frames_at
        res = extract_frames_at(
            batch_dir, moments, video_index=video_index, cfg=cfg,
        )
        out["vision_engine"] = (
            "none — GEMINI_API_KEY not set; the orchestrating agent should "
            "open the frames below and describe them itself"
        )
        for ts in moments:
            out["moments"].append({
                "timestamp": ts,
                "frames": res.get(ts, []),
                "description": None,
                "transcript_context": _window_transcript_context(
                    segments, ts, ts,
                ),
            })

    (batch_dir / "vision-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return out
