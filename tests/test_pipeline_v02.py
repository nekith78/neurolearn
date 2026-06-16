"""Tests for v0.2 pipeline wrapper that adds quality + vision stages."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.neurolearn.pipeline_v02 import apply_v02_stages
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.utils.output_writer import Segment


def _result(text="hello world"):
    return TranscriptionResult(
        text=text,
        segments=[Segment(start=0.0, end=5.0, text=text)],
        language_detected="en",
        backend_name="subtitles",
        duration_seconds=5.0,
    )


def test_quality_check_runs_when_enabled():
    cfg = {"quality_check": True, "vision_backend": "off"}
    result = _result()
    with patch(
        "skills.neurolearn.pipeline_v02.HeuristicChecker"
    ) as mock_checker:
        instance = MagicMock()
        instance.check.return_value = MagicMock(
            score=0.85, recommendation="use_as_is", flags=[], breakdown={},
        )
        mock_checker.return_value = instance

        out = apply_v02_stages(
            result=result, cfg=cfg, video_path=None,
            video_id="x", out_dir=Path("/tmp"), source="youtube_auto",
        )
    assert out.quality is not None
    assert out.quality.score == 0.85


def test_quality_check_skipped_when_disabled():
    cfg = {"quality_check": False, "vision_backend": "off"}
    result = _result()
    out = apply_v02_stages(
        result=result, cfg=cfg, video_path=None,
        video_id="x", out_dir=Path("/tmp"), source="youtube_auto",
    )
    assert out.quality is None


def test_vision_skipped_when_off():
    cfg = {"quality_check": False, "vision_backend": "off"}
    result = _result()
    out = apply_v02_stages(
        result=result, cfg=cfg, video_path=Path("/tmp/v.mp4"),
        video_id="x", out_dir=Path("/tmp"), source="whisper",
    )
    assert out.visual_segments == []


def test_vision_extracts_keyframe_manifest_mode1(tmp_path):
    """Vision is Mode-1 only: the stage extracts keyframes and writes a
    manifest for the agent — no autonomous describe backend."""
    cfg = {
        "quality_check": False,
        "vision_backend": "gemini",
        "detect_method": "keywords_only",
        "frames_per_window": 1,
        "max_windows_per_video": 5,
    }
    result = _result(text="look here")
    with patch(
        "skills.neurolearn.pipeline_v02.find_detection_windows",
        return_value=[MagicMock(start=0.0, end=5.0, reason="universal", score=0.7,
                                weight=1.0, phrase="look here", priority_score=0.7)],
    ), patch(
        "skills.neurolearn.pipeline_v02._write_keyframes_manifest",
        return_value={"keyframes": []},
    ) as mock_manifest:
        out = apply_v02_stages(
            result=result, cfg=cfg, video_path=tmp_path / "v.mp4",
            video_id="x", out_dir=tmp_path, source="whisper",
        )
    mock_manifest.assert_called_once()
    assert getattr(out, "vision_extract_manifest", None) == {"keyframes": []}


def test_window_transcript_context_grounds_vision_prompt():
    """v0.21 regression: vision windows must carry the SURROUNDING transcript
    (not just the trigger phrase) so the annotator knows what the speaker is
    referring to. Previously transcript_snippet=window.phrase → blind frames."""
    from skills.neurolearn.pipeline_v02 import (
        _window_transcript_context, _attach_transcript_context,
    )
    from skills.neurolearn.utils.output_writer import Segment
    from skills.neurolearn.detection.base import DetectionWindow

    segs = [
        Segment(start=0.0, end=5.0, text="Now let's open the expedition map."),
        Segment(start=5.0, end=10.0, text="Look at the island rumors panel."),
        Segment(start=200.0, end=205.0, text="Unrelated much later content."),
    ]
    ctx = _window_transcript_context(segs, 5.0, 9.0)
    assert "island rumors" in ctx
    assert "expedition map" in ctx          # within pad before the window
    assert "Unrelated" not in ctx           # far away → excluded

    w = DetectionWindow(start=5.0, end=9.0, reason="raw", score=1.0, phrase="look")
    enriched = _attach_transcript_context([w], segs)
    assert len(enriched) == 1
    assert "island rumors" in enriched[0].transcript_context
    assert enriched[0].phrase == "look"     # original fields preserved (frozen replace)


def test_window_transcript_context_empty_segments_safe():
    from skills.neurolearn.pipeline_v02 import _window_transcript_context
    assert _window_transcript_context([], 0.0, 10.0) == ""
