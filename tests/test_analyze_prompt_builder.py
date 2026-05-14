"""Tests for analyze.prompt_builder."""
import json
from pathlib import Path

from skills.neurolearn.analyze.prompt_builder import (
    SYSTEM_PROMPT,
    build_prompt,
)
from skills.neurolearn.analyze.source_resolver import VideoSource


def test_system_prompt_is_neutral():
    assert "assistant" in SYSTEM_PROMPT.lower()
    assert "transcript" in SYSTEM_PROMPT.lower()


def test_user_prompt_appears_verbatim(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="WHAT IS THIS ABOUT?",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "WHAT IS THIS ABOUT?" in out
    assert SYSTEM_PROMPT in out


def test_per_video_section_with_metadata(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(
            transcript_path=f,
            title="Cool Talk",
            upload_date="2026-05-09",
            duration_sec=222,
            language="en",
            url="https://youtu.be/abc",
        )],
    )
    assert "[1] Cool Talk" in out
    assert "2026-05-09" in out
    assert "en" in out
    assert "https://youtu.be/abc" in out
    assert "hi" in out


def test_fallback_to_filename_without_manifest(tmp_path: Path):
    f = tmp_path / "video-no-meta.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] x\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "video-no-meta" in out


def test_multiple_videos_get_indexed(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("[00:00:00.000 --> 00:00:01.000] aaa\n", encoding="utf-8")
    b.write_text("[00:00:00.000 --> 00:00:01.000] bbb\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[
            VideoSource(transcript_path=a, title="A"),
            VideoSource(transcript_path=b, title="B"),
        ],
    )
    assert "[1] A" in out
    assert "[2] B" in out


def test_truncation_at_max_chars(tmp_path: Path):
    long_txt = "[00:00:00.000 --> 00:00:01.000] " + ("x" * 5000) + "\n"
    f = tmp_path / "long.txt"
    f.write_text(long_txt, encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
        max_chars=200,
    )
    assert "[...truncated...]" in out


def test_json_transcript_format(tmp_path: Path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello json"}],
    }), encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "hello json" in out


def test_srt_transcript_format(tmp_path: Path):
    f = tmp_path / "t.srt"
    f.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello srt\n",
                 encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "hello srt" in out


def test_unreadable_file_silently_skipped(tmp_path: Path):
    """If one file fails to load — keep going, others should appear."""
    good = tmp_path / "good.txt"
    good.write_text("[00:00:00.000 --> 00:00:01.000] g\n", encoding="utf-8")
    missing = tmp_path / "gone.txt"  # never created
    out = build_prompt(
        user_prompt="P",
        videos=[
            VideoSource(transcript_path=missing, title="MISSING"),
            VideoSource(transcript_path=good, title="GOOD"),
        ],
    )
    assert "GOOD" in out
    assert "g" in out
