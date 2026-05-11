"""--then-analyze hook tests — direct + CLI plumbing."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli, _run_then_analyze


def _make_fake_batch(tmp_path: Path) -> Path:
    batch = tmp_path / "batch_synth"
    batch.mkdir()
    (batch / "v.txt").write_text(
        "[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "batch_synth", "created_at": "x",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "T",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")
    return batch


def test_run_then_analyze_writes_file(tmp_path: Path):
    """Direct call: _run_then_analyze produces analysis-*.md in batch."""
    batch = _make_fake_batch(tmp_path)

    captured = {}

    def fake_run(full_prompt, **kw):
        captured["prompt"] = full_prompt
        return "ANALYZED"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        side_effect=fake_run,
    ):
        _run_then_analyze(
            batch_folder=batch,
            prompt_inline="EXTRACT KEY IDEAS",
            prompt_file=None,
            backend="ollama",
        )

    assert "EXTRACT KEY IDEAS" in captured["prompt"]
    out = list(batch.glob("analysis-*.md"))
    assert len(out) == 1
    assert "ANALYZED" in out[0].read_text(encoding="utf-8")


def test_run_then_analyze_uses_prompt_file(tmp_path: Path):
    batch = _make_fake_batch(tmp_path)
    pf = tmp_path / "p.md"
    pf.write_text("FROM FILE", encoding="utf-8")

    captured = {}

    def fake_run(full_prompt, **kw):
        captured["prompt"] = full_prompt
        return "OK"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        side_effect=fake_run,
    ):
        _run_then_analyze(
            batch_folder=batch,
            prompt_inline=None,
            prompt_file=pf,
            backend="ollama",
        )

    assert "FROM FILE" in captured["prompt"]


def test_run_then_analyze_missing_key_exits_4(tmp_path: Path):
    batch = _make_fake_batch(tmp_path)
    with patch(
        "skills.youtube_transcribe.transcribe.get_api_key",
        return_value=None,
    ):
        try:
            _run_then_analyze(
                batch_folder=batch,
                prompt_inline="x",
                prompt_file=None,
                backend="gemini",
            )
            assert False, "should have exited"
        except SystemExit as e:
            assert e.code == 4


def test_run_then_analyze_empty_response_no_file(tmp_path: Path):
    batch = _make_fake_batch(tmp_path)
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="",
    ):
        _run_then_analyze(
            batch_folder=batch,
            prompt_inline="x",
            prompt_file=None,
            backend="ollama",
        )
    assert list(batch.glob("analysis-*.md")) == []


def test_then_analyze_cli_requires_prompt(tmp_path: Path):
    """CLI plumbing: --then-analyze + no prompt → exit 2 without running batch."""
    runner = CliRunner()
    res = runner.invoke(cli, [
        "batch", "https://youtu.be/dQw4w9WgXcQ",
        "--then-analyze",
    ], catch_exceptions=False)
    assert res.exit_code == 2
    assert "--then-analyze" in res.output or "prompt" in res.output.lower()
