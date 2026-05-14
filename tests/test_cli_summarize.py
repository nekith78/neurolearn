"""Tests for the standalone `neurolearn summarize` sub-command."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def test_summarize_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["summarize", "--help"])
    assert res.exit_code == 0
    assert "--backend" in res.output
    assert "ollama" in res.output


def test_summarize_writes_md_next_to_source(tmp_path: Path):
    src = tmp_path / "t.txt"
    src.write_text("[00:00:00.000 --> 00:00:05.000] hello\n", encoding="utf-8")

    fake_summary = "## TL;DR\nA summary."

    with patch(
        "skills.neurolearn.quality.summarizer.summarize_transcript",
        return_value=fake_summary,
    ), patch(
        "skills.neurolearn.transcribe.get_api_key",
        return_value="fake-key",
    ):
        runner = CliRunner()
        res = runner.invoke(
            cli, ["summarize", str(src), "--backend", "gemini"],
            catch_exceptions=False,
        )

    assert res.exit_code == 0
    out_file = src.with_suffix(".txt.summary.md")
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == fake_summary


def test_summarize_explicit_output_path(tmp_path: Path):
    src = tmp_path / "t.json"
    src.write_text(json.dumps({
        "segments": [{"start": 0, "end": 5, "text": "hi"}],
    }), encoding="utf-8")
    custom = tmp_path / "my-summary.md"

    with patch(
        "skills.neurolearn.quality.summarizer.summarize_transcript",
        return_value="## TL;DR\nx",
    ), patch(
        "skills.neurolearn.transcribe.get_api_key",
        return_value="fake-key",
    ):
        runner = CliRunner()
        res = runner.invoke(
            cli,
            ["summarize", str(src), "--backend", "gemini",
             "--output", str(custom)],
            catch_exceptions=False,
        )

    assert res.exit_code == 0
    assert custom.exists()
    assert "TL;DR" in custom.read_text(encoding="utf-8")


def test_summarize_ollama_does_not_require_api_key(tmp_path: Path):
    """Ollama is local — no API-key gate."""
    src = tmp_path / "t.txt"
    src.write_text("[00:00:00.000 --> 00:00:05.000] hi\n", encoding="utf-8")

    captured = {}

    def fake_summarize(segments, **kw):
        captured.update(kw)
        return "## TL;DR\nok"

    with patch(
        "skills.neurolearn.quality.summarizer.summarize_transcript",
        side_effect=fake_summarize,
    ):
        runner = CliRunner()
        res = runner.invoke(
            cli, ["summarize", str(src), "--backend", "ollama"],
            catch_exceptions=False,
        )

    assert res.exit_code == 0
    assert captured["backend"] == "ollama"
    assert captured["api_key"] is None


def test_summarize_missing_api_key_exits_with_hint(tmp_path: Path):
    src = tmp_path / "t.txt"
    src.write_text("[00:00:00.000 --> 00:00:05.000] hi\n", encoding="utf-8")

    with patch(
        "skills.neurolearn.transcribe.get_api_key",
        return_value=None,
    ):
        runner = CliRunner()
        res = runner.invoke(
            cli, ["summarize", str(src), "--backend", "claude"],
            catch_exceptions=False,
        )

    assert res.exit_code != 0
    assert "anthropic" in res.output.lower() or "claude" in res.output.lower()


def test_summarize_empty_transcript_exits_zero(tmp_path: Path):
    src = tmp_path / "t.json"
    src.write_text(json.dumps({"segments": []}), encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        cli, ["summarize", str(src), "--backend", "ollama"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    assert "empty" in res.output.lower()


def test_summarize_llm_returns_empty(tmp_path: Path):
    src = tmp_path / "t.txt"
    src.write_text("[00:00:00.000 --> 00:00:05.000] hi\n", encoding="utf-8")

    with patch(
        "skills.neurolearn.quality.summarizer.summarize_transcript",
        return_value="",
    ):
        runner = CliRunner()
        res = runner.invoke(
            cli, ["summarize", str(src), "--backend", "ollama"],
            catch_exceptions=False,
        )
    assert res.exit_code == 4
    assert "llm" in res.output.lower() or "response" in res.output.lower()
