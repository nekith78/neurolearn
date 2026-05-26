"""Tests for memory.learn — diff + approval + auto-description.

v0.16.2 adds Claude-extract mode tests at the bottom of this file:
when CLAUDE_PLUGIN_ROOT is set (or claude_extract=True is passed
explicitly), learn() must NOT call any LLM — it must write a briefing
manifest and exit. The companion command `memory append-facts` is a
pure write that takes a Claude-produced approved.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.neurolearn.config import Config
from skills.neurolearn.memory.learn import (
    TranscriptInput, _parse_candidates,
    append_approved_from_file,
    approve_candidates_interactive, extract_candidates, learn,
    write_learn_briefing,
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


# ---------------------------------------------------------------------------
# v0.16.2 — Claude-extract mode: NO external LLM call, writes briefing
# ---------------------------------------------------------------------------

class _BoomLLM:
    """Sentinel object that fails the test if anything tries to call an LLM.

    Used as a side_effect on run_analysis: any invocation raises and
    immediately fails the test, proving that the Claude-extract path
    truly bypasses external LLM calls.
    """
    def __call__(self, *args, **kwargs):
        raise AssertionError(
            "External LLM was called in Claude-extract mode — "
            "this violates feedback_no_anthropic_api project rule."
        )


def test_learn_claude_extract_explicit_skips_llm(cfg, tmp_path):
    """Passing claude_extract=True must skip all LLM calls and write
    a briefing manifest instead, regardless of env var state."""
    write_memory(
        MemoryFile(name="kb", description="existing scope"),
        cfg=cfg,
    )
    transcript = TranscriptInput(
        url="https://youtu.be/x",
        title="The Video",
        text="Some transcript content.",
    )

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=_BoomLLM(),
    ):
        summary = learn(
            memory_name="kb",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
            claude_extract=True,
        )

    assert summary["mode"] == "claude_code_extract_only"
    assert summary["candidates_proposed"] == 0
    assert summary["candidates_approved"] == 0
    briefing_path = Path(summary["briefing_path"])
    approved_json_path = Path(summary["approved_json_path"])
    assert briefing_path.exists(), "briefing.md must be written"
    assert briefing_path.suffix == ".md"
    assert approved_json_path.parent == briefing_path.parent

    briefing = briefing_path.read_text(encoding="utf-8")
    assert "Claude-extract mode" in briefing
    assert "kb" in briefing
    assert "The Video" in briefing
    assert "Some transcript content." in briefing
    assert "neurolearn memory append-facts kb" in briefing


def test_learn_claude_extract_via_env_var(cfg, monkeypatch):
    """When CLAUDE_PLUGIN_ROOT is set and claude_extract isn't passed
    explicitly, learn() must default to Claude-extract mode."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/some/path/from/claude/code")
    transcript = TranscriptInput(url="u", title="t", text="x")

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=_BoomLLM(),
    ):
        summary = learn(
            memory_name="auto-detect",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
        )
    assert summary["mode"] == "claude_code_extract_only"


