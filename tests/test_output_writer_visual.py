"""Tests for visual moments rendering in combined.md."""
from datetime import date, datetime
from pathlib import Path

from skills.neurolearn.utils.output_writer import (
    BatchMeta,
    BatchVideoStatus,
    write_combined_md,
)
from skills.neurolearn.backends.vision_base import VisualSegment


def _meta() -> BatchMeta:
    return BatchMeta(
        batch_name="test_batch",
        created_at=datetime(2026, 5, 10, 12, 0, 0),
        source_type="inline",
        source_url=None,
        backend="whisper-local",
        backend_options={"model": "turbo"},
        language="auto",
    )


def _video_with_visuals() -> BatchVideoStatus:
    return BatchVideoStatus(
        index=1,
        url="https://youtu.be/abc",
        video_id="abc",
        title="Tutorial",
        upload_date=date(2026, 4, 1),
        duration_sec=600,
        channel="Test",
        language_detected="en",
        text="Hello and welcome to today's tutorial.",
        files={"txt": "Tutorial_abc.txt", "srt": "Tutorial_abc.srt"},
        status="ok",
        visual_segments=[
            VisualSegment(
                start=10.0, end=15.0,
                description="Code editor with API call",
                keyframes=["frames/abc_00010.jpg"],
                detected_objects=["editor"],
                trigger_reason="universal:function",
                importance="high",
            ),
        ],
    )


def test_combined_md_includes_visual_moments_section(tmp_path):
    write_combined_md([_video_with_visuals()], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "### Visual moments" in content
    assert "frames/abc_00010.jpg" in content
    assert "Code editor with API call" in content
    assert "importance: high" in content


def test_combined_md_skips_visual_section_if_empty(tmp_path):
    v = _video_with_visuals()
    v_no_visuals = BatchVideoStatus(
        **{**v.__dict__, "visual_segments": []},
    )
    write_combined_md([v_no_visuals], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "### Visual moments" not in content


def test_combined_md_includes_quality_warning_when_low(tmp_path):
    from skills.neurolearn.quality.base import QualityReport
    v = _video_with_visuals()
    v_low_quality = BatchVideoStatus(
        **{**v.__dict__,
            "quality": QualityReport(
                score=0.3, breakdown={"oov": 0.4}, flags=["high_oov"],
                recommendation="low_quality",
            ),
        },
    )
    write_combined_md([v_low_quality], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "Quality" in content
    assert "0.3" in content or "low_quality" in content
