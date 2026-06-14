"""v0.21: a single `transcribe` must write a canonical manifest.json (same
schema as `batch`), and the legacy synthesizer must produce a manifest whose
segments actually load. Regression guard for the bug where report/vision-report
got zero segments from a single-transcribe dir (flat srt_path vs files.srt)."""
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.utils.output_writer import Segment


def _fake_result():
    segs = [
        Segment(start=0.0, end=3.0, text="First line of the transcript."),
        Segment(start=3.0, end=6.0, text="Second line, on screen a menu."),
    ]
    return TranscriptionResult(
        text="First line of the transcript. Second line, on screen a menu.",
        segments=segs, language_detected="en",
        backend_name="subtitles", duration_seconds=6.0,
    )


def test_single_transcribe_writes_canonical_manifest(tmp_path, monkeypatch):
    """`transcribe <url>` writes manifest.json with the canonical
    `files: {txt, srt}` schema that downstream commands read."""
    from skills.neurolearn.utils.resolver import ResolvedTarget
    target = ResolvedTarget(
        url="https://youtu.be/abc123", title="Demo", upload_date=None,
        duration_sec=6, channel=None, source="inline", video_id="abc123",
    )
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline",
                        lambda *a, **k: _fake_result())
    monkeypatch.setattr("skills.neurolearn.transcribe.resolve",
                        lambda *a, **k: ([target], []))
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH",
                        tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        'default_preset = "smart"\nonboarding_complete = true\n', encoding="utf-8")

    res = CliRunner().invoke(
        cli, ["transcribe", "https://youtu.be/abc123",
              "--output-dir", str(tmp_path), "--srt"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0, res.output
    mf = tmp_path / "manifest.json"
    assert mf.exists(), f"no manifest.json written. Output:\n{res.output}"

    import json
    video = json.loads(mf.read_text())["videos"][0]
    assert video["video_id"] == "abc123"
    assert video["language_detected"] == "en"
    assert "srt" in video["files"] and "txt" in video["files"]

    # The whole point: segments load from the written manifest.
    from skills.neurolearn.report.orchestrator import (
        _load_manifest, _pick_video, _segments_from_video_entry,
    )
    v = _pick_video(_load_manifest(tmp_path), 0)
    assert len(_segments_from_video_entry(tmp_path, v)) == 2


def test_legacy_synthesizer_produces_loadable_segments(tmp_path):
    """Back-compat: a transcribe dir with only loose .txt/.srt (no manifest)
    synthesizes a manifest whose segments load — both via report's loader and
    vision_report's loader (they used to silently return 0)."""
    (tmp_path / "Clip_vid12345678.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "Clip_vid12345678.srt").write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nhello world\n\n"
        "2\n00:00:03,000 --> 00:00:06,000\nsecond bit\n",
        encoding="utf-8",
    )
    from skills.neurolearn.report.orchestrator import (
        _try_synthesize_single_video_manifest, _load_manifest, _pick_video,
        _segments_from_video_entry,
    )
    assert _try_synthesize_single_video_manifest(tmp_path) is not None
    v = _pick_video(_load_manifest(tmp_path), 0)
    assert "srt" in v["files"]
    assert len(_segments_from_video_entry(tmp_path, v)) == 2

    from skills.neurolearn.vision_report_cmd import _load_segments
    assert len(_load_segments(tmp_path, v)) == 2
