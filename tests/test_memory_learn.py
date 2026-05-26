"""Tests for memory.learn — diff + approval + auto-description."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.config import Config
from skills.neurolearn.memory.learn import (
    TranscriptInput, _parse_candidates,
    approve_candidates_interactive, extract_candidates, learn,
)
from skills.neurolearn.memory.store import MemoryFile, read_memory, write_memory


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(memories_dir=str(tmp_path), analyze_backend="groq")


# ---------------------------------------------------------------------------
# _parse_candidates — robust to LLM response shapes
# ---------------------------------------------------------------------------

def test_parse_candidates_clean_json():
    raw = json.dumps({"candidates": [
        {"topic": "Hooks", "text": "Hook A.", "source_timestamp": "1:00"},
        {"topic": "Skills", "text": "Skill B.", "source_timestamp": None},
    ]})
    out = _parse_candidates(raw)
    assert len(out) == 2
    assert out[0]["text"] == "Hook A."


def test_parse_candidates_fenced_code_block():
    raw = '''Here is the result:
```json
{"candidates": [{"topic": "X", "text": "Y", "source_timestamp": null}]}
```
That's it.'''
    out = _parse_candidates(raw)
    assert len(out) == 1
    assert out[0]["text"] == "Y"


def test_parse_candidates_embedded_object():
    raw = 'Some preamble {"candidates": [{"topic": "T", "text": "Z"}]} tail.'
    out = _parse_candidates(raw)
    assert len(out) == 1
    assert out[0]["text"] == "Z"


def test_parse_candidates_empty_array():
    raw = '{"candidates": []}'
    out = _parse_candidates(raw)
    assert out == []


def test_parse_candidates_drops_items_without_text():
    raw = json.dumps({"candidates": [
        {"topic": "OK", "text": "Real."},
        {"topic": "Bad", "text": ""},
        {"topic": "Bad2"},   # no text key
    ]})
    out = _parse_candidates(raw)
    assert len(out) == 1
    assert out[0]["text"] == "Real."


def test_parse_candidates_handles_garbage_gracefully():
    assert _parse_candidates("") == []
    assert _parse_candidates("not json") == []
    assert _parse_candidates("```python\nprint('hi')\n```") == []


# ---------------------------------------------------------------------------
# extract_candidates — LLM call via mocked runner
# ---------------------------------------------------------------------------

def test_extract_candidates_calls_run_analysis_with_full_prompt(cfg):
    memory = MemoryFile(name="m", description="A description.", body="Existing fact.")
    transcript = TranscriptInput(
        url="https://youtu.be/abc",
        title="The Title",
        text="New transcript content with novel claims.",
    )

    captured: dict = {}

    def fake_run(*, full_prompt, backend, api_key):
        captured["prompt"] = full_prompt
        captured["backend"] = backend
        return json.dumps({"candidates": [
            {"topic": "T", "text": "Novel claim.", "source_timestamp": "0:30"},
        ]})

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=fake_run,
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        cands = extract_candidates(
            memory, transcript, analyze_backend="groq", cfg=cfg,
        )

    assert len(cands) == 1
    assert cands[0]["text"] == "Novel claim."
    # Prompt should embed both the existing memory and the new transcript
    assert "Existing fact." in captured["prompt"]
    assert "New transcript content with novel claims." in captured["prompt"]
    assert captured["backend"] == "groq"


# ---------------------------------------------------------------------------
# approve_candidates_interactive — auto-yes + non-TTY safety
# ---------------------------------------------------------------------------

def test_approve_with_auto_yes_returns_all():
    cands = [
        {"topic": "A", "text": "A."},
        {"topic": "B", "text": "B."},
    ]
    out = approve_candidates_interactive(cands, auto_yes=True)
    assert out == cands


def test_approve_in_non_tty_without_auto_yes_returns_empty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    out = approve_candidates_interactive(
        [{"topic": "X", "text": "X."}],
        auto_yes=False,
    )
    assert out == []


def test_approve_empty_list_returns_empty():
    assert approve_candidates_interactive([], auto_yes=True) == []


# ---------------------------------------------------------------------------
# learn — end-to-end with mocked LLM
# ---------------------------------------------------------------------------

def test_learn_writes_approved_facts_to_memory(cfg, tmp_path):
    # Pre-create an empty memory
    write_memory(
        MemoryFile(name="claude-tips", description="Tips for Claude Code."),
        cfg=cfg,
    )

    transcripts = [
        TranscriptInput(
            url="https://youtu.be/v1",
            title="Video One",
            text="Transcript content one mentioning hooks and skills.",
        ),
        TranscriptInput(
            url="https://youtu.be/v2",
            title="Video Two",
            text="Transcript content two mentioning MCP and slash commands.",
        ),
    ]

    fake_responses = [
        json.dumps({"candidates": [
            {"topic": "Hooks", "text": "Hook fact A.", "source_timestamp": None},
            {"topic": "Skills", "text": "Skill fact B.", "source_timestamp": None},
        ]}),
        json.dumps({"candidates": [
            {"topic": "MCP", "text": "MCP fact C.", "source_timestamp": None},
        ]}),
    ]
    responses_iter = iter(fake_responses)

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=lambda **kw: next(responses_iter),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        summary = learn(
            memory_name="claude-tips",
            transcripts=transcripts,
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
        )

    assert summary["candidates_proposed"] == 3
    assert summary["candidates_approved"] == 3
    assert summary["sources_total"] == 2

    m = read_memory("claude-tips", cfg=cfg)
    assert "Hook fact A." in m.body
    assert "Skill fact B." in m.body
    assert "MCP fact C." in m.body
    assert m.sources == 2


def test_learn_creates_memory_if_not_existing(cfg):
    """learn() must work even when the named memory doesn't exist yet
    (we treat it as `create-on-first-use`)."""
    transcript = TranscriptInput(
        url="https://youtu.be/x",
        title="X",
        text="Some new content.",
    )

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        return_value=json.dumps({"candidates": [
            {"topic": "T", "text": "T fact.", "source_timestamp": None},
        ]}),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        summary = learn(
            memory_name="fresh-mem",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
        )

    assert summary["candidates_approved"] == 1
    m = read_memory("fresh-mem", cfg=cfg)
    assert "T fact." in m.body


def test_learn_auto_generates_description_when_missing(cfg):
    """If the memory has no description and we just ingested content,
    learn() should call the LLM once more to summarize the SCOPE."""
    write_memory(MemoryFile(name="no-desc"), cfg=cfg)
    transcript = TranscriptInput(url="u", title="t", text="content")

    fake_responses = [
        # First call — extract candidates
        json.dumps({"candidates": [
            {"topic": "T", "text": "F1.", "source_timestamp": None},
        ]}),
        # Second call — auto-describe scope
        "A description of what belongs here. Two sentences.",
    ]
    responses_iter = iter(fake_responses)

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=lambda **kw: next(responses_iter),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        learn(
            memory_name="no-desc",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
        )

    m = read_memory("no-desc", cfg=cfg)
    assert m.description == "A description of what belongs here. Two sentences."


def test_learn_does_not_overwrite_existing_description(cfg):
    """If the user already provided a description, learn() must NOT
    auto-generate a new one — respect the user's wording."""
    write_memory(
        MemoryFile(name="has-desc", description="My exact words."),
        cfg=cfg,
    )
    transcript = TranscriptInput(url="u", title="t", text="content")

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        return_value=json.dumps({"candidates": [
            {"topic": "T", "text": "Fact.", "source_timestamp": None},
        ]}),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        learn(
            memory_name="has-desc",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
        )

    m = read_memory("has-desc", cfg=cfg)
    assert m.description == "My exact words.", (
        "Existing user-supplied description must not be overwritten."
    )
