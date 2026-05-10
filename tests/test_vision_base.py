"""Tests for VisualSegment dataclass and VisionBackend Protocol."""
from skills.youtube_transcribe.backends.vision_base import VisualSegment


def test_visual_segment_creation():
    vs = VisualSegment(
        start=10.5,
        end=15.0,
        description="Code editor with API call",
        keyframes=["frames/abc_00010.jpg"],
        detected_objects=["editor", "code"],
        trigger_reason="universal:function",
        importance="high",
    )
    assert vs.start == 10.5
    assert vs.importance == "high"


def test_visual_segment_defaults():
    vs = VisualSegment(start=0.0, end=1.0, description="x", keyframes=[])
    assert vs.detected_objects == []
    assert vs.trigger_reason == ""
    assert vs.importance == "medium"
