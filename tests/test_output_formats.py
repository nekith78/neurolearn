"""Tests for new output formats (VTT + JSON) added in v0.5.1."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from skills.youtube_transcribe.utils.output_writer import (
    Segment, write_json, write_vtt,
)


def _s(start, end, text):
    return Segment(start=start, end=end, text=text)


# === VTT ===

def test_vtt_has_header(tmp_path):
    out = tmp_path / "x.vtt"
    write_vtt([_s(0.0, 5.5, "hello")], out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")


def test_vtt_format_uses_dotted_seconds(tmp_path):
    """VTT uses HH:MM:SS.mmm (dot decimal); SRT uses comma. Make sure dot here."""
    out = tmp_path / "x.vtt"
    write_vtt([_s(1.25, 7.5, "hi")], out)
    content = out.read_text(encoding="utf-8")
    # Should contain "00:00:01.250 --> 00:00:07.500"
    assert "00:00:01.250" in content
    assert "-->" in content
    # No comma decimals
    assert "00:00:01,250" not in content


def test_vtt_multiple_segments(tmp_path):
    segs = [
        _s(0.0, 2.0, "first"),
        _s(2.0, 4.0, "second"),
    ]
    out = tmp_path / "x.vtt"
    write_vtt(segs, out)
    content = out.read_text(encoding="utf-8")
    assert "first" in content
    assert "second" in content


def test_vtt_empty(tmp_path):
    out = tmp_path / "x.vtt"
    write_vtt([], out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")


# === JSON ===

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


def test_json_includes_summary(tmp_path):
    out = tmp_path / "x.json"
    write_json([_s(0, 5, "x")], out, summary="## TL;DR\nA summary.")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"] == "## TL;DR\nA summary."


def test_json_non_ascii_preserved(tmp_path):
    """ensure_ascii=False — Russian / Cyrillic stays readable."""
    out = tmp_path / "x.json"
    write_json([_s(0, 5, "Привет мир")], out, language="ru")
    raw = out.read_text(encoding="utf-8")
    assert "Привет мир" in raw  # not \u-escaped
