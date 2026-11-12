"""Tests for analyze.chunked_runner — groq-only chunked map-reduce.

The LLM call (`run_analysis`) is always mocked: these tests assert the
chunking/routing behaviour (how many calls, single-shot vs map-reduce),
never a real API.
"""
from unittest.mock import patch

from skills.neurolearn.analyze.source_resolver import VideoSource
from skills.neurolearn.analyze import chunked_runner


def _video(tmp_path, name: str, text: str) -> VideoSource:
    p = tmp_path / f"{name}.txt"
    p.write_text(text, encoding="utf-8")
    return VideoSource(transcript_path=p, title=name, url=f"http://x/{name}")


def test_small_input_is_single_shot(tmp_path):
    """Small prompt → exactly one run_analysis call (no chunking)."""
    videos = [_video(tmp_path, "a", "short text")]
    with patch("skills.neurolearn.analyze.runner.run_analysis",
                      return_value="RESP") as m:
        out = chunked_runner.run_analysis_chunked(
            "summarize", videos, backend="groq", api_key="k",
            max_input_chars=10_000,
        )
    assert out == "RESP"
    assert m.call_count == 1


def test_non_groq_is_single_shot_even_when_large(tmp_path):
    """Non-groq backends have big contexts — never chunk."""
    videos = [_video(tmp_path, "a", "x" * 50_000)]
    with patch("skills.neurolearn.analyze.runner.run_analysis",
                      return_value="RESP") as m:
        out = chunked_runner.run_analysis_chunked(
            "summarize", videos, backend="gemini", api_key="k",
            max_input_chars=2_000,
        )
    assert out == "RESP"
    assert m.call_count == 1


def test_groq_large_multi_video_map_reduce(tmp_path):
    """groq over budget, N videos each fitting one chunk →
    N map calls + 1 reduce call. Budget (8000) is comfortably larger than
    the map scaffold so a 1500-char body is never itself split, and the
    mocked tiny summaries make the reduce a single call."""
    videos = [_video(tmp_path, f"v{i}", "x" * 1_500) for i in range(6)]
    with patch("skills.neurolearn.analyze.runner.run_analysis",
                      return_value="SUMMARY") as m:
        chunked_runner.run_analysis_chunked(
            "make a report", videos, backend="groq", api_key="k",
            max_input_chars=8_000,
        )
    assert m.call_count == 7  # 6 map + 1 reduce


def test_groq_oversized_single_transcript_is_split(tmp_path):
    """A single transcript bigger than the per-call budget is split into
    several sequential chunks (many map calls + 1 reduce)."""
    big = _video(tmp_path, "big", "z" * 6_000)
    with patch("skills.neurolearn.analyze.runner.run_analysis",
                      return_value="S") as m:
        chunked_runner.run_analysis_chunked(
            "report", [big], backend="groq", api_key="k",
            max_input_chars=2_000,
        )
    assert m.call_count >= 4  # multiple map chunks + reduce


def test_reduce_collapses_when_summaries_dont_fit(tmp_path):
    """If the assembled reduce prompt still exceeds the budget, summaries
    are collapsed in groups (extra condense calls) before the final call —
    it must terminate and still return a string."""
    videos = [_video(tmp_path, f"v{i}", "t" * 200) for i in range(8)]
    # Each map/condense returns text long enough that 8 together exceed the
    # tiny budget, forcing at least one collapse round.
    with patch("skills.neurolearn.analyze.runner.run_analysis",
                      return_value="S" * 400) as m:
        out = chunked_runner.run_analysis_chunked(
            "report", videos, backend="groq", api_key="k",
            max_input_chars=1_500,
        )
    assert isinstance(out, str)
    assert m.call_count > 9  # 8 map + collapse round(s) + final reduce


def test_comment_chunks_keep_viewer_attribution_through_collapse_and_reduce(tmp_path):
    video = _video(tmp_path, "demo", "SPOKEN " * 950)
    video.comments_text = "VIEWER " * 950
    prompts = []

    def summarize(prompt, **_):
        prompts.append(prompt)
        if "SPOKEN" in prompt:
            assert "VIEWER" not in prompt
            return "speaker-summary " * 30
        if "VIEWER" in prompt:
            assert "audience comments" in prompt.lower()
            assert "following transcript" not in prompt
            return "viewer-summary " * 30
        if "Merge the following" in prompt:
            if "viewer-summary" in prompt:
                assert "audience comments" in prompt.lower()
                assert "speaker-summary" not in prompt
                return "condensed viewer-summary"
            return "condensed speaker-summary"
        return "report"

    with patch("skills.neurolearn.analyze.runner.run_analysis", side_effect=summarize):
        out = chunked_runner.run_analysis_chunked(
            "Compare audience and speaker", [video], backend="groq", api_key=None,
            max_input_chars=3_000,
        )

    assert out == "report"
    assert sum("VIEWER" in prompt for prompt in prompts) >= 3
    assert any("Merge the following" in prompt for prompt in prompts)
    final = prompts[-1]
    speaker, audience = final.split("Audience comment summaries:")
    assert "speaker-summary" in speaker and "viewer-summary" in audience


def test_one_transcript_without_comments_keeps_one_reduction_after_map(tmp_path):
    video = _video(tmp_path, "demo", "SPOKEN " * 1_000)
    prompts = []

    def summarize(prompt, **_):
        prompts.append(prompt)
        return "map-summary " * 100

    with patch("skills.neurolearn.analyze.runner.run_analysis", side_effect=summarize):
        chunked_runner.run_analysis_chunked(
            "Summarize", [video], backend="groq", api_key=None, max_input_chars=2_000,
        )
    assert len(prompts) > 3
    assert all("Condense the following transcript" in prompt for prompt in prompts[:-1])
    assert "Transcript summaries:" in prompts[-1]
    assert "Audience comment summaries:" not in prompts[-1]
