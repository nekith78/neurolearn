"""Tests for the memory-file storage layer (memory/store.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from skills.neurolearn.config import Config
from skills.neurolearn.memory.store import (
    MemoryFile, append_facts_to_body, delete_memory, list_memories,
    memory_path, memories_dir, parse_memory, read_memory, rename_memory,
    write_memory,
)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(memories_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_write_and_read_round_trip(cfg, tmp_path):
    m = MemoryFile(
        name="claude-tips",
        description="Tips and tricks for Claude Code.",
    )
    write_memory(m, cfg=cfg)

    m2 = read_memory("claude-tips", cfg=cfg)
    assert m2.name == "claude-tips"
    assert m2.description == "Tips and tricks for Claude Code."
    assert m2.created  # auto-filled
    assert m2.last_updated  # auto-filled
    assert m2.sources == 0
    assert m2.body == ""


def test_round_trip_multi_line_description(cfg):
    m = MemoryFile(
        name="multi",
        description="Line one of description.\nLine two with more detail.\nLine three.",
    )
    write_memory(m, cfg=cfg)
    m2 = read_memory("multi", cfg=cfg)
    assert m2.description == "Line one of description.\nLine two with more detail.\nLine three."


def test_round_trip_with_special_chars_in_description(cfg):
    m = MemoryFile(
        name="quoted",
        description='He said "hello" and that was it.',
    )
    write_memory(m, cfg=cfg)
    m2 = read_memory("quoted", cfg=cfg)
    assert "hello" in m2.description


def test_round_trip_preserves_body(cfg):
    m = MemoryFile(
        name="body-test",
        description="x",
        body="## Topic\n- Fact one\n- Fact two\n\nSource: https://example.com\n",
    )
    write_memory(m, cfg=cfg)
    m2 = read_memory("body-test", cfg=cfg)
    assert "Topic" in m2.body
    assert "Fact one" in m2.body


# ---------------------------------------------------------------------------
# Naming / slugification
# ---------------------------------------------------------------------------

def test_name_is_slugified_to_kebab_case(cfg, tmp_path):
    m = MemoryFile(name="My Tips & Notes")
    p = write_memory(m, cfg=cfg)
    # Slug strips special chars, replaces spaces with hyphens, lowercases
    assert p.name == "my-tips-notes.md"


def test_can_read_back_by_original_or_slug_name(cfg):
    m = MemoryFile(name="Claude Tips")
    write_memory(m, cfg=cfg)
    # Both forms find the same file
    by_original = read_memory("Claude Tips", cfg=cfg)
    by_slug = read_memory("claude-tips", cfg=cfg)
    assert by_original.body == by_slug.body


# ---------------------------------------------------------------------------
# List / rename / delete
# ---------------------------------------------------------------------------

def test_list_memories_returns_all(cfg):
    write_memory(MemoryFile(name="a", description="A."), cfg=cfg)
    write_memory(MemoryFile(name="b", description="B."), cfg=cfg)
    write_memory(MemoryFile(name="c", description="C."), cfg=cfg)
    names = sorted(m.name for m in list_memories(cfg=cfg))
    assert names == ["a", "b", "c"]


def test_list_memories_returns_empty_when_dir_missing(cfg):
    # The fixture's tmp_path exists but no .md files yet
    assert list_memories(cfg=cfg) == []


def test_rename_updates_filename_and_frontmatter(cfg):
    write_memory(
        MemoryFile(name="old-name", description="d", body="b"),
        cfg=cfg,
    )
    new_path = rename_memory("old-name", "new-name", cfg=cfg)
    assert new_path.name == "new-name.md"
    assert not memory_path("old-name", cfg=cfg).exists()
    # Frontmatter `name:` field also updated
    m = read_memory("new-name", cfg=cfg)
    assert m.name == "new-name"
    assert m.description == "d"
    assert "b" in m.body


def test_rename_rejects_when_target_exists(cfg):
    write_memory(MemoryFile(name="a"), cfg=cfg)
    write_memory(MemoryFile(name="b"), cfg=cfg)
    with pytest.raises(FileExistsError):
        rename_memory("a", "b", cfg=cfg)


def test_rename_missing_source_raises(cfg):
    with pytest.raises(FileNotFoundError):
        rename_memory("nonexistent", "whatever", cfg=cfg)


def test_delete_removes_file(cfg):
    write_memory(MemoryFile(name="trash"), cfg=cfg)
    p = memory_path("trash", cfg=cfg)
    assert p.exists()
    delete_memory("trash", cfg=cfg)
    assert not p.exists()


def test_delete_missing_raises(cfg):
    with pytest.raises(FileNotFoundError):
        delete_memory("not-there", cfg=cfg)


# ---------------------------------------------------------------------------
# append_facts_to_body
# ---------------------------------------------------------------------------

def test_append_facts_groups_by_topic(cfg):
    m = MemoryFile(name="grouped")
    append_facts_to_body(
        m,
        [
            {"topic": "Hooks", "text": "Hook A.", "source_timestamp": "1:00-2:00"},
            {"topic": "Hooks", "text": "Hook B.", "source_timestamp": None},
            {"topic": "Slash commands", "text": "Slash A.", "source_timestamp": None},
        ],
        source_url="https://youtu.be/abc",
        when="2026-05-26T00:00:00Z",
    )
    body = m.body
    assert "## 2026-05-26 — Hooks" in body
    assert "## 2026-05-26 — Slash commands" in body
    assert "- Hook A." in body
    assert "- Hook B." in body
    assert "- Slash A." in body
    assert "Source: https://youtu.be/abc" in body
    assert m.sources == 1


def test_append_facts_increments_sources_counter(cfg):
    m = MemoryFile(name="counter")
    append_facts_to_body(m, [{"text": "First."}], source_url="u1", when="2026-05-26T")
    append_facts_to_body(m, [{"text": "Second."}], source_url="u2", when="2026-05-27T")
    assert m.sources == 2


def test_append_empty_facts_is_noop(cfg):
    m = MemoryFile(name="empty")
    append_facts_to_body(m, [], source_url="u", when="2026-05-26T")
    assert m.sources == 0
    assert m.body == ""


def test_append_prepends_newest_section_first(cfg):
    m = MemoryFile(name="ordered")
    append_facts_to_body(
        m, [{"topic": "Old", "text": "Old fact."}],
        source_url="u1", when="2026-05-20T",
    )
    append_facts_to_body(
        m, [{"topic": "New", "text": "New fact."}],
        source_url="u2", when="2026-05-26T",
    )
    # Newest sections come first so users see latest at the top
    assert m.body.index("New fact.") < m.body.index("Old fact.")


# ---------------------------------------------------------------------------
# parse_memory — backwards-compat with files lacking frontmatter
# ---------------------------------------------------------------------------

def test_parse_memory_no_frontmatter_treats_all_as_body():
    m = parse_memory("Just some content\nnot a memory file properly", fallback_name="x")
    assert m.body == "Just some content\nnot a memory file properly"
    assert m.name == "x"


def test_parse_memory_with_minimal_frontmatter():
    text = '''---
name: minimal
description: "Just one line."
created: 2026-01-01
sources: 5
last_updated: 2026-05-26
---

## Section
- Fact.
'''
    m = parse_memory(text)
    assert m.name == "minimal"
    assert m.description == "Just one line."
    assert m.sources == 5
    assert "Fact." in m.body
