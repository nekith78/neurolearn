"""Tests for `manifest.research` provenance (v0.10.7 Fix D).

YouTube's `ytsearch:` ranking shifts minute-to-minute, so two
back-to-back research runs of the same command can return different
video sets (12 vs 15 in the Windows debug report). Without recording
the search parameters and time-of-search inside `manifest.json`,
debugging "why are these videos here" is impossible.

This test suite proves the provenance block:
  * gets written for research batches,
  * stays absent for non-research batches (channel/manual URL list),
  * captures every input that influences search.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from skills.neurolearn.utils.output_writer import (
    BatchMeta, write_manifest_json,
)


def test_manifest_includes_research_block_when_set(tmp_path: Path):
    """Happy path: meta.research populated → JSON has a top-level
    `research` key with the same shape."""
    meta = BatchMeta(
        batch_name="research_2026-05-19_test",
        created_at=datetime(2026, 5, 19, 12, 0, 0),
        source_type="mixed",
        source_url=None,
        backend="subtitles",
        backend_options={},
        language="auto",
        research={
            "query": "claude code parallel subagents",
            "queries_by_language": {"en": "claude code parallel subagents"},
            "languages": ["en", "ru"],
            "source_lang_hint": None,
            "limit_per_language": 12,
            "days": 365,
            "since": None,
            "until": None,
            "match": None,
            "filter": None,
            "in_subscribes": False,
            "group": None,
            "searched_at": "2026-05-19T12:00:00+00:00",
            "candidates_before_checkpoint": 12,
        },
    )
    write_manifest_json([], [], meta, tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text())

    assert "research" in data
    r = data["research"]
    # Spot-check the fields that matter most for reproducibility.
    assert r["query"] == "claude code parallel subagents"
    assert r["languages"] == ["en", "ru"]
    assert r["limit_per_language"] == 12
    assert r["days"] == 365
    assert "searched_at" in r and r["searched_at"]


def test_manifest_omits_research_block_for_non_research_batches(tmp_path: Path):
    """Defensive: a channel/playlist/manual batch never had a search
    query, so `research` must NOT appear in the manifest. Sticking a
    null in would be confusing — absence == not-research."""
    meta = BatchMeta(
        batch_name="channel_AnthropicAI",
        created_at=datetime(2026, 5, 19, 12, 0, 0),
        source_type="channel",
        source_url="https://www.youtube.com/@AnthropicAI",
        backend="subtitles",
        backend_options={},
        language="auto",
        research=None,
    )
    write_manifest_json([], [], meta, tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert "research" not in data


def test_research_block_captures_search_parameters_user_typed(tmp_path: Path):
    """Round-trip every research parameter the user passed at the
    command line. Ensures `--rerun-from <batch>` (future) can build the
    same query without asking the user to retype anything."""
    meta = BatchMeta(
        batch_name="r_2026-05-19_x",
        created_at=datetime(2026, 5, 19),
        source_type="mixed", source_url=None,
        backend="smart", backend_options={}, language="auto",
        research={
            "query": "Q",
            "queries_by_language": {"en": "Q", "ru": "Q-ru"},
            "languages": ["en", "ru"],
            "source_lang_hint": "en",
            "limit_per_language": 20,
            "days": None,
            "since": "2026-04-01",
            "until": "2026-05-01",
            "match": "foo",
            "filter": "only commands",
            "in_subscribes": True,
            "group": "ai",
            "searched_at": "2026-05-19T12:00:00+00:00",
            "candidates_before_checkpoint": 7,
        },
    )
    write_manifest_json([], [], meta, tmp_path)
    r = json.loads((tmp_path / "manifest.json").read_text())["research"]

    # Every CLI flag the user passed shows up under a stable key.
    for key in (
        "query", "queries_by_language", "languages", "source_lang_hint",
        "limit_per_language", "days", "since", "until", "match", "filter",
        "in_subscribes", "group", "searched_at",
        "candidates_before_checkpoint",
    ):
        assert key in r, f"missing {key!r} in research block: {r.keys()}"
