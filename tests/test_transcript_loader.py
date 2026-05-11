"""Tests for utils/transcript_loader — read .txt/.json/.srt back to Segments."""
import json
from pathlib import Path

from skills.youtube_transcribe.utils.output_writer import Segment
from skills.youtube_transcribe.utils.transcript_loader import (
    load_transcript_segments,
)


def test_loads_json(tmp_path: Path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 5.5, "text": "hello"},
            {"start": 5.5, "end": 10.0, "text": "world"},
        ],
    }), encoding="utf-8")
    segs, lang = load_transcript_segments(p)
    assert len(segs) == 2
    assert segs[0].text == "hello"
    assert segs[0].start == 0.0
    assert segs[1].end == 10.0
    assert lang == "en"


def test_loads_json_without_language(tmp_path: Path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({
        "segments": [{"start": 0, "end": 1, "text": "x"}],
    }), encoding="utf-8")
    segs, lang = load_transcript_segments(p)
    assert len(segs) == 1
    assert lang is None


def test_loads_srt_comma_decimal(tmp_path: Path):
    p = tmp_path / "t.srt"
    p.write_text(
        "1\n00:00:00,000 --> 00:00:05,500\nhello\n\n"
        "2\n00:00:05,500 --> 00:00:10,000\nworld\n",
        encoding="utf-8",
    )
    segs, lang = load_transcript_segments(p)
    assert len(segs) == 2
    assert segs[0].text == "hello"
    assert segs[0].start == 0.0
    assert segs[0].end == 5.5
    assert lang is None


def test_loads_srt_multiline_text(tmp_path: Path):
    p = tmp_path / "t.srt"
    p.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nline one\nline two\n",
        encoding="utf-8",
    )
    segs, _ = load_transcript_segments(p)
    assert len(segs) == 1
    assert "line one" in segs[0].text
    assert "line two" in segs[0].text


def test_loads_txt_with_timestamps(tmp_path: Path):
    """Our write_txt_with_timestamps format: [HH:MM:SS.mmm --> HH:MM:SS.mmm] text"""
    p = tmp_path / "t.txt"
    p.write_text(
        "[00:00:00.000 --> 00:00:05.500] hello\n"
        "[00:00:05.500 --> 00:00:10.000] world\n",
        encoding="utf-8",
    )
    segs, _ = load_transcript_segments(p)
    assert len(segs) == 2
    assert segs[0].text == "hello"
    assert segs[0].end == 5.5


def test_loads_plain_txt_as_single_segment(tmp_path: Path):
    """No time-prefixes → one segment with all text and start=end=0."""
    p = tmp_path / "t.txt"
    p.write_text("Just some plain text without timestamps.", encoding="utf-8")
    segs, _ = load_transcript_segments(p)
    assert len(segs) == 1
    assert "plain text" in segs[0].text
    assert segs[0].start == 0.0


def test_unknown_extension_falls_back_to_txt(tmp_path: Path):
    """Unknown extension → treat as .txt."""
    p = tmp_path / "weird.dat"
    p.write_text(
        "[00:00:00.000 --> 00:00:02.000] test\n",
        encoding="utf-8",
    )
    segs, _ = load_transcript_segments(p)
    assert len(segs) == 1
    assert segs[0].text == "test"


def test_empty_json_segments(tmp_path: Path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"segments": []}), encoding="utf-8")
    segs, _ = load_transcript_segments(p)
    assert segs == []


def test_malformed_json_raises(tmp_path: Path):
    p = tmp_path / "t.json"
    p.write_text("not json", encoding="utf-8")
    import pytest
    with pytest.raises(Exception):
        load_transcript_segments(p)
