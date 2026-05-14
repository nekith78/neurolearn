"""Tests for JSON output format (v0.5.1)."""
import json
from unittest.mock import MagicMock

from skills.neurolearn.utils.output_writer import Segment, write_json


def _s(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_json_basic(tmp_path):
    out = tmp_path / "x.json"
    segs = [_s(0.0, 5.0, "hello"), _s(5.0, 10.0, "world")]
    write_json(
        segs, out,
        language="en", backend="gemini", duration_sec=10.0,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["backend"] == "gemini"
    assert data["duration_sec"] == 10.0
    assert len(data["segments"]) == 2
    assert data["segments"][0] == {"start": 0.0, "end": 5.0, "text": "hello"}


def test_json_quality_field_when_present(tmp_path):
    out = tmp_path / "x.json"
    quality = MagicMock()
    quality.score = 0.85
    quality.breakdown = {"oov": 0.05}
    quality.flags = []
    quality.recommendation = "use_as_is"
    write_json([_s(0, 5, "x")], out, quality=quality)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["quality"]["score"] == 0.85
    assert data["quality"]["recommendation"] == "use_as_is"


def test_json_no_quality_field_when_none(tmp_path):
    out = tmp_path / "x.json"
    write_json([_s(0, 5, "x")], out, quality=None)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["quality"] is None


def test_json_includes_visual_segments(tmp_path):
    out = tmp_path / "x.json"
    vs = MagicMock()
    vs.start = 10.0
    vs.end = 15.0
    vs.description = "diagram"
    vs.keyframes = ["frames/x.jpg"]
    vs.detected_objects = ["diagram"]
    vs.trigger_reason = "raw"
    vs.importance = "high"
    write_json([_s(0, 5, "x")], out, visual_segments=[vs])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["visual_segments"]) == 1
    assert data["visual_segments"][0]["importance"] == "high"


def test_json_non_ascii_preserved(tmp_path):
    """ensure_ascii=False — Russian / Cyrillic stays readable."""
    out = tmp_path / "x.json"
    write_json([_s(0, 5, "Привет мир")], out, language="ru")
    raw = out.read_text(encoding="utf-8")
    assert "Привет мир" in raw  # not \u-escaped
