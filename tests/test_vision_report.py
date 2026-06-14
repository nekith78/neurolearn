"""Tests for build_vision_report (vision-report / Mode-1 vision step)."""
import json
from pathlib import Path
from unittest.mock import patch

from skills.neurolearn.vision_report_cmd import build_vision_report


def _make_batch(tmp_path: Path) -> Path:
    batch = tmp_path / "batch"
    (batch / "videos").mkdir(parents=True)
    srt = batch / "videos" / "v.srt"
    srt.write_text(
        "1\n00:05:58,000 --> 00:06:02,000\nОткрываем таблицу слухов.\n\n"
        "2\n00:17:58,000 --> 00:18:02,000\nСмотрим инвентарь и сплавы.\n",
        encoding="utf-8",
    )
    (batch / "manifest.json").write_text(json.dumps({
        "videos": [{
            "index": 0, "url": "https://youtu.be/vid", "video_id": "vid",
            "title": "T", "language_detected": "ru",
            "files": {"srt": "videos/v.srt"},
        }],
    }), encoding="utf-8")
    return batch


def test_vision_report_gemini_path_maps_by_window_start(tmp_path):
    """Gemini path: descriptions map back to moments by window.start, and a
    dropped segment (frames failed) leaves that moment empty — not misaligned."""
    from skills.neurolearn.backends.vision_base import VisualSegment
    batch = _make_batch(tmp_path)
    moments = [360.0, 1080.0]  # window starts -> 358.5, 1078.5

    class FakeBackend:
        def __init__(self, *a, **k):
            self.last_run_usage = []
        def annotate_segments(self, *, video_path, windows, prompt_template,
                              language, video_id, out_dir):
            # Return only the FIRST window's segment (simulate 2nd dropped).
            assert "USER FOCUS" in prompt_template  # ask propagated
            assert language == "ru"
            w = windows[0]
            return [VisualSegment(
                start=w.start, end=w.end,
                description="Google-таблица Expedition Cheatsheet, тиры S/A/B.",
                keyframes=["frames/vid_00358.jpg"],
                detected_objects=["Cheatsheet"], importance="high",
            )]

    with patch("skills.neurolearn.config.get_api_key",
               lambda b, env_path=None: "k" if b == "gemini" else None), \
         patch("skills.neurolearn.vision.gemini.GeminiVisionBackend", FakeBackend), \
         patch("skills.neurolearn.vision_report_cmd.resolve_source_video",
               lambda *a, **k: tmp_path / "video.mp4"):
        out = build_vision_report(batch, moments, depth="deep", ask="фокус на тиры")

    assert out["language"] == "ru"
    assert out["vision_engine"].startswith("gemini:")
    by_ts = {m["timestamp"]: m for m in out["moments"]}
    assert "Cheatsheet" in by_ts[360.0]["description"]
    assert by_ts[1080.0]["description"] is None       # dropped → empty, not shifted
    # structured JSON persisted
    assert (batch / "vision-report.json").exists()


def test_vision_report_fallback_without_gemini_key(tmp_path):
    """No Gemini key → frames extracted, agent told to read them itself,
    transcript context attached per moment."""
    batch = _make_batch(tmp_path)
    moments = [360.0]

    with patch("skills.neurolearn.config.get_api_key",
               lambda b, env_path=None: None), \
         patch("skills.neurolearn.frames_cmd.extract_frames_at",
               lambda bd, ms, **k: {360.0: ["frames/vid_00360.jpg"]}):
        out = build_vision_report(batch, moments)

    assert "none" in out["vision_engine"]
    m = out["moments"][0]
    assert m["frames"] == ["frames/vid_00360.jpg"]
    assert m["description"] is None
    assert "таблиц" in m["transcript_context"]         # context from SRT around 6:00
