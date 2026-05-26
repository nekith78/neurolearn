"""CLI tests for `memory append-facts` and `memory learn --claude-extract`.

v0.16.2: ensures Click-level wiring of the new Claude-extract path is
correct end-to-end. Mostly mocks the underlying memory.* functions —
the heavy lifting is covered in test_memory_learn.py. These tests just
prove that flags reach the right helper with the right values.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from skills.neurolearn.config import Config


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(memories_dir=str(tmp_path), analyze_backend="groq")


def test_append_facts_cli_invokes_pure_writer(tmp_path, cfg):
    """`memory append-facts` should call append_approved_from_file()
    with --from-file path and never call an LLM."""
    from skills.neurolearn.memory.cli import memory_group

    approved = {
        "candidates": [
            {"topic": "T", "text": "Fact one.",
             "source_url": "https://u", "source_timestamp": "0:30"},
        ]
    }
    approved_path = tmp_path / "approved.json"
    approved_path.write_text(json.dumps(approved), encoding="utf-8")

    captured: dict = {}

    def fake_append(*, memory_name, approved_path, cfg,
                    autogenerate_description, analyze_backend):
        captured["memory_name"] = memory_name
        captured["approved_path"] = approved_path
        captured["autogenerate_description"] = autogenerate_description
        captured["analyze_backend"] = analyze_backend
        return {
            "memory": memory_name,
            "candidates_in_file": 1,
            "facts_appended": 1,
            "sources_added": 1,
            "sources_total": 1,
        }

    runner = CliRunner()
    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ), patch(
        "skills.neurolearn.memory.learn.append_approved_from_file",
        side_effect=fake_append,
    ):
        result = runner.invoke(
            memory_group,
            ["append-facts", "kb", "--from-file", str(approved_path)],
        )

    assert result.exit_code == 0, result.output
    assert captured["memory_name"] == "kb"
    assert captured["approved_path"] == approved_path
    assert captured["autogenerate_description"] is True
    assert "facts appended:       1" in result.output


def test_append_facts_cli_no_auto_description_flag(tmp_path, cfg):
    from skills.neurolearn.memory.cli import memory_group

    approved = {"candidates": [
        {"topic": "T", "text": "Fact.", "source_url": "u"},
    ]}
    p = tmp_path / "approved.json"
    p.write_text(json.dumps(approved), encoding="utf-8")

    captured: dict = {}

    def fake_append(**kwargs):
        captured.update(kwargs)
        return {
            "memory": "kb", "candidates_in_file": 1, "facts_appended": 1,
            "sources_added": 1, "sources_total": 1,
        }

    runner = CliRunner()
    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ), patch(
        "skills.neurolearn.memory.learn.append_approved_from_file",
        side_effect=fake_append,
    ):
        result = runner.invoke(
            memory_group,
            ["append-facts", "kb", "--from-file", str(p),
             "--no-auto-description"],
        )

    assert result.exit_code == 0, result.output
    assert captured["autogenerate_description"] is False


def test_append_facts_cli_missing_file_exits_3(tmp_path, cfg):
    """Click already enforces exists=True on the path; that yields a
    Click-level usage error (exit 2). We still need our own ValueError
    branch covered, but Click's filesystem check fires first. This test
    just nails the contract — missing file => non-zero exit."""
    from skills.neurolearn.memory.cli import memory_group

    runner = CliRunner()
    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ):
        result = runner.invoke(
            memory_group,
            ["append-facts", "kb", "--from-file",
             str(tmp_path / "missing.json")],
        )
    assert result.exit_code != 0


def test_append_facts_cli_value_error_exits_2(tmp_path, cfg):
    """A malformed JSON should bubble ValueError → exit 2 in our wrapper."""
    from skills.neurolearn.memory.cli import memory_group

    p = tmp_path / "approved.json"
    p.write_text("not json", encoding="utf-8")

    runner = CliRunner()
    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ):
        result = runner.invoke(
            memory_group,
            ["append-facts", "kb", "--from-file", str(p)],
        )

    assert result.exit_code == 2
    assert "not valid JSON" in result.output or "JSON" in result.output


def test_memory_learn_cli_claude_extract_skips_llm(tmp_path, cfg, monkeypatch):
    """`memory learn --claude-extract` must NOT call any LLM and must
    print the briefing path so Claude in chat can act on it."""
    from skills.neurolearn.memory.cli import memory_group

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("Some transcript content.", encoding="utf-8")

    runner = CliRunner()

    def boom(*args, **kwargs):
        raise AssertionError(
            "run_analysis was called in --claude-extract mode "
            "(violates feedback_no_anthropic_api)"
        )

    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ), patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=boom,
    ):
        result = runner.invoke(
            memory_group,
            ["learn", "kb", str(transcript_file), "--claude-extract"],
        )

    assert result.exit_code == 0, result.output
    assert "Claude-extract mode" in result.output
    assert "briefing" in result.output.lower()
    assert "neurolearn memory append-facts kb" in result.output


def test_memory_learn_cli_no_claude_extract_uses_llm(tmp_path, cfg):
    """`memory learn --no-claude-extract` must hit the LLM path even
    if CLAUDE_PLUGIN_ROOT is set in the environment."""
    from skills.neurolearn.memory.cli import memory_group

    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("Some transcript content.", encoding="utf-8")

    runner = CliRunner()
    with patch(
        "skills.neurolearn.memory.cli.load_config",
        return_value=cfg,
    ), patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        return_value=json.dumps({"candidates": [
            {"topic": "T", "text": "F.", "source_timestamp": None},
        ]}),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        result = runner.invoke(
            memory_group,
            ["learn", "kb", str(transcript_file),
             "--yes", "--no-claude-extract"],
            env={"CLAUDE_PLUGIN_ROOT": "/somewhere"},
        )

    assert result.exit_code == 0, result.output
    assert "Learn complete" in result.output
    assert "candidates approved:   1" in result.output
