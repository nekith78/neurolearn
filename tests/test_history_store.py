"""Tests for history.store — persistent log of research/subscribes runs."""
from pathlib import Path

from skills.neurolearn.history.store import (
    RunEntry,
    append_run,
    list_runs,
    get_run,
)


def _run(rid="r1", rtype="research", query="X"):
    return RunEntry(
        id=rid, type=rtype, timestamp="2026-05-12T14:00:00Z",
        query=query, group=None,
        output="/tmp/out", videos_found=5,
        analyze_backend="gemini",
        analyze_prompt_preview="prompt...",
        status="ok",
    )


def test_append_then_list(tmp_path: Path):
    p = tmp_path / "history.toml"
    append_run(p, _run(rid="r1"))
    append_run(p, _run(rid="r2"))
    out = list_runs(p)
    assert len(out) == 2
    assert out[0].id in ("r1", "r2")


def test_list_runs_empty_missing_file(tmp_path: Path):
    assert list_runs(tmp_path / "missing.toml") == []


def test_list_runs_limit(tmp_path: Path):
    p = tmp_path / "history.toml"
    for i in range(5):
        append_run(p, _run(rid=f"r{i}"))
    assert len(list_runs(p, limit=3)) == 3


def test_list_runs_filter_by_type(tmp_path: Path):
    p = tmp_path / "history.toml"
    append_run(p, _run(rid="r1", rtype="research"))
    append_run(p, _run(rid="r2", rtype="subscribes"))
    append_run(p, _run(rid="r3", rtype="research"))
    out = list_runs(p, type_filter="research")
    assert len(out) == 2
    assert all(r.type == "research" for r in out)


def test_get_run_by_id(tmp_path: Path):
    p = tmp_path / "history.toml"
    append_run(p, _run(rid="alpha"))
    append_run(p, _run(rid="beta"))
    r = get_run(p, "beta")
    assert r is not None
    assert r.id == "beta"
    assert get_run(p, "missing") is None


def test_list_runs_newest_first(tmp_path: Path):
    p = tmp_path / "history.toml"
    e1 = _run(rid="r1")
    e1.timestamp = "2026-05-10T00:00:00Z"
    e2 = _run(rid="r2")
    e2.timestamp = "2026-05-12T00:00:00Z"
    append_run(p, e1)
    append_run(p, e2)
    out = list_runs(p)
    assert out[0].id == "r2"  # newer first
    assert out[1].id == "r1"