def test_learn_env_var_override_with_explicit_false(cfg, monkeypatch):
    """--no-claude-extract (claude_extract=False) must force the Groq
    path even inside Claude Code."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/in/claude/code")
    transcript = TranscriptInput(url="u", title="t", text="content")

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        return_value=json.dumps({"candidates": [
            {"topic": "T", "text": "F.", "source_timestamp": None},
        ]}),
    ), patch(
        "skills.neurolearn.config.get_api_key",
        return_value="fake-key",
    ):
        summary = learn(
            memory_name="forced-groq",
            transcripts=[transcript],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
            claude_extract=False,
        )
    assert summary["mode"] == "llm_diff"
    assert summary["candidates_approved"] == 1


def test_write_learn_briefing_inlines_transcripts(cfg, tmp_path):
    """The briefing markdown should embed every transcript verbatim so
    Claude can read each one inline (no need to open extra files)."""
    memory = MemoryFile(name="kb", description="d", body="existing")
    transcripts = [
        TranscriptInput(url="https://a", title="A title", text="A text"),
        TranscriptInput(url="https://b", title="B title", text="B text"),
    ]
    out = write_learn_briefing(
        memory_name="kb",
        memory=memory,
        transcripts=transcripts,
        cfg=cfg,
        pending_dir=tmp_path / "pending",
    )
    md = out["briefing_path"].read_text(encoding="utf-8")
    assert "Transcript 1: A title" in md
    assert "A text" in md
    assert "Transcript 2: B title" in md
    assert "B text" in md
    assert "existing" in md  # existing body inlined

    machine = json.loads(out["transcripts_path"].read_text(encoding="utf-8"))
    assert machine["memory_name"] == "kb"
    assert len(machine["transcripts"]) == 2
    assert machine["next_command"].startswith("neurolearn memory append-facts kb ")


def test_learn_empty_transcripts_is_noop(cfg):
    """No-op when the caller passes an empty list — must not error,
    must not write a briefing, must not call an LLM."""
    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=_BoomLLM(),
    ):
        summary = learn(
            memory_name="never-touched",
            transcripts=[],
            analyze_backend="groq",
            cfg=cfg,
            auto_yes=True,
            claude_extract=True,
        )
    assert summary["mode"] == "noop"


# ---------------------------------------------------------------------------
# v0.16.2 — append_approved_from_file (pure write, no LLM)
# ---------------------------------------------------------------------------

def test_append_approved_from_file_writes_facts_no_llm(cfg, tmp_path):
    approved = {
        "candidates": [
            {
                "topic": "Hooks",
                "text": "Hooks fire on SessionStart.",
                "source_url": "https://youtu.be/v1",
                "source_timestamp": "01:23",
            },
            {
                "topic": "Hooks",
                "text": "PostToolUse hooks see tool output.",
                "source_url": "https://youtu.be/v1",
            },
            {
                "topic": "Skills",
                "text": "Skills can be invoked by /<name>.",
                "source_url": "https://youtu.be/v2",
                "source_timestamp": None,
            },
        ]
    }
    approved_path = tmp_path / "approved.json"
    approved_path.write_text(json.dumps(approved), encoding="utf-8")

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=_BoomLLM(),
    ):
        summary = append_approved_from_file(
            memory_name="claude-tips",
            approved_path=approved_path,
            cfg=cfg,
            autogenerate_description=False,
        )

    assert summary["facts_appended"] == 3
    assert summary["sources_added"] == 2  # two distinct source URLs
    assert summary["sources_total"] == 2

    m = read_memory("claude-tips", cfg=cfg)
    assert "Hooks fire on SessionStart." in m.body
    assert "PostToolUse hooks see tool output." in m.body
    assert "Skills can be invoked by /<name>." in m.body
    assert "https://youtu.be/v1" in m.body
    assert "https://youtu.be/v2" in m.body


def test_append_approved_skips_empty_text(cfg, tmp_path):
    approved = {
        "candidates": [
            {"topic": "Real", "text": "Good fact.", "source_url": "https://u"},
            {"topic": "Bad", "text": "", "source_url": "https://u"},
            {"topic": "Bad2", "source_url": "https://u"},  # no text key
        ]
    }
    p = tmp_path / "approved.json"
    p.write_text(json.dumps(approved), encoding="utf-8")
    summary = append_approved_from_file(
        memory_name="kb", approved_path=p, cfg=cfg,
        autogenerate_description=False,
    )
    assert summary["facts_appended"] == 1


def test_append_approved_rejects_malformed_json(cfg, tmp_path):
    p = tmp_path / "approved.json"
    p.write_text("not json at all", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        append_approved_from_file(
            memory_name="kb", approved_path=p, cfg=cfg,
            autogenerate_description=False,
        )


def test_append_approved_rejects_missing_candidates_key(cfg, tmp_path):
    p = tmp_path / "approved.json"
    p.write_text(json.dumps({"facts": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="'candidates' list"):
        append_approved_from_file(
            memory_name="kb", approved_path=p, cfg=cfg,
            autogenerate_description=False,
        )


def test_append_approved_does_not_autogenerate_in_claude_extract_mode(
    cfg, tmp_path, monkeypatch,
):
    """When CLAUDE_PLUGIN_ROOT is set, even append_approved_from_file
    must skip the auto-description LLM call — Claude can describe the
    memory in chat if it wants to.
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/in/cc")
    approved = {"candidates": [
        {"topic": "T", "text": "Fact one.", "source_url": "https://u"},
    ]}
    p = tmp_path / "approved.json"
    p.write_text(json.dumps(approved), encoding="utf-8")

    with patch(
        "skills.neurolearn.analyze.runner.run_analysis",
        side_effect=_BoomLLM(),
    ):
        append_approved_from_file(
            memory_name="no-desc-yet",
            approved_path=p,
            cfg=cfg,
            autogenerate_description=True,   # enabled, but env var blocks it
            analyze_backend="groq",
        )

    m = read_memory("no-desc-yet", cfg=cfg)
    assert m.description == ""  # blank — Claude will describe in chat
    assert "Fact one." in m.body
