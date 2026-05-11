# youtube-transcribe v0.7 — `research` + `subscribes` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить две команды — `research "query"` для широкого тематического поиска (multi-lang + filters + analyze) и `subscribes` для отслеживания персональных каналов (RSS-first stateful incremental), объединённые общим pipeline core.

**Architecture:** Извлекаем `_run_batch_pipeline` из v0.6 `batch_cmd` как общий core (одна функция → две команды поверх). Поверх core три новых модуля: `research/` (yt-dlp search + LLM translation), `subscribes/` (TOML store + RSS + state) и `shared/` (date filter, substring match, LLM pre-screen). Доверяем ранжированию YouTube — собственной формулы качества нет.

**Tech Stack:** Python 3.11+, uv, Click 8, Rich, questionary, tomlkit, langdetect, xml.etree.ElementTree (stdlib), urllib.request (stdlib). Никаких новых runtime deps.

**Spec:** `docs/specs/2026-05-12-youtube-transcribe-v07-research-subscribes-design.md` (commit feb83b7).

---

## Структура файлов

```
youtube-transcribe/
├── pyproject.toml                                       ← Task 1 (version 0.7.0-dev)
├── .github/workflows/test.yml                           ← Task 32 (+python 3.13)
├── skills/youtube_transcribe/
│   ├── __init__.py                                      ← Task 1 (version bump)
│   ├── transcribe.py                                    ← Tasks 13, 18, 20, 21, 27
│   ├── shared/                                          ← NEW
│   │   ├── __init__.py                                  ← Task 2
│   │   ├── date_filter.py                               ← Task 3
│   │   ├── match.py                                     ← Task 4
│   │   └── llm_screen.py                                ← Task 5
│   ├── research/                                        ← NEW
│   │   ├── __init__.py                                  ← Task 2
│   │   ├── translator.py                                ← Task 6
│   │   ├── source.py                                    ← Task 7
│   │   └── pipeline.py                                  ← Task 16
│   ├── subscribes/                                      ← NEW
│   │   ├── __init__.py                                  ← Task 2
│   │   ├── store.py                                     ← Task 8
│   │   ├── state.py                                     ← Task 9
│   │   ├── channel_resolver.py                          ← Task 10
│   │   ├── rss.py                                       ← Task 11
│   │   ├── group.py                                     ← Task 12
│   │   ├── pipeline.py                                  ← Task 17
│   │   ├── cli.py                                       ← Tasks 19, 20
│   │   └── schedule.py                                  ← Tasks 23-27
│   ├── history/                                         ← NEW
│   │   ├── __init__.py                                  ← Task 2
│   │   ├── store.py                                     ← Task 14
│   │   └── cli.py                                       ← Task 15
│   └── webui/
│       └── app.py                                       ← Tasks 28-29 (+tabs)
└── tests/
    ├── test_shared_date_filter.py                       ← Task 3
    ├── test_shared_match.py                             ← Task 4
    ├── test_shared_llm_screen.py                        ← Task 5
    ├── test_research_translator.py                      ← Task 6
    ├── test_research_source.py                          ← Task 7
    ├── test_subscribes_store.py                         ← Task 8
    ├── test_subscribes_state.py                         ← Task 9
    ├── test_subscribes_channel_resolver.py              ← Task 10
    ├── test_subscribes_rss.py                           ← Task 11
    ├── test_subscribes_group.py                         ← Task 12
    ├── test_batch_pipeline_refactor.py                  ← Task 13
    ├── test_history_store.py                            ← Task 14
    ├── test_history_cli.py                              ← Task 15
    ├── test_research_pipeline.py                        ← Task 16
    ├── test_subscribes_pipeline.py                      ← Task 17
    ├── test_cli_research.py                             ← Tasks 18, 22
    ├── test_cli_subscribes.py                           ← Tasks 19, 20
    ├── test_subscribes_schedule_*.py                    ← Tasks 23-27
    └── (existing v0.6 tests — must remain green)
```

## Фазы

- **Phase 1 (Tasks 1–2):** Bootstrap — version + scaffolding.
- **Phase 2 (Tasks 3–5):** Shared filters — date, substring, LLM-screen.
- **Phase 3 (Tasks 6–7):** Research source — translator + multi-lang yt-dlp search.
- **Phase 4 (Tasks 8–12):** Subscribes core — store, state, channel resolver, RSS, group.
- **Phase 5 (Task 13):** Refactor `_run_batch_pipeline` extraction.
- **Phase 6 (Tasks 14–15):** History store + CLI.
- **Phase 7 (Tasks 16–17):** Pipeline orchestration — research + subscribes.
- **Phase 8 (Tasks 18–22):** CLI commands — research, subscribes group, history, cross-pollination.
- **Phase 9 (Tasks 23–27):** Schedule helpers — cross-OS snippet generation.
- **Phase 10 (Tasks 28–29):** Web UI tabs.
- **Phase 11 (Tasks 30–32):** README/CHANGELOG, SKILL.md, release.

---

## Pre-flight (один раз перед началом)

- [ ] Убедиться что v0.6.0 в working state:

  Run: `git log --oneline -3`
  Expected: видны `21caf5c release: v0.6.0` или новее (включая `acc2322 fix(cli): wire __version__`).

  Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
  Expected: `1 failed, 614 passed, 2 skipped` (1 failed — pre-existing `test_webui.py::test_build_ui_returns_blocks`, gradio API mismatch, не v0.7).

- [ ] Опционально создать ветку:

  ```bash
  git checkout -b v0.7-research-subscribes
  ```

  Альтернатива — работа в `main` (стиль проекта).

---

# Phase 1 — Bootstrap v0.7

### Task 1: pyproject + version bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `skills/youtube_transcribe/__init__.py`

- [ ] **Step 1: Bump version в `pyproject.toml`**

В `[project] version` изменить:

```toml
version = "0.7.0-dev"
```

- [ ] **Step 2: Bump version в `__init__.py`**

`skills/youtube_transcribe/__init__.py`:

```python
"""youtube-transcribe — universal transcription skill."""
__version__ = "0.7.0-dev"
```

- [ ] **Step 3: Sync (без новых deps)**

Run: `uv sync --extra dev`
Expected: ничего нового не ставится (v0.7 не добавляет runtime deps).

- [ ] **Step 4: Запустить v0.6 тесты для базовой регрессии**

Run: `uv run pytest --tb=no -q`
Expected: `1 failed, 614 passed, 2 skipped` (тот же расклад что в pre-flight).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml skills/youtube_transcribe/__init__.py
git commit -m "$(cat <<'EOF'
build(v0.7): bump to 0.7.0-dev

v0.7 adds research + subscribes commands. No new runtime dependencies
(RSS via stdlib xml.etree + urllib.request; everything else already
in v0.6 deps).
EOF
)"
```

---

### Task 2: Scaffold пакетов

**Files:**
- Create: `skills/youtube_transcribe/shared/__init__.py`
- Create: `skills/youtube_transcribe/research/__init__.py`
- Create: `skills/youtube_transcribe/subscribes/__init__.py`
- Create: `skills/youtube_transcribe/history/__init__.py`
- Create: `tests/test_v07_scaffolding.py`

- [ ] **Step 1: Создать новые пакеты**

```bash
mkdir -p skills/youtube_transcribe/shared
mkdir -p skills/youtube_transcribe/research
mkdir -p skills/youtube_transcribe/subscribes
mkdir -p skills/youtube_transcribe/history
```

Содержимое каждого `__init__.py`:

```python
"""<module> — youtube-transcribe v0.7."""
```

(заменить `<module>` на `shared` / `research` / `subscribes` / `history` соответственно)

- [ ] **Step 2: Написать smoke-тест**

`tests/test_v07_scaffolding.py`:

```python
"""Smoke test: v0.7 packages exist and import cleanly."""


def test_shared_imports():
    import skills.youtube_transcribe.shared  # noqa: F401


def test_research_imports():
    import skills.youtube_transcribe.research  # noqa: F401


def test_subscribes_imports():
    import skills.youtube_transcribe.subscribes  # noqa: F401


def test_history_imports():
    import skills.youtube_transcribe.history  # noqa: F401


def test_version_is_v07():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.7.")
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_v07_scaffolding.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add skills/youtube_transcribe/shared/__init__.py \
        skills/youtube_transcribe/research/__init__.py \
        skills/youtube_transcribe/subscribes/__init__.py \
        skills/youtube_transcribe/history/__init__.py \
        tests/test_v07_scaffolding.py
git commit -m "feat(v0.7): scaffold shared/research/subscribes/history packages"
```

---

# Phase 2 — Shared filters

### Task 3: shared/date_filter.py

**Files:**
- Create: `skills/youtube_transcribe/shared/date_filter.py`
- Create: `tests/test_shared_date_filter.py`

- [ ] **Step 1: Write failing tests**

`tests/test_shared_date_filter.py`:

```python
"""Tests for shared.date_filter — --days / --since-until parsing."""
from datetime import date, datetime, timedelta, timezone

import pytest

from skills.youtube_transcribe.shared.date_filter import (
    DateWindow,
    parse_window,
    in_window,
)


def test_parse_days_simple():
    w = parse_window(days=30, since=None, until=None, now=date(2026, 5, 12))
    assert w.start == date(2026, 4, 12)
    assert w.end == date(2026, 5, 12)


def test_parse_since_until():
    w = parse_window(days=None, since=date(2024, 1, 1), until=date(2024, 12, 31),
                     now=date(2026, 5, 12))
    assert w.start == date(2024, 1, 1)
    assert w.end == date(2024, 12, 31)


def test_parse_since_only():
    """--since without --until defaults end to now."""
    w = parse_window(days=None, since=date(2024, 6, 1), until=None,
                     now=date(2026, 5, 12))
    assert w.start == date(2024, 6, 1)
    assert w.end == date(2026, 5, 12)


def test_parse_until_only_requires_since():
    with pytest.raises(ValueError, match="--until requires --since"):
        parse_window(days=None, since=None, until=date(2024, 12, 31),
                     now=date(2026, 5, 12))


def test_days_and_since_mutex():
    with pytest.raises(ValueError, match="mutually exclusive"):
        parse_window(days=30, since=date(2024, 1, 1), until=None,
                     now=date(2026, 5, 12))


def test_in_window_inclusive():
    w = DateWindow(start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert in_window(date(2024, 6, 15), w) is True
    assert in_window(date(2024, 1, 1), w) is True
    assert in_window(date(2024, 12, 31), w) is True
    assert in_window(date(2023, 12, 31), w) is False
    assert in_window(date(2025, 1, 1), w) is False


def test_in_window_with_datetime():
    """Accept datetime input — strip to date."""
    w = DateWindow(start=date(2024, 1, 1), end=date(2024, 1, 31))
    assert in_window(datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc), w) is True
    assert in_window(datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc), w) is False


def test_zero_days_raises():
    with pytest.raises(ValueError, match="days must be positive"):
        parse_window(days=0, since=None, until=None, now=date(2026, 5, 12))


def test_negative_days_raises():
    with pytest.raises(ValueError, match="days must be positive"):
        parse_window(days=-5, since=None, until=None, now=date(2026, 5, 12))


def test_reverse_range_raises():
    with pytest.raises(ValueError, match="--since must be before --until"):
        parse_window(days=None, since=date(2024, 12, 1), until=date(2024, 6, 1),
                     now=date(2026, 5, 12))


def test_no_args_returns_none():
    """No --days and no --since means caller decides (e.g. stateful subscribes)."""
    w = parse_window(days=None, since=None, until=None, now=date(2026, 5, 12))
    assert w is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_shared_date_filter.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `shared/date_filter.py`**

`skills/youtube_transcribe/shared/date_filter.py`:

```python
"""Parse --days / --since / --until into a date window, and test membership.

Used by research and subscribes commands. Returns None when caller
provided no filter (caller handles default, e.g. stateful subscribes).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class DateWindow:
    """Inclusive date window [start, end]."""
    start: date
    end: date


def parse_window(
    *,
    days: int | None,
    since: date | None,
    until: date | None,
    now: date,
) -> DateWindow | None:
    """Return a DateWindow or None if no filter given.

    Raises ValueError on mutex violations and invalid inputs.
    """
    if days is not None and (since is not None or until is not None):
        raise ValueError("--days and --since/--until are mutually exclusive")

    if days is not None:
        if days <= 0:
            raise ValueError("days must be positive")
        return DateWindow(start=now - timedelta(days=days), end=now)

    if since is None and until is None:
        return None

    if since is None and until is not None:
        raise ValueError("--until requires --since")

    end = until if until is not None else now
    if since > end:
        raise ValueError("--since must be before --until")
    return DateWindow(start=since, end=end)


def in_window(value: date | datetime, window: DateWindow) -> bool:
    """Inclusive membership test. Accepts date or datetime."""
    d = value.date() if isinstance(value, datetime) else value
    return window.start <= d <= window.end
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_shared_date_filter.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/shared/date_filter.py \
        tests/test_shared_date_filter.py
git commit -m "feat(v0.7): shared.date_filter — --days / --since-until parsing"
```

---

### Task 4: shared/match.py — substring filter

**Files:**
- Create: `skills/youtube_transcribe/shared/match.py`
- Create: `tests/test_shared_match.py`

- [ ] **Step 1: Write failing tests**

`tests/test_shared_match.py`:

```python
"""Tests for shared.match — case-insensitive substring filter."""
from dataclasses import dataclass

from skills.youtube_transcribe.shared.match import match_titles


@dataclass
class _Cand:
    """Minimal test stand-in for any candidate with a `title` attribute."""
    title: str
    extra: str = ""


def test_simple_substring():
    cands = [_Cand(title="Claude features deep dive"),
             _Cand(title="GPT-5 release notes")]
    out = match_titles(cands, "claude")
    assert len(out) == 1
    assert out[0].title.startswith("Claude")


def test_case_insensitive():
    cands = [_Cand(title="CLAUDE FEATURES"),
             _Cand(title="claude features"),
             _Cand(title="Claude Features")]
    assert len(match_titles(cands, "claude")) == 3


def test_empty_match_returns_all():
    cands = [_Cand(title="a"), _Cand(title="b")]
    assert match_titles(cands, "") == cands
    assert match_titles(cands, None) == cands


def test_no_matches_returns_empty():
    cands = [_Cand(title="dogs"), _Cand(title="cats")]
    assert match_titles(cands, "birds") == []


def test_preserves_order():
    cands = [_Cand(title="Z claude one"),
             _Cand(title="A claude two"),
             _Cand(title="M claude three")]
    out = match_titles(cands, "claude")
    assert [c.title for c in out] == [
        "Z claude one", "A claude two", "M claude three",
    ]


def test_whitespace_in_match_kept():
    """'new release' shouldn't match 'newrelease'."""
    cands = [_Cand(title="Newrelease party"),
             _Cand(title="New release announcement")]
    out = match_titles(cands, "new release")
    assert len(out) == 1
    assert out[0].title == "New release announcement"


def test_unicode_works():
    cands = [_Cand(title="Клод новинки"),
             _Cand(title="GPT releases")]
    out = match_titles(cands, "клод")
    assert len(out) == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_shared_match.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `shared/match.py`**

`skills/youtube_transcribe/shared/match.py`:

```python
"""Case-insensitive substring filter on a `title` attribute.

Used by --match flag in research and subscribes. Offline, no LLM call.
Whitespace inside the match pattern is preserved (literal match).
"""
from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")


def match_titles(candidates: Iterable[T], pattern: str | None) -> list[T]:
    """Return candidates whose `.title` contains `pattern` (case-insensitive).

    Empty/None pattern → return all candidates unchanged (no-op filter).
    Pattern is matched via `str.lower().find(...) != -1` on `.title.lower()`.
    """
    if not pattern:
        return list(candidates)
    needle = pattern.lower()
    return [c for c in candidates if needle in (c.title or "").lower()]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_shared_match.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/shared/match.py \
        tests/test_shared_match.py
git commit -m "feat(v0.7): shared.match — case-insensitive substring filter on title"
```

---

### Task 5: shared/llm_screen.py — LLM pre-screening

**Files:**
- Create: `skills/youtube_transcribe/shared/llm_screen.py`
- Create: `tests/test_shared_llm_screen.py`

- [ ] **Step 1: Write failing tests**

`tests/test_shared_llm_screen.py`:

```python
"""Tests for shared.llm_screen — LLM-based candidate filtering."""
from dataclasses import dataclass
from unittest.mock import patch

from skills.youtube_transcribe.shared.llm_screen import (
    screen_candidates,
    _build_prompt,
)


@dataclass
class _Cand:
    title: str
    channel: str = "ch"
    upload_date: str | None = None
    duration_sec: int | None = None


def test_screen_returns_subset_from_llm():
    cands = [_Cand(title="A"), _Cand(title="B"), _Cand(title="C")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
        return_value="[1, 3]",
    ):
        out = screen_candidates(cands, "any filter",
                                backend="gemini", api_key="k")
    assert len(out) == 2
    assert out[0].title == "A"
    assert out[1].title == "C"


def test_screen_invalid_json_returns_all():
    """If LLM returns garbage, fall back to keeping all candidates."""
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
        return_value="LLM gibberish here",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    assert out == cands


def test_screen_empty_response_returns_all():
    cands = [_Cand(title="A")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
        return_value="",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    assert out == cands


def test_screen_empty_filter_returns_all_without_llm_call():
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
    ) as mock_run:
        out = screen_candidates(cands, "", backend="gemini", api_key="k")
    assert out == cands
    mock_run.assert_not_called()


def test_screen_indices_out_of_range_ignored():
    cands = [_Cand(title="A"), _Cand(title="B")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
        return_value="[1, 5, 99]",
    ):
        out = screen_candidates(cands, "filter", backend="gemini", api_key="k")
    # Only index 1 (= "A") is valid; 5 and 99 silently dropped
    assert len(out) == 1
    assert out[0].title == "A"


def test_prompt_includes_metadata():
    cands = [_Cand(title="Claude tutorial", channel="@anth",
                   upload_date="2024-05-01", duration_sec=720)]
    prompt = _build_prompt(cands, "best ones")
    assert "best ones" in prompt
    assert "Claude tutorial" in prompt
    assert "@anth" in prompt
    assert "2024-05-01" in prompt
    assert "12:00" in prompt or "720" in prompt
    assert "JSON" in prompt


def test_prompt_handles_missing_fields():
    cands = [_Cand(title="X", channel=None, upload_date=None,
                   duration_sec=None)]
    prompt = _build_prompt(cands, "f")
    assert "X" in prompt


def test_screen_ollama_no_key():
    cands = [_Cand(title="A")]
    with patch(
        "skills.youtube_transcribe.shared.llm_screen.run_analysis",
        return_value="[1]",
    ) as mock:
        screen_candidates(cands, "f", backend="ollama", api_key=None)
    kwargs = mock.call_args.kwargs
    assert kwargs["backend"] == "ollama"
    assert kwargs["api_key"] is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_shared_llm_screen.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `shared/llm_screen.py`**

`skills/youtube_transcribe/shared/llm_screen.py`:

```python
"""LLM-based pre-screening of candidate videos by title+metadata.

Used by --filter flag in research and subscribes. Sends a structured
prompt to the chosen LLM backend and expects a JSON array of 1-based
indices back. Falls back to keeping all candidates if the response
can't be parsed.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from skills.youtube_transcribe.analyze.runner import run_analysis

T = TypeVar("T")


def screen_candidates(
    candidates: list[T],
    filter_text: str | None,
    *,
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> list[T]:
    """Return subset chosen by the LLM, or all candidates on parse failure.

    `candidates` must have `.title` and optionally `.channel`,
    `.upload_date`, `.duration_sec` attributes.
    """
    if not filter_text or not candidates:
        return list(candidates)

    prompt = _build_prompt(candidates, filter_text)
    response = run_analysis(
        prompt,
        backend=backend,
        api_key=api_key,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
    )

    indices = _extract_indices(response, total=len(candidates))
    if indices is None:
        return list(candidates)
    return [candidates[i - 1] for i in indices if 1 <= i <= len(candidates)]


def _build_prompt(candidates: list, filter_text: str) -> str:
    lines = [
        "You select videos relevant to the user's filter from a candidate list.",
        "",
        f"User filter: {filter_text}",
        "",
        "Candidates (1-indexed):",
    ]
    for i, c in enumerate(candidates, start=1):
        title = c.title or "(no title)"
        channel = getattr(c, "channel", None) or "?"
        date = getattr(c, "upload_date", None) or "?"
        dur_sec = getattr(c, "duration_sec", None)
        dur = _fmt_dur(dur_sec) if dur_sec else "?"
        lines.append(f"[{i}] {title} — {channel} — {date} — {dur}")
    lines.extend([
        "",
        "Return ONLY a JSON array of selected indices (e.g. [1, 3, 5]).",
        "No prose, no explanation, no code fence.",
    ])
    return "\n".join(lines)


def _fmt_dur(sec: int) -> str:
    mm, ss = divmod(sec, 60)
    hh, mm = divmod(mm, 60)
    return f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"


def _extract_indices(response: str, *, total: int) -> list[int] | None:
    """Parse JSON array of ints from LLM output. None on failure."""
    if not response or not response.strip():
        return None
    # Find first [...] in response (LLM may wrap in code fence or text).
    m = re.search(r"\[[^\]]*\]", response)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    try:
        return [int(x) for x in parsed]
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_shared_llm_screen.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/shared/llm_screen.py \
        tests/test_shared_llm_screen.py
git commit -m "feat(v0.7): shared.llm_screen — LLM pre-screening of candidates"
```

---

# Phase 3 — Research source

### Task 6: research/translator.py — LLM query translation

**Files:**
- Create: `skills/youtube_transcribe/research/translator.py`
- Create: `tests/test_research_translator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_research_translator.py`:

```python
"""Tests for research.translator — LLM query translation per language."""
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.research.translator import (
    detect_language,
    translate_query,
    build_queries_per_language,
)


def test_detect_language_ru():
    assert detect_language("Клод новинки за неделю") == "ru"


def test_detect_language_en():
    assert detect_language("Claude new features this week") == "en"


def test_detect_language_short_string():
    """langdetect can fail on very short input — should return None."""
    result = detect_language("hi")
    # langdetect may or may not detect; both None and a code are acceptable
    assert result is None or isinstance(result, str)


def test_translate_query_skip_same_language():
    """If target == source language, return query as-is, no LLM call."""
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
    ) as mock_run:
        out = translate_query("Claude new features", target="en", source="en",
                              backend="gemini", api_key="k")
    assert out == "Claude new features"
    mock_run.assert_not_called()


def test_translate_query_calls_llm():
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
        return_value="Клод новинки",
    ) as mock_run:
        out = translate_query("Claude new features", target="ru", source="en",
                              backend="gemini", api_key="k")
    assert out == "Клод новинки"
    mock_run.assert_called_once()
    # Verify prompt mentions both source and target language
    prompt = mock_run.call_args.args[0]
    assert "ru" in prompt.lower() or "russian" in prompt.lower()
    assert "Claude new features" in prompt


def test_translate_query_empty_llm_returns_original():
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
        return_value="",
    ):
        out = translate_query("Claude", target="ru", source="en",
                              backend="gemini", api_key="k")
    assert out == "Claude"


def test_translate_query_strips_quotes_from_llm_output():
    """LLMs love wrapping output in quotes — strip them."""
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
        return_value='"Клод новинки"',
    ):
        out = translate_query("Claude features", target="ru", source="en",
                              backend="gemini", api_key="k")
    assert out == "Клод новинки"


def test_build_queries_for_matching_source_language():
    """If query is in ru and languages=ru,en — ru uses query as-is, en translated."""
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
        return_value="Claude новости",
    ), patch(
        "skills.youtube_transcribe.research.translator.detect_language",
        return_value="ru",
    ):
        out = build_queries_per_language(
            "Клод новости", languages=["ru", "en"],
            backend="gemini", api_key="k",
        )
    assert out["ru"] == "Клод новости"
    assert out["en"] == "Claude новости"


def test_build_queries_unknown_source_uses_first_lang_as_anchor():
    """If language can't be detected, use the query as-is for the first lang
    and translate to the others."""
    with patch(
        "skills.youtube_transcribe.research.translator.run_analysis",
        return_value="<<translated>>",
    ), patch(
        "skills.youtube_transcribe.research.translator.detect_language",
        return_value=None,
    ):
        out = build_queries_per_language(
            "ambiguous", languages=["en", "ru"],
            backend="gemini", api_key="k",
        )
    assert out["en"] == "ambiguous"
    assert out["ru"] == "<<translated>>"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_research_translator.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `research/translator.py`**

`skills/youtube_transcribe/research/translator.py`:

```python
"""LLM-based translation of YouTube search queries between languages.

Translates the user's single query to each requested target language
via the same LLM backend used for analyze/filter. Falls back to the
original query if the LLM returns nothing useful.
"""
from __future__ import annotations

from skills.youtube_transcribe.analyze.runner import run_analysis


def detect_language(text: str) -> str | None:
    """Best-effort language detection. Returns ISO 639-1 code or None."""
    if not text or len(text.strip()) < 3:
        return None
    try:
        from langdetect import detect, DetectorFactory, LangDetectException
        DetectorFactory.seed = 0  # reproducible
        return detect(text)
    except Exception:
        return None


def translate_query(
    query: str,
    *,
    target: str,
    source: str | None,
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Translate `query` to `target` language. Returns original if target==source
    or LLM fails."""
    if source and target == source:
        return query

    prompt = (
        f"Translate the following YouTube search query to {target}. "
        "Keep technical terms, product names, and proper nouns intact "
        "(e.g. 'Claude', 'GPT', 'transformers'). "
        "Return ONLY the translated text, no quotes, no explanation.\n\n"
        f"Query: {query}"
    )

    response = run_analysis(
        prompt,
        backend=backend,
        api_key=api_key,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
    )

    text = (response or "").strip()
    if not text:
        return query
    # LLMs sometimes wrap output in quotes — strip them.
    text = text.strip('"').strip("'").strip()
    return text or query


def build_queries_per_language(
    query: str,
    *,
    languages: list[str],
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> dict[str, str]:
    """Return {lang_code: query_string} for each language in `languages`.

    The language matching the detected source-language gets the query as-is.
    If detection fails, the first language in `languages` is treated as the
    anchor (no translation), others are translated.
    """
    if not languages:
        return {}

    detected = detect_language(query)
    anchor = detected if detected in languages else languages[0]

    out: dict[str, str] = {}
    for lang in languages:
        if lang == anchor:
            out[lang] = query
        else:
            out[lang] = translate_query(
                query, target=lang, source=anchor,
                backend=backend, api_key=api_key,
                ollama_model=ollama_model, ollama_host=ollama_host,
            )
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_research_translator.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/research/translator.py \
        tests/test_research_translator.py
git commit -m "feat(v0.7): research.translator — LLM query translation per language"
```

---

### Task 7: research/source.py — multi-lang yt-dlp search

**Files:**
- Create: `skills/youtube_transcribe/research/source.py`
- Create: `tests/test_research_source.py`

- [ ] **Step 1: Write failing tests**

`tests/test_research_source.py`:

```python
"""Tests for research.source — multi-language yt-dlp search + dedup."""
from datetime import date
from unittest.mock import patch

from skills.youtube_transcribe.research.source import (
    SearchCandidate,
    search_multi_language,
)


def _entry(vid, title, channel="ch", duration=300, upload="20260501"):
    return {
        "id": vid, "title": title, "channel": channel,
        "duration": duration, "upload_date": upload,
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def test_search_single_language():
    """Single language → one yt-dlp call, candidates returned in order."""
    fake_results = {"entries": [_entry("v1", "First"), _entry("v2", "Second")]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake_results,
    ) as mock:
        out = search_multi_language(
            {"en": "Claude features"}, limit=10,
        )
    mock.assert_called_once_with("ytsearch10:Claude features")
    assert len(out) == 2
    assert out[0].video_id == "v1"
    assert out[0].title == "First"


def test_search_multi_language_dedup():
    """Same video_id across languages — dedup keeps first occurrence."""
    def fake_extract(url):
        if "Claude features" in url:
            return {"entries": [_entry("dup", "Claude features"),
                                _entry("en1", "EN only")]}
        elif "Клод" in url:
            return {"entries": [_entry("dup", "Клод фичи"),
                                _entry("ru1", "RU only")]}
        return {"entries": []}

    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        side_effect=fake_extract,
    ):
        out = search_multi_language(
            {"en": "Claude features", "ru": "Клод фичи"}, limit=10,
        )
    video_ids = [c.video_id for c in out]
    # Dup appears once; en1 and ru1 also present
    assert "dup" in video_ids
    assert video_ids.count("dup") == 1
    assert "en1" in video_ids
    assert "ru1" in video_ids


def test_search_skip_entries_without_id():
    """Some yt-dlp results may have None id — skip them."""
    fake = {"entries": [_entry("v1", "OK"), {"id": None, "title": "broken"},
                        None]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=10)
    assert len(out) == 1
    assert out[0].video_id == "v1"


def test_search_parses_upload_date():
    fake = {"entries": [_entry("v1", "T", upload="20240115")]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].upload_date == date(2024, 1, 15)


def test_search_handles_missing_upload_date():
    fake = {"entries": [{"id": "v1", "title": "T", "url": "u", "channel": "c",
                          "duration": 100}]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].upload_date is None


def test_search_empty_queries():
    out = search_multi_language({}, limit=10)
    assert out == []


def test_search_attaches_language_to_candidates():
    """Each candidate remembers which language search produced it (for diagnostics)."""
    fake = {"entries": [_entry("v1", "T")]}
    with patch(
        "skills.youtube_transcribe.research.source._extract_flat",
        return_value=fake,
    ):
        out = search_multi_language({"en": "x"}, limit=5)
    assert out[0].source_language == "en"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_research_source.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `research/source.py`**

`skills/youtube_transcribe/research/source.py`:

```python
"""Multi-language YouTube search via yt-dlp `ytsearchN:query`.

Issues one yt-dlp search per language, dedups results by video_id,
preserves first-occurrence order. No full extract — flat metadata only
(title, channel, duration, upload_date).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from skills.youtube_transcribe.utils.downloader import (
    parse_yt_date,
    _yt_url_from_id,
)


@dataclass
class SearchCandidate:
    """One video from YouTube search results."""
    video_id: str
    url: str
    title: str | None
    channel: str | None
    duration_sec: int | None
    upload_date: date | None
    source_language: str  # which language produced this result


def search_multi_language(
    queries: dict[str, str],
    *,
    limit: int,
) -> list[SearchCandidate]:
    """Issue one yt-dlp search per (lang, query) pair, dedup by video_id.

    Returns candidates in first-occurrence order. Limit applies per language
    (so up to `limit * len(queries)` videos before dedup).
    """
    seen: set[str] = set()
    out: list[SearchCandidate] = []
    for lang, query in queries.items():
        if not query or not query.strip():
            continue
        info = _extract_flat(f"ytsearch{limit}:{query.strip()}")
        entries = (info or {}).get("entries") or []
        for e in entries[:limit]:
            if not e:
                continue
            vid = e.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(SearchCandidate(
                video_id=vid,
                url=e.get("url") or _yt_url_from_id(vid),
                title=e.get("title"),
                channel=e.get("channel") or e.get("uploader"),
                duration_sec=int(e["duration"]) if e.get("duration") else None,
                upload_date=parse_yt_date(e.get("upload_date")),
                source_language=lang,
            ))
    return out


def _extract_flat(url: str) -> dict:
    """Thin yt-dlp wrapper — isolated so tests can mock it."""
    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "skip_download": True,
        "geo_bypass": True,
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_research_source.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/research/source.py \
        tests/test_research_source.py
git commit -m "feat(v0.7): research.source — multi-language yt-dlp search + dedup"
```

---

# Phase 4 — Subscribes core

### Task 8: subscribes/store.py — TOML CRUD

**Files:**
- Create: `skills/youtube_transcribe/subscribes/store.py`
- Create: `tests/test_subscribes_store.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_store.py`:

```python
"""Tests for subscribes.store — TOML read/write with comment preservation."""
from pathlib import Path

import pytest

from skills.youtube_transcribe.subscribes.store import (
    Channel,
    load_subscribes,
    save_subscribes,
    add_channel,
    remove_channel,
    find_channel,
)


def test_load_missing_file_returns_empty(tmp_path: Path):
    assert load_subscribes(tmp_path / "missing.toml") == []


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "sub.toml"
    channels = [
        Channel(url="https://www.youtube.com/@A", handle="@A",
                channel_id="UC_a", group="ai", added="2026-05-12"),
        Channel(url="https://www.youtube.com/@B", handle="@B",
                channel_id="UC_b", group=None, added="2026-05-12"),
    ]
    save_subscribes(p, channels)
    loaded = load_subscribes(p)
    assert len(loaded) == 2
    assert loaded[0].handle == "@A"
    assert loaded[0].group == "ai"
    assert loaded[1].group is None


def test_preserves_comments_on_round_trip(tmp_path: Path):
    """If user added comments — keep them after CLI mutations."""
    p = tmp_path / "sub.toml"
    p.write_text(
        "# my favorite ai channels\n\n"
        "[[channels]]\n"
        "url = \"https://www.youtube.com/@A\"\n"
        "handle = \"@A\"\n"
        "channel_id = \"UC_a\"\n"
        "group = \"ai\"\n"
        "added = \"2026-05-12\"\n",
        encoding="utf-8",
    )
    chans = load_subscribes(p)
    add_channel(p, Channel(
        url="https://www.youtube.com/@B", handle="@B",
        channel_id="UC_b", group="ai", added="2026-05-12",
    ))
    out = p.read_text(encoding="utf-8")
    assert "# my favorite ai channels" in out
    assert "@A" in out
    assert "@B" in out


def test_add_duplicate_replaces(tmp_path: Path):
    """Adding same channel_id twice updates instead of duplicating."""
    p = tmp_path / "sub.toml"
    c1 = Channel(url="u1", handle="@A", channel_id="UC_a", group=None,
                 added="2026-05-12")
    add_channel(p, c1)
    c2 = Channel(url="u1", handle="@A", channel_id="UC_a", group="ai",
                 added="2026-05-12")  # different group
    add_channel(p, c2)
    chans = load_subscribes(p)
    assert len(chans) == 1
    assert chans[0].group == "ai"


def test_remove_by_handle(tmp_path: Path):
    p = tmp_path / "sub.toml"
    add_channel(p, Channel(url="u1", handle="@A", channel_id="UC_a",
                            group=None, added="x"))
    add_channel(p, Channel(url="u2", handle="@B", channel_id="UC_b",
                            group=None, added="x"))
    removed = remove_channel(p, "@A")
    assert removed is True
    chans = load_subscribes(p)
    assert len(chans) == 1
    assert chans[0].handle == "@B"


def test_remove_by_url(tmp_path: Path):
    p = tmp_path / "sub.toml"
    add_channel(p, Channel(url="https://www.youtube.com/@A", handle="@A",
                            channel_id="UC_a", group=None, added="x"))
    removed = remove_channel(p, "https://www.youtube.com/@A")
    assert removed is True
    assert load_subscribes(p) == []


def test_remove_missing_returns_false(tmp_path: Path):
    p = tmp_path / "sub.toml"
    assert remove_channel(p, "@nope") is False


def test_find_channel(tmp_path: Path):
    p = tmp_path / "sub.toml"
    add_channel(p, Channel(url="u1", handle="@A", channel_id="UC_a",
                            group=None, added="x"))
    found = find_channel(p, "@A")
    assert found is not None
    assert found.handle == "@A"
    assert find_channel(p, "@nope") is None


def test_load_with_last_seen_fields(tmp_path: Path):
    p = tmp_path / "sub.toml"
    p.write_text(
        "[[channels]]\n"
        "url = \"u\"\n"
        "handle = \"@A\"\n"
        "channel_id = \"UC_a\"\n"
        "added = \"2026-05-12\"\n"
        "last_seen_video_id = \"vid123\"\n"
        "last_seen_published = \"2026-05-10T14:00:00Z\"\n",
        encoding="utf-8",
    )
    chans = load_subscribes(p)
    assert chans[0].last_seen_video_id == "vid123"
    assert chans[0].last_seen_published == "2026-05-10T14:00:00Z"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_store.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `subscribes/store.py`**

`skills/youtube_transcribe/subscribes/store.py`:

```python
"""TOML-backed channel list for subscribes — preserves user comments
through CLI mutations via tomlkit.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

import tomlkit


@dataclass
class Channel:
    """One subscribed YouTube channel."""
    url: str
    handle: str | None
    channel_id: str | None
    group: str | None
    added: str  # YYYY-MM-DD
    last_seen_video_id: str | None = None
    last_seen_published: str | None = None  # ISO 8601


def load_subscribes(path: Path) -> list[Channel]:
    """Load channels from TOML. Returns empty list if file missing."""
    if not path.exists():
        return []
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    raw = doc.get("channels") or []
    return [_from_dict(dict(entry)) for entry in raw]


def save_subscribes(path: Path, channels: list[Channel]) -> None:
    """Write channels to TOML. Overwrites — does NOT preserve comments.

    Use add_channel/remove_channel for incremental edits that preserve comments.
    """
    doc = tomlkit.document()
    arr = tomlkit.aot()
    for c in channels:
        tbl = tomlkit.table()
        for k, v in _to_dict(c).items():
            if v is not None:
                tbl[k] = v
        arr.append(tbl)
    doc["channels"] = arr
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def add_channel(path: Path, channel: Channel) -> None:
    """Add or update a channel by channel_id (or url if id missing).

    Comment-preserving via tomlkit document mutation.
    """
    doc = (
        tomlkit.parse(path.read_text(encoding="utf-8"))
        if path.exists() else tomlkit.document()
    )
    arr = doc.get("channels")
    if arr is None:
        arr = tomlkit.aot()
        doc["channels"] = arr

    key = channel.channel_id or channel.url
    # In-place update if duplicate
    for i, entry in enumerate(list(arr)):
        existing_key = entry.get("channel_id") or entry.get("url")
        if existing_key == key:
            for k, v in _to_dict(channel).items():
                if v is not None:
                    entry[k] = v
            path.write_text(tomlkit.dumps(doc), encoding="utf-8")
            return

    tbl = tomlkit.table()
    for k, v in _to_dict(channel).items():
        if v is not None:
            tbl[k] = v
    arr.append(tbl)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def remove_channel(path: Path, identifier: str) -> bool:
    """Remove channel by handle, url, or channel_id. Returns True if removed."""
    if not path.exists():
        return False
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    arr = doc.get("channels") or []
    for i, entry in enumerate(list(arr)):
        if (entry.get("handle") == identifier or
            entry.get("url") == identifier or
            entry.get("channel_id") == identifier):
            del arr[i]
            path.write_text(tomlkit.dumps(doc), encoding="utf-8")
            return True
    return False


def find_channel(path: Path, identifier: str) -> Channel | None:
    """Find by handle, url, or channel_id."""
    for c in load_subscribes(path):
        if identifier in (c.handle, c.url, c.channel_id):
            return c
    return None


def _to_dict(c: Channel) -> dict:
    return {
        "url": c.url,
        "handle": c.handle,
        "channel_id": c.channel_id,
        "group": c.group,
        "added": c.added,
        "last_seen_video_id": c.last_seen_video_id,
        "last_seen_published": c.last_seen_published,
    }


def _from_dict(d: dict) -> Channel:
    return Channel(
        url=d.get("url", ""),
        handle=d.get("handle"),
        channel_id=d.get("channel_id"),
        group=d.get("group"),
        added=d.get("added", ""),
        last_seen_video_id=d.get("last_seen_video_id"),
        last_seen_published=d.get("last_seen_published"),
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_store.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/store.py \
        tests/test_subscribes_store.py
git commit -m "feat(v0.7): subscribes.store — TOML CRUD with comment preservation"
```

---

### Task 9: subscribes/state.py — last_seen tracking

**Files:**
- Create: `skills/youtube_transcribe/subscribes/state.py`
- Create: `tests/test_subscribes_state.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_state.py`:

```python
"""Tests for subscribes.state — last-seen tracking per channel."""
from pathlib import Path

from skills.youtube_transcribe.subscribes.store import (
    Channel, add_channel, load_subscribes,
)
from skills.youtube_transcribe.subscribes.state import (
    needs_initial_run,
    update_last_seen,
    channels_without_state,
)


def _c(handle="@A", channel_id="UC_a", last_id=None, last_pub=None):
    return Channel(
        url=f"https://www.youtube.com/{handle}",
        handle=handle, channel_id=channel_id,
        group=None, added="2026-05-12",
        last_seen_video_id=last_id, last_seen_published=last_pub,
    )


def test_needs_initial_run_true_when_empty():
    assert needs_initial_run(_c(last_id=None)) is True


def test_needs_initial_run_false_when_state_present():
    assert needs_initial_run(_c(last_id="vid1", last_pub="2026-05-10T14:00:00Z")) is False


def test_channels_without_state_filters():
    chans = [
        _c(handle="@A", last_id="v"),
        _c(handle="@B", last_id=None),
        _c(handle="@C", last_id="v2"),
    ]
    missing = channels_without_state(chans)
    assert len(missing) == 1
    assert missing[0].handle == "@B"


def test_update_last_seen_writes_to_toml(tmp_path: Path):
    p = tmp_path / "sub.toml"
    add_channel(p, _c(handle="@A", channel_id="UC_a"))
    update_last_seen(p, "UC_a", "newvid", "2026-05-12T14:00:00Z")
    loaded = load_subscribes(p)
    assert loaded[0].last_seen_video_id == "newvid"
    assert loaded[0].last_seen_published == "2026-05-12T14:00:00Z"


def test_update_last_seen_missing_channel_silent(tmp_path: Path):
    """Updating state for an unknown channel is a no-op (no crash)."""
    p = tmp_path / "sub.toml"
    add_channel(p, _c(handle="@A", channel_id="UC_a"))
    # No exception:
    update_last_seen(p, "UC_NOTEXIST", "v", "2026-05-12T14:00:00Z")
    loaded = load_subscribes(p)
    assert loaded[0].last_seen_video_id is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_state.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `subscribes/state.py`**

`skills/youtube_transcribe/subscribes/state.py`:

```python
"""Per-channel last-seen tracking for stateful incremental subscribes update.

State is stored in subscribes.toml itself (fields `last_seen_video_id`
and `last_seen_published` per channel). Update happens only after a
successful default-mode run; user-supplied --days/--since overrides
must NOT call this (override = ad-hoc, doesn't disturb incremental).
"""
from __future__ import annotations

from pathlib import Path

from skills.youtube_transcribe.subscribes.store import (
    Channel, load_subscribes, save_subscribes,
)


def needs_initial_run(channel: Channel) -> bool:
    """True if channel has no recorded state — first run needs explicit window."""
    return channel.last_seen_video_id is None


def channels_without_state(channels: list[Channel]) -> list[Channel]:
    """Subset of channels that have never been processed."""
    return [c for c in channels if needs_initial_run(c)]


def update_last_seen(
    path: Path, channel_id: str, video_id: str, published: str,
) -> None:
    """Write `last_seen_*` fields for a channel. No-op if channel missing."""
    channels = load_subscribes(path)
    for c in channels:
        if c.channel_id == channel_id:
            c.last_seen_video_id = video_id
            c.last_seen_published = published
            save_subscribes(path, channels)
            return
    # Silent no-op on unknown channel (defensive)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_state.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/state.py \
        tests/test_subscribes_state.py
git commit -m "feat(v0.7): subscribes.state — last-seen per-channel tracking"
```

---

### Task 10: subscribes/channel_resolver.py — url → channel_id

**Files:**
- Create: `skills/youtube_transcribe/subscribes/channel_resolver.py`
- Create: `tests/test_subscribes_channel_resolver.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_channel_resolver.py`:

```python
"""Tests for subscribes.channel_resolver — url → channel_id via yt-dlp."""
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.subscribes.channel_resolver import (
    resolve_channel,
    ResolvedChannel,
)


def test_resolve_handle_url():
    fake = {
        "channel_id": "UC_abc123",
        "channel": "Anthropic AI",
        "uploader": "Anthropic AI",
    }
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ) as mock:
        out = resolve_channel("https://www.youtube.com/@AnthropicAI")
    assert out.channel_id == "UC_abc123"
    assert out.handle == "@AnthropicAI"
    assert out.url == "https://www.youtube.com/@AnthropicAI"


def test_resolve_canonical_url():
    fake = {
        "channel_id": "UC_xyz",
        "channel": "OpenAI",
    }
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/channel/UC_xyz")
    assert out.channel_id == "UC_xyz"


def test_resolve_strips_trailing_slash():
    fake = {"channel_id": "UC_a", "channel": "A"}
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@A/")
    assert out.url == "https://www.youtube.com/@A"


def test_resolve_extracts_handle_from_url():
    """If yt-dlp doesn't give us a handle, parse it from the URL."""
    fake = {"channel_id": "UC_a", "channel": "TestChannel"}
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@SomeHandle")
    assert out.handle == "@SomeHandle"


def test_resolve_no_channel_id_raises():
    fake = {"channel": "weird"}  # no channel_id
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        with pytest.raises(ValueError, match="channel_id"):
            resolve_channel("https://www.youtube.com/@X")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_channel_resolver.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `subscribes/channel_resolver.py`**

`skills/youtube_transcribe/subscribes/channel_resolver.py`:

```python
"""Resolve a YouTube channel URL to a stable channel_id (UC...).

One-time call on `subscribes add` — result is cached in subscribes.toml
so subsequent operations (RSS, etc.) work directly with channel_id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ResolvedChannel:
    url: str          # canonical, trailing-slash stripped
    handle: str | None  # @handle if present in URL
    channel_id: str   # UC...
    title: str | None


def resolve_channel(url: str) -> ResolvedChannel:
    """Return ResolvedChannel for a YouTube channel URL.

    Raises ValueError if the URL doesn't resolve to a real channel.
    """
    canonical = url.rstrip("/")
    handle = _extract_handle(canonical)
    info = _extract_flat(canonical)
    channel_id = info.get("channel_id")
    if not channel_id:
        raise ValueError(f"could not resolve channel_id for {url}")
    return ResolvedChannel(
        url=canonical,
        handle=handle,
        channel_id=channel_id,
        title=info.get("channel") or info.get("uploader"),
    )


def _extract_handle(url: str) -> str | None:
    """Extract @handle from a YouTube URL, if present."""
    m = re.search(r"/(@[\w\-.]+)", url)
    return m.group(1) if m else None


def _extract_flat(url: str) -> dict:
    """yt-dlp wrapper — isolated for tests to mock."""
    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "skip_download": True,
        "playlist_items": "0",  # only metadata, don't enumerate uploads
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_channel_resolver.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/channel_resolver.py \
        tests/test_subscribes_channel_resolver.py
git commit -m "feat(v0.7): subscribes.channel_resolver — url to channel_id via yt-dlp"
```

---

### Task 11: subscribes/rss.py — RSS feed fetch + parse

**Files:**
- Create: `skills/youtube_transcribe/subscribes/rss.py`
- Create: `tests/test_subscribes_rss.py`
- Create: `tests/data/sample_rss.xml`

- [ ] **Step 1: Create RSS test fixture**

`tests/data/sample_rss.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <yt:channelId>UC_abc123</yt:channelId>
  <title>Sample Channel</title>
  <link rel="alternate" href="https://www.youtube.com/channel/UC_abc123"/>
  <entry>
    <id>yt:video:vid111</id>
    <yt:videoId>vid111</yt:videoId>
    <yt:channelId>UC_abc123</yt:channelId>
    <title>First video — newest</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid111"/>
    <published>2026-05-12T14:00:00+00:00</published>
    <updated>2026-05-12T14:00:00+00:00</updated>
  </entry>
  <entry>
    <id>yt:video:vid222</id>
    <yt:videoId>vid222</yt:videoId>
    <yt:channelId>UC_abc123</yt:channelId>
    <title>Second video — older</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid222"/>
    <published>2026-05-10T09:30:00+00:00</published>
    <updated>2026-05-10T09:30:00+00:00</updated>
  </entry>
  <entry>
    <id>yt:video:vid333</id>
    <yt:videoId>vid333</yt:videoId>
    <yt:channelId>UC_abc123</yt:channelId>
    <title>Third — oldest</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=vid333"/>
    <published>2026-04-30T08:00:00+00:00</published>
    <updated>2026-04-30T08:00:00+00:00</updated>
  </entry>
</feed>
```

- [ ] **Step 2: Write failing tests**

`tests/test_subscribes_rss.py`:

```python
"""Tests for subscribes.rss — fetch + parse YouTube channel RSS feeds."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.subscribes.rss import (
    RssEntry,
    parse_rss,
    fetch_rss,
    rss_url_for_channel,
)


FIXTURE = Path(__file__).parent / "data" / "sample_rss.xml"


def test_rss_url_format():
    url = rss_url_for_channel("UC_abc")
    assert url == "https://www.youtube.com/feeds/videos.xml?channel_id=UC_abc"


def test_parse_rss_three_entries():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert len(entries) == 3
    assert entries[0].video_id == "vid111"
    assert entries[0].title == "First video — newest"


def test_parse_rss_published_as_datetime():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].published == datetime(
        2026, 5, 12, 14, 0, 0, tzinfo=timezone.utc,
    )


def test_parse_rss_channel_id():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].channel_id == "UC_abc123"


def test_parse_rss_url():
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    assert entries[0].url == "https://www.youtube.com/watch?v=vid111"


def test_parse_empty_feed():
    empty = ('<?xml version="1.0"?><feed '
             'xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
             'xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert parse_rss(empty) == []


def test_parse_malformed_returns_empty():
    """Defensive: malformed XML returns empty rather than crashing."""
    assert parse_rss("<not><proper></xml>") == []


def test_fetch_rss_uses_urllib():
    """fetch_rss should fetch via urllib and pass body to parse_rss."""
    body = FIXTURE.read_text(encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.subscribes.rss._http_get",
        return_value=body,
    ) as mock_get:
        out = fetch_rss("UC_abc")
    mock_get.assert_called_once_with(
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC_abc"
    )
    assert len(out) == 3


def test_fetch_rss_network_error_returns_empty():
    with patch(
        "skills.youtube_transcribe.subscribes.rss._http_get",
        side_effect=OSError("network down"),
    ):
        assert fetch_rss("UC_x") == []


def test_filter_after_published(tmp_path: Path):
    """Helper used by pipeline: entries newer than a reference timestamp."""
    from skills.youtube_transcribe.subscribes.rss import entries_after
    entries = parse_rss(FIXTURE.read_text(encoding="utf-8"))
    cutoff = datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc)
    filtered = entries_after(entries, cutoff)
    assert len(filtered) == 1
    assert filtered[0].video_id == "vid111"
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_rss.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 4: Implement `subscribes/rss.py`**

`skills/youtube_transcribe/subscribes/rss.py`:

```python
"""YouTube channel RSS feed — fetch via urllib, parse via xml.etree.

YouTube exposes per-channel RSS at
https://www.youtube.com/feeds/videos.xml?channel_id=<UC...>
with ~15 most recent videos. Stable public format used for 10+ years.

Used in subscribes for fast discovery: ~10× faster than yt-dlp channel
scraping for most workloads. Falls back to yt-dlp when filters need
data not in RSS (duration, views, description).
"""
from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime


_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


@dataclass
class RssEntry:
    video_id: str
    url: str
    title: str
    channel_id: str
    published: datetime


def rss_url_for_channel(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def fetch_rss(channel_id: str, *, timeout: float = 10.0) -> list[RssEntry]:
    """Fetch + parse RSS for a channel. Empty list on any error."""
    try:
        body = _http_get(rss_url_for_channel(channel_id), timeout=timeout)
    except (urllib.error.URLError, OSError):
        return []
    return parse_rss(body)


def parse_rss(xml_text: str) -> list[RssEntry]:
    """Parse YouTube channel RSS XML. Empty list on malformed input."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[RssEntry] = []
    for entry in root.findall("atom:entry", _NS):
        vid_el = entry.find("yt:videoId", _NS)
        title_el = entry.find("atom:title", _NS)
        pub_el = entry.find("atom:published", _NS)
        ch_el = entry.find("yt:channelId", _NS)
        if vid_el is None or vid_el.text is None:
            continue
        out.append(RssEntry(
            video_id=vid_el.text,
            url=f"https://www.youtube.com/watch?v={vid_el.text}",
            title=(title_el.text if title_el is not None else "") or "",
            channel_id=(ch_el.text if ch_el is not None else "") or "",
            published=_parse_iso(pub_el.text if pub_el is not None else None),
        ))
    return out


def entries_after(entries: list[RssEntry], cutoff: datetime) -> list[RssEntry]:
    """Return entries whose `published` is strictly after `cutoff`."""
    return [e for e in entries if e.published > cutoff]


def _http_get(url: str, *, timeout: float = 10.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-transcribe/0.7"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_iso(s: str | None) -> datetime:
    """Parse YouTube ISO 8601 timestamp. Returns epoch on failure."""
    from datetime import timezone
    if not s:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    # Replace trailing Z with +00:00 for fromisoformat compat
    cleaned = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_rss.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/subscribes/rss.py \
        tests/test_subscribes_rss.py \
        tests/data/sample_rss.xml
git commit -m "feat(v0.7): subscribes.rss — fetch+parse YouTube channel RSS feeds"
```

---

### Task 12: subscribes/group.py — group filtering

**Files:**
- Create: `skills/youtube_transcribe/subscribes/group.py`
- Create: `tests/test_subscribes_group.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_group.py`:

```python
"""Tests for subscribes.group — channel grouping helpers."""
from skills.youtube_transcribe.subscribes.store import Channel
from skills.youtube_transcribe.subscribes.group import (
    filter_by_group,
    list_groups,
)


def _c(handle, group):
    return Channel(url=f"u/{handle}", handle=handle, channel_id=f"UC_{handle}",
                   group=group, added="x")


def test_filter_by_group_named():
    chans = [_c("@A", "ai"), _c("@B", "philosophy"), _c("@C", "ai")]
    out = filter_by_group(chans, "ai")
    assert [c.handle for c in out] == ["@A", "@C"]


def test_filter_by_group_none_returns_all():
    chans = [_c("@A", "ai"), _c("@B", None), _c("@C", "philosophy")]
    assert filter_by_group(chans, None) == chans


def test_filter_by_group_unknown_returns_empty():
    chans = [_c("@A", "ai")]
    assert filter_by_group(chans, "nope") == []


def test_filter_by_group_ungrouped_keyword():
    """Special keyword 'ungrouped' selects channels with group=None."""
    chans = [_c("@A", "ai"), _c("@B", None), _c("@C", None)]
    out = filter_by_group(chans, "ungrouped")
    assert [c.handle for c in out] == ["@B", "@C"]


def test_list_groups_returns_unique_sorted():
    chans = [_c("@A", "ai"), _c("@B", "philosophy"), _c("@C", "ai"),
             _c("@D", None), _c("@E", "art")]
    groups = list_groups(chans)
    assert groups == ["ai", "art", "philosophy"]
    # None should NOT appear in list (use 'ungrouped' filter explicitly).


def test_list_groups_empty():
    assert list_groups([]) == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_group.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `subscribes/group.py`**

`skills/youtube_transcribe/subscribes/group.py`:

```python
"""Channel grouping helpers — filter and listing for subscribes.

Groups are user-defined string tags on Channel.group. Special keyword
"ungrouped" selects channels with group=None. None as filter input
returns the full list (no-op).
"""
from __future__ import annotations

from skills.youtube_transcribe.subscribes.store import Channel


def filter_by_group(channels: list[Channel], group: str | None) -> list[Channel]:
    """Return channels matching the given group.

    - None → all channels (no filter)
    - "ungrouped" → channels with group=None
    - other → channels whose group equals the input
    """
    if group is None:
        return list(channels)
    if group == "ungrouped":
        return [c for c in channels if c.group is None]
    return [c for c in channels if c.group == group]


def list_groups(channels: list[Channel]) -> list[str]:
    """Return sorted unique non-None group names."""
    return sorted({c.group for c in channels if c.group is not None})
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_group.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/group.py \
        tests/test_subscribes_group.py
git commit -m "feat(v0.7): subscribes.group — group filtering + listing"
```

---

# Phase 5 — Refactor: extract `_run_batch_pipeline`

### Task 13: Extract `_run_batch_pipeline` from `batch_cmd`

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py`
- Create: `tests/test_batch_pipeline_refactor.py`

**This is the most invasive task.** Existing `batch_cmd` is ~400 lines of monolithic Click logic. We extract the post-parsing core into a reusable function so research/subscribes pipelines can call it directly.

- [ ] **Step 1: Write a focused regression test for the refactor**

`tests/test_batch_pipeline_refactor.py`:

```python
"""Refactor test: _run_batch_pipeline is callable directly with synthetic targets.

The full v0.6 test suite (614 tests) is the primary regression guard for
batch_cmd. This file adds the new contract: research/subscribes can call
_run_batch_pipeline directly without going through Click.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_run_batch_pipeline_importable():
    """Function exists and is importable."""
    from skills.youtube_transcribe.transcribe import _run_batch_pipeline
    assert callable(_run_batch_pipeline)


def test_run_batch_pipeline_signature():
    """Signature: (targets, cfg, options) -> Path."""
    import inspect
    from skills.youtube_transcribe.transcribe import _run_batch_pipeline
    sig = inspect.signature(_run_batch_pipeline)
    params = list(sig.parameters)
    assert "targets" in params
    assert "cfg" in params


def test_run_batch_pipeline_empty_targets_returns_none(tmp_path: Path):
    """Calling with zero targets returns None (nothing to do)."""
    from skills.youtube_transcribe.transcribe import _run_batch_pipeline
    from skills.youtube_transcribe.config import load_config, CONFIG_PATH

    cfg = load_config(CONFIG_PATH)
    result = _run_batch_pipeline(
        targets=[],
        cfg=cfg,
        opts={"output_dir": str(tmp_path), "batch_name": "empty_test"},
    )
    assert result is None


def test_run_batch_pipeline_returns_batch_dir(tmp_path: Path):
    """With successful targets, returns the Path to the batch folder."""
    from skills.youtube_transcribe.transcribe import _run_batch_pipeline
    from skills.youtube_transcribe.utils.resolver import ResolvedTarget
    from skills.youtube_transcribe.config import load_config, CONFIG_PATH
    from skills.youtube_transcribe.backends.base import TranscriptionResult

    cfg = load_config(CONFIG_PATH)
    fake_target = ResolvedTarget(
        url="https://www.youtube.com/watch?v=abc123",
        video_id="abc123",
        title="Test video",
        channel="Test channel",
        duration_sec=60,
        upload_date=None,
        source="single",
    )
    fake_result = TranscriptionResult(
        segments=[], language="en", backend="subtitles",
        duration_sec=60, text="hello", model_label=None,
        backend_impl=None, device=None, vram=None,
    )

    with patch(
        "skills.youtube_transcribe.transcribe.run_pipeline",
        return_value=fake_result,
    ):
        result = _run_batch_pipeline(
            targets=[fake_target],
            cfg=cfg,
            opts={"output_dir": str(tmp_path), "batch_name": "synthetic"},
        )

    assert result is not None
    assert result == tmp_path / "synthetic"
    assert (result / "manifest.json").exists()
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/test_batch_pipeline_refactor.py -v`
Expected: FAIL — `_run_batch_pipeline` not defined yet.

- [ ] **Step 3: Refactor `batch_cmd` — extract `_run_batch_pipeline`**

В `skills/youtube_transcribe/transcribe.py`:

1. **Найди** функцию `batch_cmd` (около строки 585). Тело начинается с `if not CONFIG_PATH.exists(): run_wizard()` и заканчивается финальным `console.print('  \\n  [dim]Next:[/dim] ...')` и опциональным `_run_then_analyze` блоком (v0.6).

2. **Идентифицируй split point**: после resolve targets, перед download/transcribe цикла. Конкретно — после строк где определяется `targets`, `output_root`, `name`, `batch_dir`. (Эти определения остаются в `batch_cmd`, после них вызывается `_run_batch_pipeline`.)

3. **Скопируй** всё тело от первой строки после `targets = ...` определения (т.е. от `output_root = Path(...)` до последнего вывода `console.print(f"\\n  [bold]{batch_dir}/[/bold]")`) в новую module-level функцию **ВЫШЕ** `@cli.command(name="batch")`:

```python
def _run_batch_pipeline(
    *,
    targets,           # list[ResolvedTarget]
    cfg,               # Config
    opts,              # dict (output_dir, batch_name, no_combined, fail_fast, etc.)
) -> Path | None:
    """Core batch pipeline — download → transcribe → write outputs.

    Extracted from batch_cmd in v0.7 to enable reuse from research/
    subscribes commands. Returns Path to the final batch folder, or
    None when there are no targets / nothing was written.

    All side-effects of v0.6 batch_cmd are preserved byte-for-byte
    (combined.md, manifest.json, errors.log, videos/, summary console
    output). The existing 614 tests continue to pass without modification.
    """
    if not targets:
        return None

    # [PASTE existing batch_cmd body from output_root = ... through final
    #  console.print of batch_dir summary, with these adjustments:
    #  1. Replace local opts.get(...) calls — opts is now a dict argument.
    #  2. Read backend_name / fast_path flags / etc. from cfg + opts.
    #  3. NO Click-level error-printing (raise instead), unless they were
    #     already raising via sys.exit — keep sys.exit as v0.6 had it.
    #  4. Return batch_dir at the end.]

    return batch_dir
```

4. **В `batch_cmd`** замени всё тело **после** определения `targets` (и до начала v0.6 `_run_then_analyze` блока) на:

```python
    # === v0.7: delegate to extracted pipeline ===
    batch_dir = _run_batch_pipeline(
        targets=targets,
        cfg=cfg,
        opts=opts,
    )

    # v0.6 post-batch analyze hook stays as-is
    if then_analyze and batch_dir is not None and batch_dir.exists():
        _run_then_analyze(
            batch_folder=batch_dir,
            prompt_inline=analyze_prompt,
            prompt_file=analyze_prompt_file,
            backend=analyze_backend,
        )
```

5. **`opts` parameter conventions** — `_run_batch_pipeline` accepts a flat dict with the same keys that `batch_cmd` currently reads via `opts.get(...)`. Required keys: `output_dir`, `batch_name`, `no_combined`, `fail_fast`. Optional: everything else `batch_cmd` passes through to `run_pipeline` (`whisper_model`, `gemini_model`, ...). Document with a short module-level note in `transcribe.py`.

6. **Subtle alignment with v0.7 callers:** research/subscribes pipelines (Tasks 16-17) will build their own `opts` dict from research/subscribes CLI flags. The dict keys must match what `_run_batch_pipeline` reads. Keep contract clear via inline comments inside the function — what keys are read.

- [ ] **Step 4: Run the refactor regression test**

Run: `uv run pytest tests/test_batch_pipeline_refactor.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the existing v0.6 batch + then-analyze tests**

Run: `uv run pytest tests/test_batch_*.py tests/test_cli_*.py -v --tb=short`
Expected: every test that passed in v0.6 still passes. Particularly `test_batch_then_analyze.py` (5 tests) — verifies the post-batch hook still works after refactor.

- [ ] **Step 6: Run the FULL suite**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: `1 failed, 618 passed, 2 skipped` (618 = 614 v0.6 + 4 new in this task) — same pre-existing webui failure.

If any v0.6 test breaks: STOP and report BLOCKED. Do NOT modify v0.6 tests to make them pass.

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py \
        tests/test_batch_pipeline_refactor.py
git commit -m "$(cat <<'EOF'
refactor(v0.7): extract _run_batch_pipeline from batch_cmd

Pulls the post-args-resolution core of batch_cmd (download → transcribe
→ write outputs) into a reusable module-level function. Enables
research and subscribes (v0.7) to drive the same pipeline directly
without going through Click parsing.

Behavior of `youtube-transcribe batch ...` preserved byte-for-byte —
all 614 v0.6 tests stay green (verified). Post-batch --then-analyze
hook continues to work unchanged.

The new function takes (targets, cfg, opts) and returns the final
batch folder Path (or None if nothing was written).
EOF
)"
```

---

# Phase 6 — History store + CLI

### Task 14: history/store.py — history.toml CRUD

**Files:**
- Create: `skills/youtube_transcribe/history/store.py`
- Create: `tests/test_history_store.py`

- [ ] **Step 1: Write failing tests**

`tests/test_history_store.py`:

```python
"""Tests for history.store — persistent log of research/subscribes runs."""
from datetime import datetime, timezone
from pathlib import Path

from skills.youtube_transcribe.history.store import (
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_history_store.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `history/store.py`**

`skills/youtube_transcribe/history/store.py`:

```python
"""Persistent log of research/subscribes runs as a TOML file.

Stored at ~/.youtube-transcribe/history.toml. Each entry has run id,
type (research/subscribes), timestamp, summary fields, output folder
path, status. Append-only; never modifies past entries.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path

import tomlkit


@dataclass
class RunEntry:
    id: str
    type: str                    # "research" | "subscribes"
    timestamp: str               # ISO 8601 UTC
    query: str | None            # research query (or None for subscribes)
    group: str | None            # subscribes group (or None for research)
    output: str                  # path to batch folder
    videos_found: int
    analyze_backend: str | None  # None if --no-analyze
    analyze_prompt_preview: str | None  # first ~200 chars of prompt
    status: str = "ok"           # "ok" | "failed" | "partial"
    languages: list[str] = field(default_factory=list)


def append_run(path: Path, entry: RunEntry) -> None:
    """Append a run to history.toml."""
    doc = (
        tomlkit.parse(path.read_text(encoding="utf-8"))
        if path.exists() else tomlkit.document()
    )
    arr = doc.get("runs")
    if arr is None:
        arr = tomlkit.aot()
        doc["runs"] = arr
    tbl = tomlkit.table()
    for k, v in asdict(entry).items():
        if v is not None:
            tbl[k] = v
    arr.append(tbl)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def list_runs(
    path: Path,
    *,
    limit: int | None = None,
    type_filter: str | None = None,
) -> list[RunEntry]:
    """Return runs newest-first. Filter by type if given."""
    if not path.exists():
        return []
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    raw = doc.get("runs") or []
    runs = [_from_dict(dict(r)) for r in raw]
    if type_filter:
        runs = [r for r in runs if r.type == type_filter]
    runs.sort(key=lambda r: r.timestamp, reverse=True)
    if limit is not None:
        runs = runs[:limit]
    return runs


def get_run(path: Path, run_id: str) -> RunEntry | None:
    for r in list_runs(path):
        if r.id == run_id:
            return r
    return None


def _from_dict(d: dict) -> RunEntry:
    return RunEntry(
        id=d.get("id", ""),
        type=d.get("type", "research"),
        timestamp=d.get("timestamp", ""),
        query=d.get("query"),
        group=d.get("group"),
        output=d.get("output", ""),
        videos_found=int(d.get("videos_found", 0)),
        analyze_backend=d.get("analyze_backend"),
        analyze_prompt_preview=d.get("analyze_prompt_preview"),
        status=d.get("status", "ok"),
        languages=list(d.get("languages") or []),
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_history_store.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/history/store.py \
        tests/test_history_store.py
git commit -m "feat(v0.7): history.store — append-only TOML log of runs"
```

---

### Task 15: history/cli.py + register in transcribe.py

**Files:**
- Create: `skills/youtube_transcribe/history/cli.py`
- Modify: `skills/youtube_transcribe/transcribe.py` (register history group + __all__)
- Create: `tests/test_history_cli.py`

- [ ] **Step 1: Write failing tests**

`tests/test_history_cli.py`:

```python
"""Tests for `youtube-transcribe history` CLI."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def _make_history(tmp_path: Path):
    """Create a synthetic history.toml with 3 runs."""
    from skills.youtube_transcribe.history.store import RunEntry, append_run
    p = tmp_path / "history.toml"
    for i, t in enumerate(("research", "subscribes", "research"), start=1):
        append_run(p, RunEntry(
            id=f"run_{i}", type=t,
            timestamp=f"2026-05-1{i}T14:00:00Z",
            query=f"q{i}" if t == "research" else None,
            group=None, output=f"/tmp/o{i}",
            videos_found=i * 2,
            analyze_backend="gemini",
            analyze_prompt_preview="prompt preview",
        ))
    return p


def test_history_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["history", "--help"])
    assert res.exit_code == 0
    assert "list" in res.output
    assert "show" in res.output


def test_history_list(tmp_path: Path):
    p = _make_history(tmp_path)
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "list"])
    assert res.exit_code == 0
    assert "run_1" in res.output or "q1" in res.output
    assert "run_2" in res.output or "subscribes" in res.output.lower()


def test_history_list_limit(tmp_path: Path):
    p = _make_history(tmp_path)
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "list", "--last", "1"])
    assert res.exit_code == 0
    # Only one entry shown
    occurrences = sum(res.output.count(f"run_{i}") for i in (1, 2, 3))
    assert occurrences == 1


def test_history_list_filter_by_type(tmp_path: Path):
    p = _make_history(tmp_path)
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "list", "--type", "research"])
    assert res.exit_code == 0
    # 2 research entries
    research_count = sum(
        res.output.count(f"run_{i}") for i in (1, 3)
    )
    assert research_count >= 2 or "q1" in res.output


def test_history_show_by_id(tmp_path: Path):
    p = _make_history(tmp_path)
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "show", "run_2"])
    assert res.exit_code == 0
    assert "run_2" in res.output
    assert "subscribes" in res.output.lower()
    assert "/tmp/o2" in res.output


def test_history_show_missing_id(tmp_path: Path):
    p = _make_history(tmp_path)
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "show", "missing"])
    assert res.exit_code != 0
    assert "not found" in res.output.lower()


def test_history_list_empty(tmp_path: Path):
    """No history.toml yet → friendly empty output."""
    p = tmp_path / "empty.toml"
    with patch(
        "skills.youtube_transcribe.history.cli.HISTORY_PATH",
        new=p,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["history", "list"])
    assert res.exit_code == 0
    assert "пуст" in res.output.lower() or "empty" in res.output.lower() or "no runs" in res.output.lower()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_history_cli.py -v`
Expected: FAIL — `history` command not registered.

- [ ] **Step 3: Implement `history/cli.py`**

`skills/youtube_transcribe/history/cli.py`:

```python
"""CLI for `youtube-transcribe history` — list and show past runs."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from skills.youtube_transcribe.history.store import (
    list_runs, get_run,
)

HISTORY_PATH = Path.home() / ".youtube-transcribe" / "history.toml"

_console = Console()


@click.group(name="history")
def history_group() -> None:
    """View past research / subscribes runs."""


@history_group.command(name="list")
@click.option("--last", "limit", type=int, default=10, show_default=True,
              help="How many runs to show (newest first).")
@click.option("--type", "type_filter",
              type=click.Choice(["research", "subscribes"]),
              default=None,
              help="Filter by run type.")
def list_cmd(limit: int, type_filter: str | None) -> None:
    """List recent runs."""
    runs = list_runs(HISTORY_PATH, limit=limit, type_filter=type_filter)
    if not runs:
        _console.print("[yellow]История пуста (no runs yet).[/yellow]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("When")
    table.add_column("Query / Group")
    table.add_column("Videos")
    table.add_column("Status")
    for r in runs:
        target = r.query or r.group or "—"
        table.add_row(
            r.id, r.type, r.timestamp,
            (target[:40] + "…") if target and len(target) > 40 else target,
            str(r.videos_found),
            r.status,
        )
    _console.print(table)


@history_group.command(name="show")
@click.argument("run_id")
def show_cmd(run_id: str) -> None:
    """Show full details for one run."""
    r = get_run(HISTORY_PATH, run_id)
    if r is None:
        _console.print(f"[red]Run not found: {run_id}[/red]")
        raise SystemExit(2)
    _console.print(f"[bold]ID:[/bold] {r.id}")
    _console.print(f"[bold]Type:[/bold] {r.type}")
    _console.print(f"[bold]Timestamp:[/bold] {r.timestamp}")
    if r.query:
        _console.print(f"[bold]Query:[/bold] {r.query}")
    if r.group:
        _console.print(f"[bold]Group:[/bold] {r.group}")
    if r.languages:
        _console.print(f"[bold]Languages:[/bold] {', '.join(r.languages)}")
    _console.print(f"[bold]Output:[/bold] {r.output}")
    _console.print(f"[bold]Videos found:[/bold] {r.videos_found}")
    _console.print(f"[bold]Status:[/bold] {r.status}")
    if r.analyze_backend:
        _console.print(f"[bold]Analyze backend:[/bold] {r.analyze_backend}")
    if r.analyze_prompt_preview:
        _console.print(f"[bold]Prompt:[/bold] {r.analyze_prompt_preview}")
```

- [ ] **Step 4: Register history group in `transcribe.py`**

В `skills/youtube_transcribe/transcribe.py`, после строки регистрации `triggers_cli` (или после `summarize_cmd` если triggers не зарегистрирован), добавь:

```python
# === v0.7: history command group ===
from skills.youtube_transcribe.history.cli import history_group
cli.add_command(history_group)
```

И добавь `"history_group"` в `__all__`:

```python
__all__ = [
    "cli", "transcribe_cmd", "batch_cmd", "config",
    "webui_cmd", "summarize_cmd", "analyze_cmd", "history_group",
]
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest tests/test_history_cli.py -v`
Expected: 7 passed.

- [ ] **Step 6: Full suite check**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: `1 failed, 631 passed, 2 skipped` (618 + 13 new).

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/history/cli.py \
        skills/youtube_transcribe/transcribe.py \
        tests/test_history_cli.py
git commit -m "feat(v0.7): history CLI — list/show recent research+subscribes runs"
```

---

# Phase 7 — Pipeline orchestration

### Task 16: research/pipeline.py — orchestrate research flow

**Files:**
- Create: `skills/youtube_transcribe/research/pipeline.py`
- Create: `tests/test_research_pipeline.py`

- [ ] **Step 1: Write failing tests**

`tests/test_research_pipeline.py`:

```python
"""Tests for research.pipeline — full orchestration with mocked dependencies."""
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _candidate(vid="v1", title="T", url=None, lang="en"):
    from skills.youtube_transcribe.research.source import SearchCandidate
    return SearchCandidate(
        video_id=vid, url=url or f"https://www.youtube.com/watch?v={vid}",
        title=title, channel="ch", duration_sec=300,
        upload_date=date(2026, 5, 11), source_language=lang,
    )


def test_pipeline_happy_path_invokes_components(tmp_path: Path):
    """The pipeline should: translate → search → date-filter → match →
    llm-screen → checkpoint → batch_pipeline → analyze. Each step mocked."""
    from skills.youtube_transcribe.research.pipeline import run_research

    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "Claude features"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate("v1"), _candidate("v2")],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch_dir",
    ) as mock_batch, patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ) as mock_analyze, patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,  # non-TTY → skip picker
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ):
        result = run_research(
            query="Claude features",
            queries_by_language=None,
            languages=["en"],
            days=30, since=None, until=None,
            limit=20,
            match=None, filter_text=None,
            in_subscribes=False, group=None,
            yes=True, no_analyze=False,
            prompt="summarize", prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b",
            ollama_host="http://localhost:11434",
            no_stdout=False,
            output_dir=str(tmp_path),
            batch_name="research_test",
            api_keys={"gemini": "fake", "anthropic": None, "openai": None},
            batch_opts={},
        )

    assert result == tmp_path / "batch_dir"
    mock_batch.assert_called_once()
    mock_analyze.assert_called_once()


def test_pipeline_no_analyze_skips_analyze(tmp_path: Path):
    from skills.youtube_transcribe.research.pipeline import run_research
    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate()],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=tmp_path,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ) as mock_analyze, patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=True,  # ← analyze off
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    mock_analyze.assert_not_called()


def test_pipeline_no_results_after_filter_returns_none(tmp_path: Path):
    """If filters reduce candidates to zero, pipeline reports and returns None."""
    from skills.youtube_transcribe.research.pipeline import run_research
    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[],  # nothing found
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ):
        result = run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    assert result is None


def test_pipeline_in_subscribes_uses_rss(tmp_path: Path):
    """--in-subscribes flips source from search → subscribes channels via RSS."""
    from skills.youtube_transcribe.research.pipeline import run_research
    from skills.youtube_transcribe.subscribes.rss import RssEntry
    from datetime import datetime, timezone

    fake_chan = MagicMock(handle="@A", channel_id="UC_a", group=None,
                          last_seen_video_id=None)
    fake_entries = [
        RssEntry(video_id="rss1", url="u", title="From RSS",
                 channel_id="UC_a",
                 published=datetime(2026, 5, 11, tzinfo=timezone.utc)),
    ]

    with patch(
        "skills.youtube_transcribe.research.pipeline.load_subscribes",
        return_value=[fake_chan],
    ), patch(
        "skills.youtube_transcribe.research.pipeline.fetch_rss",
        return_value=fake_entries,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
    ) as mock_search, patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=tmp_path,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None,
            in_subscribes=True, group=None,  # ← cross-pollination
            yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    # search_multi_language NOT called when in_subscribes=True
    mock_search.assert_not_called()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_research_pipeline.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `research/pipeline.py`**

`skills/youtube_transcribe/research/pipeline.py`:

```python
"""Research command orchestration — search → filter → transcribe → analyze.

This is the brain of `youtube-transcribe research`. It composes the
shared filter modules, the research source (multi-lang search), and
the v0.6 batch + analyze infrastructure.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from rich.console import Console

from skills.youtube_transcribe.research.translator import (
    build_queries_per_language,
)
from skills.youtube_transcribe.research.source import (
    SearchCandidate, search_multi_language,
)
from skills.youtube_transcribe.shared.date_filter import (
    parse_window, in_window, DateWindow,
)
from skills.youtube_transcribe.shared.match import match_titles
from skills.youtube_transcribe.shared.llm_screen import screen_candidates
from skills.youtube_transcribe.subscribes.store import load_subscribes
from skills.youtube_transcribe.subscribes.group import filter_by_group
from skills.youtube_transcribe.subscribes.rss import fetch_rss
from skills.youtube_transcribe.history.store import (
    RunEntry, append_run,
)
from skills.youtube_transcribe.transcribe import (
    _run_batch_pipeline, _run_then_analyze, _stdin_is_tty,
)
from skills.youtube_transcribe.utils.resolver import ResolvedTarget

_console = Console()


def run_research(
    *,
    query: str | None,
    queries_by_language: dict[str, str] | None,
    languages: list[str],
    days: int | None,
    since: date | None,
    until: date | None,
    limit: int,
    match: str | None,
    filter_text: str | None,
    in_subscribes: bool,
    group: str | None,
    yes: bool,
    no_analyze: bool,
    prompt: str | None,
    prompt_file: Path | None,
    analyze_backend: str,
    filter_backend: str,
    translate_backend: str,
    ollama_model: str,
    ollama_host: str,
    no_stdout: bool,
    output_dir: str,
    batch_name: str,
    api_keys: dict[str, str | None],
    batch_opts: dict,
) -> Path | None:
    """Run the full research pipeline. Returns batch folder Path or None."""

    # 1. Build per-language queries (or use explicit ones).
    queries: dict[str, str]
    if queries_by_language:
        queries = queries_by_language
        languages_used = list(queries.keys())
    else:
        queries = build_queries_per_language(
            query, languages=languages,
            backend=translate_backend,
            api_key=api_keys.get(_backend_to_key(translate_backend)),
            ollama_model=ollama_model, ollama_host=ollama_host,
        )
        languages_used = list(languages)

    # 2. Source: search OR cross-pollination from subscribes
    candidates: list = []
    if in_subscribes:
        candidates = _fetch_from_subscribes(group, limit)
    else:
        candidates = search_multi_language(queries, limit=limit)

    if not candidates:
        _console.print("[yellow]Кандидаты не найдены.[/yellow]")
        return None

    # 3. Date filter
    window = parse_window(
        days=days, since=since, until=until, now=date.today(),
    )
    if window is not None:
        candidates = _filter_by_window(candidates, window)
        if not candidates:
            _console.print(
                f"[yellow]После фильтра по дате осталось 0.[/yellow]"
            )
            return None

    # 4. substring --match
    if match:
        candidates = match_titles(candidates, match)
        if not candidates:
            _console.print(f"[yellow]После --match '{match}' осталось 0.[/yellow]")
            return None

    # 5. LLM --filter
    if filter_text:
        candidates = screen_candidates(
            candidates, filter_text,
            backend=filter_backend,
            api_key=api_keys.get(_backend_to_key(filter_backend)),
            ollama_model=ollama_model, ollama_host=ollama_host,
        )
        if not candidates:
            _console.print(f"[yellow]LLM filter оставил 0.[/yellow]")
            return None

    # 6. TTY checkpoint
    if not yes and _stdin_is_tty():
        candidates = _tty_checkpoint(candidates)
        if not candidates:
            _console.print("[yellow]Отменено.[/yellow]")
            return None

    # 7. Convert to ResolvedTarget and run batch_pipeline
    targets = [_to_resolved_target(c) for c in candidates]
    cfg = batch_opts.pop("cfg", None) or _load_default_cfg()
    opts = {
        "output_dir": output_dir,
        "batch_name": batch_name,
        "no_combined": batch_opts.get("no_combined", False),
        "fail_fast": batch_opts.get("fail_fast", False),
        **batch_opts,
    }
    batch_dir = _run_batch_pipeline(targets=targets, cfg=cfg, opts=opts)

    # 8. Analyze (unless --no-analyze)
    if not no_analyze and batch_dir is not None and batch_dir.exists():
        _run_then_analyze(
            batch_folder=batch_dir,
            prompt_inline=prompt,
            prompt_file=prompt_file,
            backend=analyze_backend,
        )

    # 9. History entry
    _append_history(
        type_="research", query=query, group=group,
        languages=languages_used,
        output=str(batch_dir) if batch_dir else "",
        videos_found=len(candidates),
        prompt=prompt or (prompt_file.read_text() if prompt_file else None),
        analyze_backend=None if no_analyze else analyze_backend,
    )

    return batch_dir


def _fetch_from_subscribes(group: str | None, limit: int) -> list:
    """Pull latest videos from subscribes channels (via RSS)."""
    sub_path = Path.home() / ".youtube-transcribe" / "subscribes.toml"
    channels = load_subscribes(sub_path)
    channels = filter_by_group(channels, group)
    out = []
    for ch in channels:
        if not ch.channel_id:
            continue
        entries = fetch_rss(ch.channel_id)
        for e in entries[:limit]:
            out.append(_rss_to_candidate(e, channel_title=ch.handle or ch.url))
    return out


def _rss_to_candidate(entry, *, channel_title: str):
    from skills.youtube_transcribe.research.source import SearchCandidate
    return SearchCandidate(
        video_id=entry.video_id, url=entry.url, title=entry.title,
        channel=channel_title, duration_sec=None,
        upload_date=entry.published.date() if entry.published else None,
        source_language="(subscribes)",
    )


def _filter_by_window(candidates: list, window: DateWindow) -> list:
    out = []
    for c in candidates:
        d = getattr(c, "upload_date", None)
        if d is None:
            continue  # without date, exclude (defensive)
        if in_window(d, window):
            out.append(c)
    return out


def _tty_checkpoint(candidates: list) -> list:
    """Show interactive checkbox picker; return chosen subset."""
    try:
        import questionary
    except ImportError:
        return list(candidates)
    choices = []
    for i, c in enumerate(candidates, start=1):
        title = (c.title or "—")[:60]
        date_str = c.upload_date.isoformat() if getattr(c, "upload_date", None) else "—"
        label = f"{date_str}  {title}  [{getattr(c, 'channel', '?')}]"
        choices.append(questionary.Choice(title=label, value=i - 1, checked=True))
    answer = questionary.checkbox(
        "Выбери видео для analyze (Space=toggle, Enter=ok):",
        choices=choices,
    ).ask()
    if answer is None:
        return []
    return [candidates[i] for i in answer]


def _to_resolved_target(c) -> ResolvedTarget:
    return ResolvedTarget(
        url=c.url, video_id=c.video_id, title=c.title,
        channel=getattr(c, "channel", None),
        duration_sec=getattr(c, "duration_sec", None),
        upload_date=getattr(c, "upload_date", None),
        source="search",
    )


def _backend_to_key(backend: str) -> str:
    return {"gemini": "gemini", "claude": "anthropic",
            "openai": "openai", "ollama": "ollama"}[backend]


def _load_default_cfg():
    from skills.youtube_transcribe.config import load_config, CONFIG_PATH
    return load_config(CONFIG_PATH)


def _append_history(
    *, type_: str, query, group, languages, output,
    videos_found, prompt, analyze_backend,
) -> None:
    from datetime import datetime, timezone
    import uuid
    p = Path.home() / ".youtube-transcribe" / "history.toml"
    run_id = f"{type_}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"
    entry = RunEntry(
        id=run_id, type=type_,
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=query, group=group,
        output=output, videos_found=videos_found,
        analyze_backend=analyze_backend,
        analyze_prompt_preview=((prompt or "")[:200]) if prompt else None,
        status="ok", languages=languages or [],
    )
    append_run(p, entry)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_research_pipeline.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/research/pipeline.py \
        tests/test_research_pipeline.py
git commit -m "feat(v0.7): research.pipeline — orchestrate search/filter/transcribe/analyze"
```

---

### Task 17: subscribes/pipeline.py — orchestrate subscribes update

**Files:**
- Create: `skills/youtube_transcribe/subscribes/pipeline.py`
- Create: `tests/test_subscribes_pipeline.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_pipeline.py`:

```python
"""Tests for subscribes.pipeline — orchestration of update flow."""
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _channel(handle="@A", channel_id="UC_a", last_id=None, last_pub=None,
             group=None):
    from skills.youtube_transcribe.subscribes.store import Channel
    return Channel(
        url=f"https://www.youtube.com/{handle}", handle=handle,
        channel_id=channel_id, group=group, added="2026-05-12",
        last_seen_video_id=last_id, last_seen_published=last_pub,
    )


def _rss(vid, pub_iso="2026-05-11T14:00:00+00:00"):
    from skills.youtube_transcribe.subscribes.rss import RssEntry
    return RssEntry(
        video_id=vid, url=f"https://www.youtube.com/watch?v={vid}",
        title=f"Title {vid}", channel_id="UC_a",
        published=datetime.fromisoformat(pub_iso),
    )


def test_first_run_requires_window(tmp_path: Path):
    """If a channel has no state and no override window — exit 2."""
    from skills.youtube_transcribe.subscribes.pipeline import (
        run_subscribes_update, SubscribesError,
    )
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[_channel(last_id=None)],
    ):
        with pytest.raises(SubscribesError, match="initial"):
            run_subscribes_update(
                subscribes_path=sub_path,
                group=None,
                days=None, since=None, until=None,  # NO override
                match=None, filter_text=None,
                no_rss=False, yes=True, no_analyze=True,
                prompt=None, prompt_file=None,
                analyze_backend="gemini", filter_backend="gemini",
                ollama_model="llama3.2:3b",
                ollama_host="http://localhost:11434",
                no_stdout=False, output_dir=str(tmp_path),
                api_keys={}, batch_opts={},
            )


def test_stateful_default_uses_last_seen(tmp_path: Path):
    """Channel with state: pipeline filters entries where published > last_seen."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    entries = [_rss("new1", "2026-05-12T00:00:00+00:00"),
               _rss("old1", "2026-05-09T00:00:00+00:00")]

    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=entries,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # State updated with newest video
    mock_state.assert_called_once()
    args, _ = mock_state.call_args
    # update_last_seen(path, channel_id, video_id, published)
    assert args[2] == "new1"


def test_override_days_skips_state_update(tmp_path: Path):
    """When --days override is used, state must NOT be updated."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    entries = [_rss("v1", "2026-05-12T00:00:00+00:00")]

    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=entries,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, days=7,   # ← override
            since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    mock_state.assert_not_called()


def test_group_filters_channels(tmp_path: Path):
    """--group ai-research should only fetch RSS for matching channels."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@AI1", channel_id="UC_ai1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="ai-research"),
        _channel(handle="@PH1", channel_id="UC_ph1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="philosophy"),
    ]
    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=[],
    ) as mock_rss, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group="ai-research",
            days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # Only UC_ai1 fetched
    mock_rss.assert_called_once_with("UC_ai1")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_pipeline.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement `subscribes/pipeline.py`**

`skills/youtube_transcribe/subscribes/pipeline.py`:

```python
"""Subscribes command orchestration — stateful incremental update.

Default: per-channel RSS-first discovery filtered by last_seen_published.
After successful run, updates last_seen_* in TOML.

Override (--days / --since / --until): applies global window, does NOT
update state — keeps incremental stream intact for normal runs.

First-run for channels without state: requires explicit --days or
--since (else SubscribesError).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console

from skills.youtube_transcribe.subscribes.store import (
    Channel, load_subscribes,
)
from skills.youtube_transcribe.subscribes.state import (
    update_last_seen, channels_without_state, needs_initial_run,
)
from skills.youtube_transcribe.subscribes.group import filter_by_group
from skills.youtube_transcribe.subscribes.rss import (
    fetch_rss, entries_after, RssEntry,
)
from skills.youtube_transcribe.shared.date_filter import (
    parse_window, in_window,
)
from skills.youtube_transcribe.shared.match import match_titles
from skills.youtube_transcribe.shared.llm_screen import screen_candidates
from skills.youtube_transcribe.history.store import RunEntry, append_run
from skills.youtube_transcribe.transcribe import (
    _run_batch_pipeline, _run_then_analyze, _stdin_is_tty,
)
from skills.youtube_transcribe.utils.resolver import ResolvedTarget
from skills.youtube_transcribe.research.source import SearchCandidate


class SubscribesError(Exception):
    """Pipeline-level error (e.g. missing initial state)."""


_console = Console()


def run_subscribes_update(
    *,
    subscribes_path: Path,
    group: str | None,
    days: int | None,
    since: date | None,
    until: date | None,
    match: str | None,
    filter_text: str | None,
    no_rss: bool,
    yes: bool,
    no_analyze: bool,
    prompt: str | None,
    prompt_file: Path | None,
    analyze_backend: str,
    filter_backend: str,
    ollama_model: str,
    ollama_host: str,
    no_stdout: bool,
    output_dir: str,
    api_keys: dict[str, str | None],
    batch_opts: dict,
) -> Path | None:
    """Run subscribes update. Returns Path to batch folder or None."""

    channels = load_subscribes(subscribes_path)
    channels = filter_by_group(channels, group)
    if not channels:
        _console.print("[yellow]Нет каналов (или группа пуста).[/yellow]")
        return None

    # Determine date window mode
    is_override = days is not None or since is not None or until is not None
    window = parse_window(days=days, since=since, until=until,
                         now=date.today()) if is_override else None

    # First-run validation
    if not is_override:
        missing = channels_without_state(channels)
        if missing:
            handles = ", ".join(c.handle or c.channel_id for c in missing)
            raise SubscribesError(
                f"--days or --since required for initial run of: {handles}"
            )

    # Per-channel: fetch + filter
    candidates: list[SearchCandidate] = []
    state_updates: list[tuple[str, str, str]] = []  # (chan_id, vid, pub_iso)

    for ch in channels:
        if not ch.channel_id:
            continue

        if no_rss:
            # yt-dlp fallback (not in MVP; for v0.7 hand-print warn + skip)
            _console.print(f"[yellow]--no-rss not yet implemented for "
                           f"{ch.handle}; skipping.[/yellow]")
            continue

        entries = fetch_rss(ch.channel_id)
        if not entries:
            continue

        # Filter by window (override) OR by last_seen (stateful default)
        if window is not None:
            entries = [
                e for e in entries
                if in_window(e.published, window)
            ]
        else:
            # Stateful: keep entries newer than last_seen_published
            cutoff = _parse_iso(ch.last_seen_published) if ch.last_seen_published else None
            if cutoff is not None:
                entries = entries_after(entries, cutoff)

        if not entries:
            continue

        # Convert to SearchCandidate for downstream uniformity
        for e in entries:
            candidates.append(SearchCandidate(
                video_id=e.video_id, url=e.url, title=e.title,
                channel=ch.handle or ch.url,
                duration_sec=None,
                upload_date=e.published.date(),
                source_language="(subscribes)",
            ))

        # Record state update for after successful run (default mode only)
        if not is_override:
            newest = max(entries, key=lambda e: e.published)
            state_updates.append((
                ch.channel_id, newest.video_id,
                newest.published.isoformat(),
            ))

    if not candidates:
        _console.print(
            "[yellow]Нет новых видео с момента последнего запуска.[/yellow]"
        )
        return None

    # Apply --match
    if match:
        candidates = match_titles(candidates, match)

    # Apply --filter (LLM)
    if filter_text and candidates:
        candidates = screen_candidates(
            candidates, filter_text,
            backend=filter_backend,
            api_key=api_keys.get(_backend_to_key(filter_backend)),
            ollama_model=ollama_model, ollama_host=ollama_host,
        )

    if not candidates:
        _console.print("[yellow]После фильтров ничего не осталось.[/yellow]")
        return None

    # TTY checkpoint
    if not yes and _stdin_is_tty():
        candidates = _tty_checkpoint(candidates)
        if not candidates:
            _console.print("[yellow]Отменено.[/yellow]")
            return None

    # Batch pipeline
    targets = [
        ResolvedTarget(
            url=c.url, video_id=c.video_id, title=c.title,
            channel=c.channel, duration_sec=c.duration_sec,
            upload_date=c.upload_date, source="channel",
        )
        for c in candidates
    ]
    batch_name = f"subscribes_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    from skills.youtube_transcribe.config import load_config, CONFIG_PATH
    cfg = load_config(CONFIG_PATH)
    opts = {
        "output_dir": output_dir,
        "batch_name": batch_name,
        "no_combined": batch_opts.get("no_combined", False),
        "fail_fast": batch_opts.get("fail_fast", False),
        **batch_opts,
    }
    batch_dir = _run_batch_pipeline(targets=targets, cfg=cfg, opts=opts)

    # Analyze
    if not no_analyze and batch_dir is not None and batch_dir.exists():
        _run_then_analyze(
            batch_folder=batch_dir,
            prompt_inline=prompt, prompt_file=prompt_file,
            backend=analyze_backend,
        )

    # State update (only if NOT override)
    if not is_override and batch_dir is not None:
        for chan_id, vid, pub in state_updates:
            update_last_seen(subscribes_path, chan_id, vid, pub)

    _append_history(
        group=group, output=str(batch_dir) if batch_dir else "",
        videos_found=len(candidates),
        prompt=prompt or (prompt_file.read_text() if prompt_file else None),
        analyze_backend=None if no_analyze else analyze_backend,
    )

    return batch_dir


def _tty_checkpoint(candidates: list) -> list:
    try:
        import questionary
    except ImportError:
        return list(candidates)
    choices = []
    for i, c in enumerate(candidates, start=1):
        title = (c.title or "—")[:60]
        date_str = c.upload_date.isoformat() if c.upload_date else "—"
        label = f"{date_str}  {title}  [{c.channel}]"
        choices.append(questionary.Choice(title=label, value=i - 1, checked=True))
    answer = questionary.checkbox(
        "Выбери видео для analyze (Space=toggle, Enter=ok):",
        choices=choices,
    ).ask()
    if answer is None:
        return []
    return [candidates[i] for i in answer]


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _backend_to_key(backend: str) -> str:
    return {"gemini": "gemini", "claude": "anthropic",
            "openai": "openai", "ollama": "ollama"}[backend]


def _append_history(*, group, output, videos_found, prompt, analyze_backend) -> None:
    import uuid
    p = Path.home() / ".youtube-transcribe" / "history.toml"
    run_id = (
        f"subscribes_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )
    entry = RunEntry(
        id=run_id, type="subscribes",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=None, group=group,
        output=output, videos_found=videos_found,
        analyze_backend=analyze_backend,
        analyze_prompt_preview=((prompt or "")[:200]) if prompt else None,
        status="ok",
    )
    append_run(p, entry)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_pipeline.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/pipeline.py \
        tests/test_subscribes_pipeline.py
git commit -m "feat(v0.7): subscribes.pipeline — stateful incremental update orchestration"
```

---

# Phase 8 — CLI commands

### Task 18: research_cmd in transcribe.py

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py` (add research_cmd)
- Create: `tests/test_cli_research.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli_research.py`:

```python
"""Tests for `youtube-transcribe research` CLI."""
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def test_research_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["research", "--help"])
    assert res.exit_code == 0
    for opt in ["--prompt", "--prompt-file", "--days", "--since", "--until",
                "--languages", "--limit", "--match", "--filter",
                "--in-subscribes", "--group", "--yes", "--no-analyze",
                "--analyze-backend", "--filter-backend",
                "--translate-backend", "--no-stdout"]:
        assert opt in res.output


def test_research_requires_query_or_query_file():
    """No query and no --query-* → exit 2."""
    runner = CliRunner()
    res = runner.invoke(cli, [
        "research",  # no query, no --query-*
        "--prompt", "test", "--analyze-backend", "ollama",
    ], catch_exceptions=False)
    assert res.exit_code == 2


def test_research_calls_pipeline(tmp_path: Path):
    """research_cmd должен делегировать в run_research с правильными опциями."""
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=tmp_path / "fake_batch",
    ) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "research", "Claude features",
            "--days", "7",
            "--languages", "en",
            "--limit", "5",
            "--no-analyze",
            "--yes",
            "--backend", "subtitles",
            "--analyze-backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 0
    mock_pipe.assert_called_once()
    kwargs = mock_pipe.call_args.kwargs
    assert kwargs["query"] == "Claude features"
    assert kwargs["days"] == 7
    assert kwargs["languages"] == ["en"]
    assert kwargs["limit"] == 5
    assert kwargs["no_analyze"] is True
    assert kwargs["yes"] is True


def test_research_query_file(tmp_path: Path):
    """--prompt-file reads file content."""
    pf = tmp_path / "p.md"
    pf.write_text("PROMPT FROM FILE", encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=tmp_path / "fake",
    ) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "research", "topic",
            "--prompt-file", str(pf),
            "--backend", "subtitles",
            "--yes",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    kwargs = mock_pipe.call_args.kwargs
    # query stays "topic"; prompt_file path passed through
    assert kwargs["prompt_file"] is not None


def test_research_mutex_prompt_and_prompt_file_when_analyze(tmp_path: Path):
    """analyze on (default) requires exactly one of --prompt / --prompt-file."""
    pf = tmp_path / "p.md"
    pf.write_text("x", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(cli, [
        "research", "topic",
        "--prompt", "x", "--prompt-file", str(pf),
        "--backend", "subtitles",
    ], catch_exceptions=False)
    assert res.exit_code == 2


def test_research_languages_default_ru_en():
    """When --languages absent — default 'ru,en'."""
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=None,
    ) as mock_pipe:
        runner = CliRunner()
        runner.invoke(cli, [
            "research", "topic", "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    kwargs = mock_pipe.call_args.kwargs
    assert kwargs["languages"] == ["ru", "en"]


def test_research_days_default_30():
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=None,
    ) as mock_pipe:
        runner = CliRunner()
        runner.invoke(cli, [
            "research", "topic", "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert mock_pipe.call_args.kwargs["days"] == 30


def test_research_limit_default_20():
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=None,
    ) as mock_pipe:
        runner = CliRunner()
        runner.invoke(cli, [
            "research", "topic", "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert mock_pipe.call_args.kwargs["limit"] == 20
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_research.py -v`
Expected: FAIL — `research` command not registered.

- [ ] **Step 3: Add `research_cmd` to `transcribe.py`**

После `analyze_cmd` (но перед регистрацией `history_group`) в `transcribe.py`:

```python
@cli.command(name="research")
@click.argument("query", required=False)
@click.option("--prompt", "prompt_inline", default=None,
              help="Analyze prompt (required unless --no-analyze).")
@click.option("--prompt-file", "prompt_file", default=None,
              type=click.Path(exists=True, path_type=Path),
              help="Read analyze prompt from file. Mutex with --prompt.")
@click.option("--languages", "languages_csv", default="ru,en",
              show_default=True,
              help="Comma-separated language codes for search. "
                   "Translates query into each via LLM.")
@click.option("--translate-backend", "translate_backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default=None,
              help="LLM for query translation. Defaults to --analyze-backend.")
@click.option("--days", "days_opt", type=int, default=30, show_default=True,
              help="Window: last N days (mutex with --since/--until).")
@click.option("--since", "since_opt", default=None,
              help="Window start YYYY-MM-DD.")
@click.option("--until", "until_opt", default=None,
              help="Window end YYYY-MM-DD.")
@click.option("--limit", "limit_opt", type=int, default=20, show_default=True,
              help="Videos to take from top YouTube results per language.")
@click.option("--match", "match_opt", default=None,
              help="Case-insensitive substring filter on title.")
@click.option("--filter", "filter_opt", default=None,
              help="LLM pre-screening prompt.")
@click.option("--filter-backend", "filter_backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini", show_default=True)
@click.option("--in-subscribes", is_flag=True, default=False,
              help="Source = subscribes channels (RSS) instead of YouTube search.")
@click.option("--group", "group_opt", default=None,
              help="With --in-subscribes — limit to channels in this group.")
@click.option("--yes", is_flag=True, default=False,
              help="Skip TTY checkpoint.")
@click.option("--no-analyze", is_flag=True, default=False,
              help="Skip final analyze step (just transcribe).")
@click.option("--analyze-backend", "analyze_backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini", show_default=True,
              help="LLM for analyze step.")
@click.option("--ollama-model", "ollama_model_opt", default=None)
@click.option("--ollama-host", "ollama_host_opt", default=None)
@click.option("--no-stdout", "no_stdout_opt", is_flag=True, default=False)
@click.option("--output-dir", "output_dir_opt", default=None,
              help="Override config output_dir.")
@click.option("--batch-name", "batch_name_opt", default=None,
              help="Override auto batch name.")
# Pass-through batch flags:
@click.option("--backend", "backend_opt",
              type=click.Choice(BACKEND_CHOICES), default=None)
@click.option("--whisper-model",
              type=click.Choice(["turbo", "large", "medium", "small", "distil"]),
              default=None)
@click.option("--language", "language_opt", default=None)
@click.option("--timestamps/--no-timestamps", default=None)
@click.option("--srt/--no-srt", default=None)
@click.option("--no-shorts", "no_shorts_opt", is_flag=True, default=False)
@click.option("--min-duration", "min_duration_opt", type=int, default=None)
@click.option("--max-duration", "max_duration_opt", type=int, default=None)
@click.option("--workers", "workers_opt", type=int, default=1, show_default=True)
def research_cmd(
    query: str | None,
    prompt_inline: str | None,
    prompt_file: Path | None,
    languages_csv: str,
    translate_backend_opt: str | None,
    days_opt: int,
    since_opt: str | None,
    until_opt: str | None,
    limit_opt: int,
    match_opt: str | None,
    filter_opt: str | None,
    filter_backend_opt: str,
    in_subscribes: bool,
    group_opt: str | None,
    yes: bool,
    no_analyze: bool,
    analyze_backend_opt: str,
    ollama_model_opt: str | None,
    ollama_host_opt: str | None,
    no_stdout_opt: bool,
    output_dir_opt: str | None,
    batch_name_opt: str | None,
    **batch_passthrough,
) -> None:
    """Research a topic — search YouTube + transcribe + analyze."""
    from datetime import date as _date
    from skills.youtube_transcribe.research.pipeline import run_research

    # 1. Validation: must have query (or --in-subscribes which needs no query)
    if not query and not in_subscribes:
        console.print(
            "[red]Нужен QUERY (или --in-subscribes).[/red]"
        )
        sys.exit(2)

    # 2. Prompt validation (only if analyze enabled)
    if not no_analyze:
        if bool(prompt_inline) == bool(prompt_file):
            console.print(
                "[red]При analyze on — нужен ровно один из[/red] "
                "--prompt / --prompt-file."
            )
            sys.exit(2)

    # 3. Parse dates
    since_d = _date.fromisoformat(since_opt) if since_opt else None
    until_d = _date.fromisoformat(until_opt) if until_opt else None
    days_arg = days_opt if (since_d is None and until_d is None) else None

    # 4. Languages
    languages = [s.strip() for s in languages_csv.split(",") if s.strip()]

    # 5. Translate backend default
    translate_backend = translate_backend_opt or analyze_backend_opt

    # 6. Resolve API keys
    api_keys = {
        "gemini": get_api_key("gemini"),
        "anthropic": get_api_key("anthropic"),
        "openai": get_api_key("openai"),
        "ollama": None,
    }

    # 7. Build pass-through batch_opts dict for the transcription core
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    output_dir = (
        output_dir_opt or (cfg.output_dir if cfg else "./transcripts")
    )
    batch_name = batch_name_opt or _research_batch_name(query)
    batch_opts = {k: v for k, v in batch_passthrough.items() if v is not None}
    batch_opts["no_combined"] = False
    batch_opts["fail_fast"] = False

    # 8. Delegate to pipeline
    try:
        run_research(
            query=query,
            queries_by_language=None,
            languages=languages,
            days=days_arg, since=since_d, until=until_d,
            limit=limit_opt,
            match=match_opt, filter_text=filter_opt,
            in_subscribes=in_subscribes, group=group_opt,
            yes=yes, no_analyze=no_analyze,
            prompt=prompt_inline, prompt_file=prompt_file,
            analyze_backend=analyze_backend_opt,
            filter_backend=filter_backend_opt,
            translate_backend=translate_backend,
            ollama_model=ollama_model_opt or "llama3.2:3b",
            ollama_host=ollama_host_opt or "http://localhost:11434",
            no_stdout=no_stdout_opt,
            output_dir=output_dir,
            batch_name=batch_name,
            api_keys=api_keys,
            batch_opts=batch_opts,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(2)


def _research_batch_name(query: str | None) -> str:
    """Generate batch name from query: research_<ts>_<slug>."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    if not query:
        return f"research_{ts}"
    # Simple slug: lowercase, alnum + hyphens, max 30 chars
    slug = "".join(c if c.isalnum() else "-" for c in query.lower())
    slug = "-".join(p for p in slug.split("-") if p)[:30].rstrip("-")
    return f"research_{ts}_{slug or 'topic'}"
```

И в `__all__` добавить `"research_cmd"`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_research.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py tests/test_cli_research.py
git commit -m "feat(v0.7): research CLI — multi-lang search to transcribe+analyze pipeline"
```

---

### Task 19: subscribes/cli.py — add/remove/list/edit sub-commands

**Files:**
- Create: `skills/youtube_transcribe/subscribes/cli.py`
- Modify: `skills/youtube_transcribe/transcribe.py` (register subscribes group)
- Create: `tests/test_cli_subscribes.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli_subscribes.py`:

```python
"""Tests for `youtube-transcribe subscribes` CLI: add/remove/list/edit."""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def _resolved(url, channel_id="UC_abc"):
    from skills.youtube_transcribe.subscribes.channel_resolver import (
        ResolvedChannel,
    )
    return ResolvedChannel(
        url=url.rstrip("/"), handle="@A", channel_id=channel_id, title="A",
    )


def test_subscribes_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["subscribes", "--help"])
    assert res.exit_code == 0
    for sub in ["add", "remove", "list", "edit", "update"]:
        assert sub in res.output


def test_add_persists_channel(tmp_path: Path):
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ), patch(
        "skills.youtube_transcribe.subscribes.cli.resolve_channel",
        return_value=_resolved("https://www.youtube.com/@A"),
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "add", "https://www.youtube.com/@A",
            "--group", "ai-research",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    text = sub_path.read_text()
    assert "@A" in text
    assert "ai-research" in text


def test_add_resolution_failure_exits_3(tmp_path: Path):
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ), patch(
        "skills.youtube_transcribe.subscribes.cli.resolve_channel",
        side_effect=ValueError("not a channel"),
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "add", "https://www.youtube.com/notchannel",
        ], catch_exceptions=False)
    assert res.exit_code == 3


def test_list_shows_channels(tmp_path: Path):
    from skills.youtube_transcribe.subscribes.store import (
        Channel, add_channel,
    )
    sub_path = tmp_path / "subscribes.toml"
    add_channel(sub_path, Channel(
        url="u1", handle="@A", channel_id="UC_a", group="ai",
        added="2026-05-12",
    ))
    add_channel(sub_path, Channel(
        url="u2", handle="@B", channel_id="UC_b", group=None,
        added="2026-05-12",
    ))
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["subscribes", "list"])
    assert res.exit_code == 0
    assert "@A" in res.output
    assert "@B" in res.output


def test_list_filter_by_group(tmp_path: Path):
    from skills.youtube_transcribe.subscribes.store import (
        Channel, add_channel,
    )
    sub_path = tmp_path / "subscribes.toml"
    add_channel(sub_path, Channel(
        url="u1", handle="@A", channel_id="UC_a", group="ai", added="x",
    ))
    add_channel(sub_path, Channel(
        url="u2", handle="@B", channel_id="UC_b", group="philosophy", added="x",
    ))
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["subscribes", "list", "--group", "ai"])
    assert res.exit_code == 0
    assert "@A" in res.output
    assert "@B" not in res.output


def test_remove_existing(tmp_path: Path):
    from skills.youtube_transcribe.subscribes.store import (
        Channel, add_channel,
    )
    sub_path = tmp_path / "subscribes.toml"
    add_channel(sub_path, Channel(
        url="u", handle="@A", channel_id="UC_a", group=None, added="x",
    ))
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["subscribes", "remove", "@A"])
    assert res.exit_code == 0
    assert "@A" not in sub_path.read_text()


def test_remove_missing_exits_3(tmp_path: Path):
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["subscribes", "remove", "@MISSING"])
    assert res.exit_code == 3


def test_edit_uses_env_editor(tmp_path: Path, monkeypatch):
    """`subscribes edit` invokes $EDITOR on the TOML file."""
    sub_path = tmp_path / "subscribes.toml"
    sub_path.write_text("# empty\n", encoding="utf-8")
    monkeypatch.setenv("EDITOR", "true")  # Unix /usr/bin/true exits 0
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, ["subscribes", "edit"])
    assert res.exit_code == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_subscribes.py -v`
Expected: FAIL — `subscribes` command not registered.

- [ ] **Step 3: Implement `subscribes/cli.py`**

`skills/youtube_transcribe/subscribes/cli.py`:

```python
"""CLI for `youtube-transcribe subscribes` group:
add / remove / list / edit / update.

The update sub-command is registered separately in Task 20.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from skills.youtube_transcribe.subscribes.store import (
    Channel, add_channel, load_subscribes, remove_channel,
)
from skills.youtube_transcribe.subscribes.group import filter_by_group
from skills.youtube_transcribe.subscribes.channel_resolver import (
    resolve_channel,
)

SUBSCRIBES_PATH = Path.home() / ".youtube-transcribe" / "subscribes.toml"

_console = Console()


@click.group(name="subscribes")
def subscribes_group() -> None:
    """Manage and run subscribes (channel list + incremental update)."""


@subscribes_group.command(name="add")
@click.argument("channel_url")
@click.option("--group", default=None,
              help="Optional group tag (e.g. 'ai-research').")
def add_cmd(channel_url: str, group: str | None) -> None:
    """Add a channel by URL or @handle."""
    try:
        resolved = resolve_channel(channel_url)
    except ValueError as e:
        _console.print(f"[red]Не удалось распознать канал:[/red] {e}")
        sys.exit(3)

    channel = Channel(
        url=resolved.url,
        handle=resolved.handle,
        channel_id=resolved.channel_id,
        group=group,
        added=date.today().isoformat(),
    )
    add_channel(SUBSCRIBES_PATH, channel)
    _console.print(
        f"[green]✓[/green] Добавлен {resolved.handle or resolved.url} "
        f"(channel_id={resolved.channel_id}, group={group or '—'})"
    )


@subscribes_group.command(name="remove")
@click.argument("identifier")
def remove_cmd(identifier: str) -> None:
    """Remove a channel by handle, URL, or channel_id."""
    if not remove_channel(SUBSCRIBES_PATH, identifier):
        _console.print(f"[red]Канал не найден: {identifier}[/red]")
        sys.exit(3)
    _console.print(f"[green]✓[/green] Удалён {identifier}")


@subscribes_group.command(name="list")
@click.option("--group", default=None, help="Filter by group.")
def list_cmd(group: str | None) -> None:
    """List subscribed channels."""
    channels = load_subscribes(SUBSCRIBES_PATH)
    channels = filter_by_group(channels, group)
    if not channels:
        _console.print("[yellow]Нет каналов.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Handle")
    table.add_column("Group")
    table.add_column("Channel ID")
    table.add_column("Last seen")
    for c in channels:
        table.add_row(
            c.handle or "—",
            c.group or "—",
            c.channel_id or "—",
            c.last_seen_published or "—",
        )
    _console.print(table)


@subscribes_group.command(name="edit")
def edit_cmd() -> None:
    """Open subscribes.toml in $EDITOR (or vi/notepad fallback)."""
    SUBSCRIBES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SUBSCRIBES_PATH.exists():
        SUBSCRIBES_PATH.write_text("# subscribes — youtube-transcribe v0.7\n",
                                   encoding="utf-8")

    editor = os.environ.get("EDITOR") or _default_editor()
    try:
        subprocess.run([editor, str(SUBSCRIBES_PATH)], check=True)
    except FileNotFoundError:
        _console.print(
            f"[red]Editor not found: {editor}. Set $EDITOR.[/red]"
        )
        sys.exit(4)
    except subprocess.CalledProcessError as e:
        # Editor exit non-zero — not fatal (user may have just quit)
        if e.returncode != 0:
            _console.print(f"[yellow]Editor exited with {e.returncode}[/yellow]")


def _default_editor() -> str:
    """Cross-OS fallback editor."""
    if sys.platform == "win32":
        return "notepad"
    return "vi"
```

- [ ] **Step 4: Register subscribes group в transcribe.py**

В `transcribe.py` после `history_group` registration:

```python
# === v0.7: subscribes command group ===
from skills.youtube_transcribe.subscribes.cli import subscribes_group
cli.add_command(subscribes_group)
```

И в `__all__` добавить `"subscribes_group"`.

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_subscribes.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/subscribes/cli.py \
        skills/youtube_transcribe/transcribe.py \
        tests/test_cli_subscribes.py
git commit -m "feat(v0.7): subscribes CLI — add/remove/list/edit sub-commands"
```

---

### Task 20: subscribes update sub-command

**Files:**
- Modify: `skills/youtube_transcribe/subscribes/cli.py` (add update command)
- Modify: `tests/test_cli_subscribes.py` (add update tests)

- [ ] **Step 1: Add failing tests**

В конец `tests/test_cli_subscribes.py` добавить:

```python
def test_update_delegates_to_pipeline(tmp_path: Path):
    sub_path = tmp_path / "subscribes.toml"
    sub_path.write_text("# empty\n", encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.run_subscribes_update",
        return_value=tmp_path / "fake",
    ) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "update",
            "--days", "7",
            "--no-analyze",
            "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    kwargs = mock_pipe.call_args.kwargs
    assert kwargs["days"] == 7
    assert kwargs["no_analyze"] is True
    assert kwargs["yes"] is True


def test_update_subscribes_error_exits_2(tmp_path: Path):
    """SubscribesError from pipeline → exit 2 with friendly message."""
    from skills.youtube_transcribe.subscribes.pipeline import SubscribesError
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.run_subscribes_update",
        side_effect=SubscribesError("--days required for: @X"),
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "update", "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert res.exit_code == 2
    assert "--days required" in res.output or "@X" in res.output


def test_update_analyze_requires_prompt(tmp_path: Path):
    """analyze ON (default) requires --prompt or --prompt-file."""
    sub_path = tmp_path / "subscribes.toml"
    sub_path.write_text("# empty\n", encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.subscribes.cli.SUBSCRIBES_PATH",
        new=sub_path,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "update",
            "--days", "7",
            "--backend", "subtitles",
            # no --prompt and no --no-analyze
        ], catch_exceptions=False)
    assert res.exit_code == 2
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_subscribes.py -v`
Expected: 3 new tests FAIL.

- [ ] **Step 3: Add `update_cmd` to `subscribes/cli.py`**

В `subscribes/cli.py`, после `edit_cmd`, добавить:

```python
@subscribes_group.command(name="update")
@click.option("--group", default=None)
@click.option("--days", type=int, default=None,
              help="Override stateful window: last N days (state NOT updated).")
@click.option("--since", default=None,
              help="Override window start YYYY-MM-DD.")
@click.option("--until", default=None,
              help="Override window end YYYY-MM-DD.")
@click.option("--match", default=None, help="Substring filter on title.")
@click.option("--filter", "filter_text", default=None,
              help="LLM pre-screening.")
@click.option("--no-rss", is_flag=True, default=False,
              help="Force yt-dlp instead of RSS.")
@click.option("--yes", is_flag=True, default=False)
@click.option("--no-analyze", is_flag=True, default=False)
@click.option("--prompt", "prompt_inline", default=None)
@click.option("--prompt-file", "prompt_file", default=None,
              type=click.Path(exists=True, path_type=Path))
@click.option("--analyze-backend", "analyze_backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini")
@click.option("--filter-backend", "filter_backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini")
@click.option("--ollama-model", "ollama_model_opt", default=None)
@click.option("--ollama-host", "ollama_host_opt", default=None)
@click.option("--no-stdout", "no_stdout_opt", is_flag=True, default=False)
@click.option("--output-dir", "output_dir_opt", default=None)
@click.option("--backend", "backend_opt",
              type=click.Choice([
                  "subtitles", "whisper-local", "gemini", "groq",
                  "openai", "deepgram", "assemblyai", "custom", "smart",
              ]), default=None)
@click.option("--whisper-model",
              type=click.Choice(["turbo", "large", "medium", "small", "distil"]),
              default=None)
@click.option("--language", "language_opt", default=None)
@click.option("--workers", "workers_opt", type=int, default=1)
def update_cmd(
    group: str | None,
    days: int | None,
    since: str | None,
    until: str | None,
    match: str | None,
    filter_text: str | None,
    no_rss: bool,
    yes: bool,
    no_analyze: bool,
    prompt_inline: str | None,
    prompt_file: Path | None,
    analyze_backend_opt: str,
    filter_backend_opt: str,
    ollama_model_opt: str | None,
    ollama_host_opt: str | None,
    no_stdout_opt: bool,
    output_dir_opt: str | None,
    **batch_passthrough,
) -> None:
    """Run subscribes update — fetch latest, filter, transcribe, analyze."""
    from datetime import date as _date

    if not no_analyze:
        if bool(prompt_inline) == bool(prompt_file):
            _console.print(
                "[red]При analyze on — нужен ровно один из[/red] "
                "--prompt / --prompt-file."
            )
            sys.exit(2)

    # Parse dates
    since_d = _date.fromisoformat(since) if since else None
    until_d = _date.fromisoformat(until) if until else None

    # API keys
    from skills.youtube_transcribe.config import get_api_key, load_config, CONFIG_PATH
    api_keys = {
        "gemini": get_api_key("gemini"),
        "anthropic": get_api_key("anthropic"),
        "openai": get_api_key("openai"),
        "ollama": None,
    }

    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    output_dir = output_dir_opt or (cfg.output_dir if cfg else "./transcripts")
    batch_opts = {k: v for k, v in batch_passthrough.items() if v is not None}

    from skills.youtube_transcribe.subscribes.pipeline import (
        run_subscribes_update, SubscribesError,
    )
    try:
        run_subscribes_update(
            subscribes_path=SUBSCRIBES_PATH,
            group=group,
            days=days, since=since_d, until=until_d,
            match=match, filter_text=filter_text,
            no_rss=no_rss, yes=yes, no_analyze=no_analyze,
            prompt=prompt_inline, prompt_file=prompt_file,
            analyze_backend=analyze_backend_opt,
            filter_backend=filter_backend_opt,
            ollama_model=ollama_model_opt or "llama3.2:3b",
            ollama_host=ollama_host_opt or "http://localhost:11434",
            no_stdout=no_stdout_opt,
            output_dir=output_dir,
            api_keys=api_keys,
            batch_opts=batch_opts,
        )
    except SubscribesError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_subscribes.py -v`
Expected: 11 passed (8 from T19 + 3 new).

- [ ] **Step 5: Run full suite check**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: `1 failed, ~660 passed, 2 skipped`.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/subscribes/cli.py \
        tests/test_cli_subscribes.py
git commit -m "feat(v0.7): subscribes update — incremental run via pipeline"
```

---

### Task 21: Wire research and subscribes into transcribe.py __all__

This task is a small consolidation — ensure `__all__` in `transcribe.py` lists all v0.7 additions, and add SKILL.md entries for Claude awareness. SKILL.md update is Task 31; here just the `__all__`.

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py` (__all__ only)

- [ ] **Step 1: Verify current `__all__`**

Run: `grep -n "__all__" skills/youtube_transcribe/transcribe.py`

Should list `analyze_cmd`, `history_group`, `subscribes_group` already. Add `research_cmd`:

```python
__all__ = [
    "cli", "transcribe_cmd", "batch_cmd", "config",
    "webui_cmd", "summarize_cmd", "analyze_cmd",
    "history_group", "subscribes_group", "research_cmd",
]
```

- [ ] **Step 2: Smoke test**

Run: `uv run python -c "from skills.youtube_transcribe.transcribe import research_cmd, subscribes_group, history_group; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: same green as Task 20.

- [ ] **Step 4: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py
git commit -m "chore(v0.7): export research_cmd / subscribes_group / history_group in __all__"
```

---

### Task 22: --in-subscribes integration test

**Files:**
- Modify: `tests/test_cli_research.py` (add cross-pollination tests)

- [ ] **Step 1: Add tests**

В конец `tests/test_cli_research.py` добавить:

```python
def test_research_in_subscribes_calls_pipeline_with_flag(tmp_path: Path):
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=None,
    ) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "research", "Claude features",
            "--in-subscribes",
            "--group", "ai-research",
            "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    kwargs = mock_pipe.call_args.kwargs
    assert kwargs["in_subscribes"] is True
    assert kwargs["group"] == "ai-research"


def test_research_in_subscribes_without_query_works(tmp_path: Path):
    """--in-subscribes can run without a positional query (just filter
    latest from subscribes)."""
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=None,
    ) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "research",  # no positional
            "--in-subscribes",
            "--no-analyze", "--yes",
            "--backend", "subtitles",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    kwargs = mock_pipe.call_args.kwargs
    assert kwargs["query"] is None
    assert kwargs["in_subscribes"] is True
```

- [ ] **Step 2: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_research.py::test_research_in_subscribes_calls_pipeline_with_flag tests/test_cli_research.py::test_research_in_subscribes_without_query_works -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_research.py
git commit -m "test(v0.7): cover research --in-subscribes cross-pollination flag"
```

---

# Phase 9 — Schedule helpers (cross-OS)

### Task 23: schedule.py — platform detection + interval parsing

**Files:**
- Create: `skills/youtube_transcribe/subscribes/schedule.py`
- Create: `tests/test_subscribes_schedule_core.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_schedule_core.py`:

```python
"""Tests for subscribes.schedule core — platform detect, interval parse."""
import pytest

from skills.youtube_transcribe.subscribes.schedule import (
    detect_platform,
    parse_interval,
)


def test_detect_platform_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert detect_platform() == "launchd"


def test_detect_platform_linux(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert detect_platform() in ("systemd", "cron")


def test_detect_platform_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert detect_platform() == "taskscheduler"


def test_parse_interval_minutes():
    assert parse_interval("15m") == 900
    assert parse_interval("30m") == 1800


def test_parse_interval_hours():
    assert parse_interval("1h") == 3600
    assert parse_interval("6h") == 21600


def test_parse_interval_days():
    assert parse_interval("1d") == 86400
    assert parse_interval("7d") == 7 * 86400


def test_parse_interval_invalid():
    with pytest.raises(ValueError, match="interval"):
        parse_interval("bogus")
    with pytest.raises(ValueError, match="interval"):
        parse_interval("5x")


def test_parse_interval_zero_raises():
    with pytest.raises(ValueError, match="positive"):
        parse_interval("0h")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_schedule_core.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement core functions**

`skills/youtube_transcribe/subscribes/schedule.py`:

```python
"""Cross-OS schedule helpers — generate snippet files for cron / launchd
/ systemd / Windows Task Scheduler.

We DON'T install schedules ourselves — printing snippet + instructions
keeps cross-platform safety. User installs via documented one-liner.
"""
from __future__ import annotations

import re
import sys

# Public re-exports for the install/uninstall commands
__all__ = [
    "detect_platform", "parse_interval",
    "generate_cron_line", "generate_launchd_plist",
    "generate_systemd_units", "generate_taskscheduler_xml",
]


def detect_platform() -> str:
    """Return one of 'launchd' / 'systemd' / 'cron' / 'taskscheduler'."""
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform == "win32":
        return "taskscheduler"
    if sys.platform.startswith("linux"):
        # Prefer systemd if available; cron is universal fallback
        import shutil
        if shutil.which("systemctl"):
            return "systemd"
        return "cron"
    return "cron"


def parse_interval(spec: str) -> int:
    """Parse '15m' / '1h' / '6h' / '1d' to seconds. Raises ValueError on garbage."""
    m = re.match(r"^(\d+)([mhd])$", (spec or "").strip().lower())
    if not m:
        raise ValueError(f"invalid interval: {spec!r}")
    n = int(m.group(1))
    if n <= 0:
        raise ValueError("interval must be positive")
    return n * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_schedule_core.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/schedule.py \
        tests/test_subscribes_schedule_core.py
git commit -m "feat(v0.7): subscribes.schedule core — platform detect + interval parse"
```

---

### Task 24: Cron + systemd snippet generators

**Files:**
- Modify: `skills/youtube_transcribe/subscribes/schedule.py`
- Create: `tests/test_subscribes_schedule_unix.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_schedule_unix.py`:

```python
"""Tests for cron + systemd snippet generation."""
from skills.youtube_transcribe.subscribes.schedule import (
    generate_cron_line,
    generate_systemd_units,
)


def test_cron_line_hourly():
    line = generate_cron_line(
        command_argv=["/usr/local/bin/youtube-transcribe", "subscribes",
                       "update", "--prompt", "x"],
        every_seconds=3600,
    )
    # Hourly cron expression: "0 * * * *"
    assert line.startswith("0 * * * *")
    assert "/usr/local/bin/youtube-transcribe" in line
    assert "subscribes" in line


def test_cron_line_every_15min():
    line = generate_cron_line(
        command_argv=["yt-tr", "subscribes", "update"],
        every_seconds=900,
    )
    # 15-min cron: "*/15 * * * *"
    assert line.startswith("*/15 * * * *")


def test_cron_line_daily():
    line = generate_cron_line(
        command_argv=["yt-tr", "subscribes", "update"],
        every_seconds=86400,
    )
    assert line.startswith("0 0 * * *")


def test_cron_line_quotes_args_with_spaces():
    """Args with spaces должны быть в кавычках."""
    line = generate_cron_line(
        command_argv=["yt-tr", "subscribes", "update",
                       "--prompt", "summarize this week"],
        every_seconds=3600,
    )
    assert '"summarize this week"' in line or "'summarize this week'" in line


def test_systemd_units_returns_pair():
    timer, service = generate_systemd_units(
        command_argv=["/usr/local/bin/yt-tr", "subscribes", "update"],
        every_seconds=3600,
        label="yt-tr-subscribes",
    )
    assert "[Timer]" in timer
    assert "OnUnitActiveSec=3600" in timer or "OnUnitActiveSec=1h" in timer
    assert "[Service]" in service
    assert "ExecStart=" in service
    assert "/usr/local/bin/yt-tr" in service


def test_systemd_user_install_path_hint():
    """Snippet should mention ~/.config/systemd/user/ in the install
    instructions."""
    timer, service = generate_systemd_units(
        command_argv=["yt-tr", "subscribes", "update"],
        every_seconds=3600,
        label="yt-tr-subscribes",
    )
    # Either content lists user-mode path
    assert "[Install]" in timer
    assert "WantedBy=timers.target" in timer
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_schedule_unix.py -v`
Expected: FAIL — functions not implemented yet.

- [ ] **Step 3: Add cron + systemd generators to `subscribes/schedule.py`**

Append to `subscribes/schedule.py`:

```python
import shlex


def generate_cron_line(
    *,
    command_argv: list[str],
    every_seconds: int,
) -> str:
    """Generate a crontab line that runs `command_argv` at `every_seconds`.

    Supports common intervals: minutes (1-59), hours (1-23), days.
    Pads to standard 5-field cron expression.
    """
    cron_expr = _seconds_to_cron(every_seconds)
    cmd = " ".join(shlex.quote(a) for a in command_argv)
    return f"{cron_expr} {cmd}"


def generate_systemd_units(
    *,
    command_argv: list[str],
    every_seconds: int,
    label: str,
) -> tuple[str, str]:
    """Generate (timer_unit, service_unit) text pair for systemd.

    Caller installs at ~/.config/systemd/user/<label>.timer and .service.
    """
    timer = (
        f"[Unit]\n"
        f"Description=youtube-transcribe {label}\n\n"
        f"[Timer]\n"
        f"OnBootSec=2min\n"
        f"OnUnitActiveSec={every_seconds}\n"
        f"Unit={label}.service\n\n"
        f"[Install]\n"
        f"WantedBy=timers.target\n"
    )
    exec_start = " ".join(shlex.quote(a) for a in command_argv)
    service = (
        f"[Unit]\n"
        f"Description=youtube-transcribe {label}\n\n"
        f"[Service]\n"
        f"Type=oneshot\n"
        f"ExecStart={exec_start}\n"
    )
    return timer, service


def _seconds_to_cron(seconds: int) -> str:
    """Approximate cron expression for common intervals."""
    if seconds < 60:
        raise ValueError("cron supports minute resolution at best")
    minutes = seconds // 60
    if minutes < 60:
        return f"*/{minutes} * * * *"
    hours = minutes // 60
    if hours < 24:
        return f"0 */{hours} * * *" if hours > 1 else "0 * * * *"
    days = hours // 24
    return f"0 0 */{days} * *" if days > 1 else "0 0 * * *"
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_schedule_unix.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/schedule.py \
        tests/test_subscribes_schedule_unix.py
git commit -m "feat(v0.7): subscribes.schedule — cron + systemd snippet generators"
```

---

### Task 25: launchd plist generator

**Files:**
- Modify: `skills/youtube_transcribe/subscribes/schedule.py`
- Create: `tests/test_subscribes_schedule_launchd.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_schedule_launchd.py`:

```python
"""Tests for macOS launchd plist generation."""
from skills.youtube_transcribe.subscribes.schedule import (
    generate_launchd_plist,
)


def test_launchd_plist_basic_structure():
    plist = generate_launchd_plist(
        command_argv=["/usr/local/bin/yt-tr", "subscribes", "update"],
        every_seconds=3600,
        label="com.user.yt-tr-subscribes",
    )
    assert "<?xml" in plist
    assert "<plist" in plist
    assert "<key>Label</key>" in plist
    assert "<string>com.user.yt-tr-subscribes</string>" in plist
    assert "<key>StartInterval</key>" in plist
    assert "<integer>3600</integer>" in plist


def test_launchd_plist_program_arguments():
    plist = generate_launchd_plist(
        command_argv=["/usr/local/bin/yt-tr", "subscribes",
                       "update", "--days", "7"],
        every_seconds=900,
        label="com.user.test",
    )
    assert "<key>ProgramArguments</key>" in plist
    assert "<array>" in plist
    assert "<string>/usr/local/bin/yt-tr</string>" in plist
    assert "<string>subscribes</string>" in plist
    assert "<string>update</string>" in plist
    assert "<string>--days</string>" in plist
    assert "<string>7</string>" in plist


def test_launchd_plist_run_at_load():
    """Mandatory key: RunAtLoad = true (otherwise first run waits StartInterval)."""
    plist = generate_launchd_plist(
        command_argv=["yt-tr"],
        every_seconds=3600,
        label="com.user.test",
    )
    assert "<key>RunAtLoad</key>" in plist
    assert "<true/>" in plist


def test_launchd_plist_escapes_xml_special_chars():
    """If command contains < > & — they must be escaped in <string>."""
    plist = generate_launchd_plist(
        command_argv=["yt-tr", "--prompt", "find <ai> & related"],
        every_seconds=3600,
        label="com.user.test",
    )
    assert "&lt;ai&gt;" in plist
    assert "&amp;" in plist
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_schedule_launchd.py -v`
Expected: FAIL.

- [ ] **Step 3: Add `generate_launchd_plist` to `subscribes/schedule.py`**

Append:

```python
from xml.sax.saxutils import escape as _xml_escape


def generate_launchd_plist(
    *,
    command_argv: list[str],
    every_seconds: int,
    label: str,
) -> str:
    """Generate a macOS LaunchAgent plist text.

    Caller saves to ~/Library/LaunchAgents/<label>.plist and loads via
    `launchctl load`.
    """
    args_xml = "\n    ".join(
        f"<string>{_xml_escape(a)}</string>" for a in command_argv
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        f'  <key>Label</key>\n  <string>{_xml_escape(label)}</string>\n'
        '  <key>ProgramArguments</key>\n'
        '  <array>\n'
        f'    {args_xml}\n'
        '  </array>\n'
        f'  <key>StartInterval</key>\n  <integer>{every_seconds}</integer>\n'
        '  <key>RunAtLoad</key>\n  <true/>\n'
        '  <key>StandardOutPath</key>\n'
        f'  <string>/tmp/{_xml_escape(label)}.log</string>\n'
        '  <key>StandardErrorPath</key>\n'
        f'  <string>/tmp/{_xml_escape(label)}.err</string>\n'
        '</dict>\n'
        '</plist>\n'
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_schedule_launchd.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/schedule.py \
        tests/test_subscribes_schedule_launchd.py
git commit -m "feat(v0.7): subscribes.schedule — macOS launchd plist generator"
```

---

### Task 26: Windows Task Scheduler XML generator

**Files:**
- Modify: `skills/youtube_transcribe/subscribes/schedule.py`
- Create: `tests/test_subscribes_schedule_windows.py`

- [ ] **Step 1: Write failing tests**

`tests/test_subscribes_schedule_windows.py`:

```python
"""Tests for Windows Task Scheduler XML generation."""
from skills.youtube_transcribe.subscribes.schedule import (
    generate_taskscheduler_xml,
)


def test_taskscheduler_xml_structure():
    xml = generate_taskscheduler_xml(
        command_argv=["C:\\Python\\Scripts\\yt-tr.exe", "subscribes", "update"],
        every_seconds=3600,
        task_name="yt-tr-subscribes",
    )
    assert "<?xml" in xml
    assert "<Task " in xml
    assert "<Triggers>" in xml
    assert "<TimeTrigger>" in xml or "<CalendarTrigger>" in xml
    assert "<Actions>" in xml
    assert "<Exec>" in xml


def test_taskscheduler_xml_interval_pt1h():
    """PT1H is the ISO 8601 duration for 1 hour."""
    xml = generate_taskscheduler_xml(
        command_argv=["yt-tr.exe", "subscribes", "update"],
        every_seconds=3600,
        task_name="t",
    )
    assert "PT1H" in xml


def test_taskscheduler_xml_interval_pt15m():
    xml = generate_taskscheduler_xml(
        command_argv=["yt-tr.exe"],
        every_seconds=900,
        task_name="t",
    )
    assert "PT15M" in xml


def test_taskscheduler_xml_command_and_args_separated():
    """Exec/Command and Exec/Arguments must be separate."""
    xml = generate_taskscheduler_xml(
        command_argv=["C:\\Python\\Scripts\\yt-tr.exe", "subscribes",
                       "update", "--days", "7"],
        every_seconds=3600,
        task_name="t",
    )
    assert "<Command>C:\\Python\\Scripts\\yt-tr.exe</Command>" in xml
    assert "<Arguments>" in xml
    # Subsequent args joined
    assert "subscribes" in xml
    assert "update" in xml
    assert "--days" in xml


def test_taskscheduler_xml_escapes_special_chars():
    xml = generate_taskscheduler_xml(
        command_argv=["yt-tr.exe", "--prompt", "find <x> & y"],
        every_seconds=3600,
        task_name="t",
    )
    assert "&lt;x&gt;" in xml
    assert "&amp;" in xml
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_subscribes_schedule_windows.py -v`
Expected: FAIL.

- [ ] **Step 3: Add `generate_taskscheduler_xml` to `subscribes/schedule.py`**

Append:

```python
def generate_taskscheduler_xml(
    *,
    command_argv: list[str],
    every_seconds: int,
    task_name: str,
) -> str:
    """Generate a Windows Task Scheduler import XML.

    Caller saves to a temp file and imports via:
        schtasks /create /tn <name> /xml <file>
    """
    duration = _seconds_to_iso8601(every_seconds)
    command = _xml_escape(command_argv[0])
    args = " ".join(_xml_escape(a) for a in command_argv[1:])
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.4" '
        'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo>\n'
        f'    <URI>\\{_xml_escape(task_name)}</URI>\n'
        '  </RegistrationInfo>\n'
        '  <Triggers>\n'
        '    <TimeTrigger>\n'
        '      <Repetition>\n'
        f'        <Interval>{duration}</Interval>\n'
        '        <StopAtDurationEnd>false</StopAtDurationEnd>\n'
        '      </Repetition>\n'
        '      <StartBoundary>2026-01-01T00:00:00</StartBoundary>\n'
        '      <Enabled>true</Enabled>\n'
        '    </TimeTrigger>\n'
        '  </Triggers>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '  </Settings>\n'
        '  <Actions>\n'
        '    <Exec>\n'
        f'      <Command>{command}</Command>\n'
        f'      <Arguments>{args}</Arguments>\n'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )


def _seconds_to_iso8601(seconds: int) -> str:
    """Convert seconds to ISO 8601 duration (PT15M / PT1H / P1D)."""
    if seconds < 60:
        raise ValueError("interval below 1 minute not supported")
    minutes = seconds // 60
    if minutes < 60:
        return f"PT{minutes}M"
    hours = minutes // 60
    if hours < 24:
        return f"PT{hours}H"
    days = hours // 24
    return f"P{days}D"
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_subscribes_schedule_windows.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/subscribes/schedule.py \
        tests/test_subscribes_schedule_windows.py
git commit -m "feat(v0.7): subscribes.schedule — Windows Task Scheduler XML generator"
```

---

### Task 27: schedule install/uninstall CLI command

**Files:**
- Modify: `skills/youtube_transcribe/subscribes/cli.py` (add schedule subgroup)
- Create: `tests/test_cli_subscribes_schedule.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli_subscribes_schedule.py`:

```python
"""Tests for `subscribes schedule install/uninstall` CLI."""
from unittest.mock import patch

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def test_schedule_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["subscribes", "schedule", "--help"])
    assert res.exit_code == 0
    assert "install" in res.output
    assert "uninstall" in res.output


def test_schedule_install_prints_launchd_on_macos():
    with patch(
        "skills.youtube_transcribe.subscribes.cli.detect_platform",
        return_value="launchd",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "schedule", "install",
            "--every", "1h",
            "--prompt", "summarize",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "<plist" in res.output
    assert "PT" not in res.output  # not Windows xml
    assert "LaunchAgents" in res.output or "launchctl" in res.output


def test_schedule_install_prints_cron_on_linux():
    with patch(
        "skills.youtube_transcribe.subscribes.cli.detect_platform",
        return_value="cron",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "schedule", "install", "--every", "1h",
            "--prompt", "x",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "crontab" in res.output.lower() or "0 *" in res.output


def test_schedule_install_prints_systemd():
    with patch(
        "skills.youtube_transcribe.subscribes.cli.detect_platform",
        return_value="systemd",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "schedule", "install", "--every", "1h",
            "--prompt", "x",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "[Timer]" in res.output
    assert "systemctl" in res.output.lower()


def test_schedule_install_prints_taskscheduler_on_windows():
    with patch(
        "skills.youtube_transcribe.subscribes.cli.detect_platform",
        return_value="taskscheduler",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "schedule", "install", "--every", "1h",
            "--prompt", "x",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "<Task" in res.output
    assert "schtasks" in res.output.lower()


def test_schedule_install_platform_override():
    """--platform cron forces cron output regardless of detected platform."""
    with patch(
        "skills.youtube_transcribe.subscribes.cli.detect_platform",
        return_value="launchd",  # detected
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "subscribes", "schedule", "install",
            "--every", "1h", "--platform", "cron",
            "--prompt", "x",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "<plist" not in res.output
    assert "crontab" in res.output.lower() or "0 *" in res.output


def test_schedule_install_invalid_interval():
    runner = CliRunner()
    res = runner.invoke(cli, [
        "subscribes", "schedule", "install",
        "--every", "bogus", "--prompt", "x",
    ], catch_exceptions=False)
    assert res.exit_code == 2


def test_schedule_uninstall_prints_instructions():
    runner = CliRunner()
    res = runner.invoke(cli, [
        "subscribes", "schedule", "uninstall",
    ], catch_exceptions=False)
    assert res.exit_code == 0
    # Should give removal hints for all platforms
    out = res.output.lower()
    assert "launchctl" in out or "crontab" in out or "schtasks" in out
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_subscribes_schedule.py -v`
Expected: FAIL.

- [ ] **Step 3: Add schedule subgroup to `subscribes/cli.py`**

Append to `subscribes/cli.py`:

```python
from skills.youtube_transcribe.subscribes.schedule import (
    detect_platform, parse_interval,
    generate_cron_line, generate_launchd_plist,
    generate_systemd_units, generate_taskscheduler_xml,
)


@subscribes_group.group(name="schedule")
def schedule_group() -> None:
    """Generate scheduler snippets (cron/launchd/systemd/Task Scheduler)."""


@schedule_group.command(name="install")
@click.option("--every", default="1h", show_default=True,
              help="Interval: 15m, 1h, 6h, 1d.")
@click.option("--platform", "platform_opt",
              type=click.Choice(["auto", "cron", "launchd",
                                  "systemd", "taskscheduler"]),
              default="auto", show_default=True)
@click.option("--prompt", default=None,
              help="Embedded prompt for the scheduled subscribes update.")
@click.option("--prompt-file", default=None,
              type=click.Path(exists=True, path_type=Path),
              help="Embedded prompt-file path for the scheduled run.")
@click.option("--group", "group_opt", default=None,
              help="Embedded --group for the scheduled run.")
def schedule_install_cmd(
    every: str,
    platform_opt: str,
    prompt: str | None,
    prompt_file: Path | None,
    group_opt: str | None,
) -> None:
    """Print a schedule snippet + install instructions for the current OS."""
    try:
        seconds = parse_interval(every)
    except ValueError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)

    plat = detect_platform() if platform_opt == "auto" else platform_opt

    # Build the command argv that the scheduler will invoke
    yt_exe = sys.executable.replace("python", "youtube-transcribe") \
        if "youtube-transcribe" not in sys.executable else sys.executable
    # Best-effort fallback to "youtube-transcribe" on PATH
    if not Path(yt_exe).exists():
        yt_exe = "youtube-transcribe"
    argv = [yt_exe, "subscribes", "update"]
    if prompt:
        argv.extend(["--prompt", prompt])
    if prompt_file:
        argv.extend(["--prompt-file", str(prompt_file)])
    if group_opt:
        argv.extend(["--group", group_opt])

    if plat == "launchd":
        label = "com.user.yt-tr-subscribes"
        plist = generate_launchd_plist(
            command_argv=argv, every_seconds=seconds, label=label,
        )
        path = f"~/Library/LaunchAgents/{label}.plist"
        _console.print(f"\n[bold]# Save to {path}[/bold]\n")
        click.echo(plist)
        _console.print(
            f"\n[bold]# Then run:[/bold]\n"
            f"  mkdir -p ~/Library/LaunchAgents\n"
            f"  cat > {path} <<'EOF'\n  ...  (the XML above)\n  EOF\n"
            f"  launchctl load {path}\n"
            f"\n[dim]# To remove later:[/dim]\n"
            f"  launchctl unload {path} && rm {path}\n"
        )
    elif plat == "cron":
        line = generate_cron_line(command_argv=argv, every_seconds=seconds)
        _console.print("\n[bold]# Add to crontab via `crontab -e`:[/bold]\n")
        click.echo(line)
        _console.print(
            "\n[dim]# To remove: `crontab -e` and delete the line above.[/dim]\n"
        )
    elif plat == "systemd":
        timer, service = generate_systemd_units(
            command_argv=argv, every_seconds=seconds, label="yt-tr-subscribes",
        )
        _console.print(
            "\n[bold]# Save the timer to ~/.config/systemd/user/"
            "yt-tr-subscribes.timer:[/bold]\n"
        )
        click.echo(timer)
        _console.print(
            "\n[bold]# Save the service to ~/.config/systemd/user/"
            "yt-tr-subscribes.service:[/bold]\n"
        )
        click.echo(service)
        _console.print(
            "\n[bold]# Then enable + start:[/bold]\n"
            "  systemctl --user daemon-reload\n"
            "  systemctl --user enable --now yt-tr-subscribes.timer\n"
            "\n[dim]# To remove:[/dim]\n"
            "  systemctl --user disable --now yt-tr-subscribes.timer\n"
            "  rm ~/.config/systemd/user/yt-tr-subscribes.{timer,service}\n"
        )
    elif plat == "taskscheduler":
        xml = generate_taskscheduler_xml(
            command_argv=argv, every_seconds=seconds,
            task_name="yt-tr-subscribes",
        )
        _console.print(
            "\n[bold]# Save XML to a temp file (e.g. "
            "%TEMP%\\yt-tr-subscribes.xml):[/bold]\n"
        )
        click.echo(xml)
        _console.print(
            "\n[bold]# Then import via schtasks:[/bold]\n"
            "  schtasks /create /tn yt-tr-subscribes /xml "
            "%TEMP%\\yt-tr-subscribes.xml\n"
            "\n[dim]# To remove:[/dim]\n"
            "  schtasks /delete /tn yt-tr-subscribes /f\n"
        )


@schedule_group.command(name="uninstall")
def schedule_uninstall_cmd() -> None:
    """Print uninstall instructions for all supported platforms."""
    _console.print(
        "[bold]# macOS (launchd):[/bold]\n"
        "  launchctl unload ~/Library/LaunchAgents/com.user.yt-tr-subscribes.plist\n"
        "  rm ~/Library/LaunchAgents/com.user.yt-tr-subscribes.plist\n\n"
        "[bold]# Linux (cron):[/bold]\n"
        "  crontab -e   # delete the yt-tr-subscribes line\n\n"
        "[bold]# Linux (systemd):[/bold]\n"
        "  systemctl --user disable --now yt-tr-subscribes.timer\n"
        "  rm ~/.config/systemd/user/yt-tr-subscribes.{timer,service}\n\n"
        "[bold]# Windows (Task Scheduler):[/bold]\n"
        "  schtasks /delete /tn yt-tr-subscribes /f\n"
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_subscribes_schedule.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run full suite check**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: `1 failed, ~680 passed, 2 skipped`.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/subscribes/cli.py \
        tests/test_cli_subscribes_schedule.py
git commit -m "feat(v0.7): subscribes schedule install/uninstall — cross-OS snippet generation"
```

---

# Phase 10 — Web UI extensions

### Task 28: webui Research tab

**Files:**
- Modify: `skills/youtube_transcribe/webui/app.py` (add Research tab)
- Create: `tests/test_webui_research_tab.py`

The existing webui has one tab. v0.7 adds two new tabs (Research + Subscribes). Tests use mocks because we can't drive Gradio in unit tests, but we can call the tab-building functions and verify their structure.

- [ ] **Step 1: Write failing tests**

`tests/test_webui_research_tab.py`:

```python
"""Tests for the Research tab in webui/app.py.

The tab itself is Gradio Blocks — we can't render it in pytest, but we
can verify the tab-building function exists, returns a Blocks/Tab object,
and that the handler delegates to run_research with parsed parameters.
"""
from pathlib import Path
from unittest.mock import patch


def test_research_tab_builder_exists():
    """build_research_tab callable exists and is importable."""
    try:
        from skills.youtube_transcribe.webui.app import build_research_tab
    except ImportError:
        # Gradio not installed — skip test (we only verify when webui extra installed)
        import pytest
        pytest.skip("gradio not installed; webui extra not available")
    assert callable(build_research_tab)


def test_research_handler_delegates_to_pipeline():
    """The button handler in the Research tab invokes run_research."""
    try:
        from skills.youtube_transcribe.webui.app import _handle_research_submit
    except ImportError:
        import pytest
        pytest.skip("gradio not installed")
    with patch(
        "skills.youtube_transcribe.research.pipeline.run_research",
        return_value=Path("/tmp/fake"),
    ) as mock_pipe:
        out = _handle_research_submit(
            query="Claude features",
            languages_csv="ru,en",
            days=30,
            limit=20,
            match_text="",
            filter_text="",
            no_analyze=True,
            yes=True,
            prompt="",
            analyze_backend="gemini",
            filter_backend="gemini",
            backend="subtitles",
        )
    mock_pipe.assert_called_once()
    assert "fake" in str(out)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_webui_research_tab.py -v`
Expected: FAIL — `build_research_tab` not yet defined.

- [ ] **Step 3: Add Research tab to `webui/app.py`**

Open `skills/youtube_transcribe/webui/app.py`. Currently `build_ui()` returns one-tab Gradio Blocks. We extend it.

После существующих imports добавь:

```python
from pathlib import Path
from skills.youtube_transcribe.research.pipeline import run_research
from skills.youtube_transcribe.config import (
    get_api_key, load_config, CONFIG_PATH,
)
```

После функции `build_ui()` (или в конце файла) добавь:

```python
def build_research_tab(gr):
    """Build the Research tab UI. Returns the Tab object."""
    with gr.Tab("Research"):
        gr.Markdown("# Research a topic\n"
                    "Поиск, фильтрация, транскрибация, анализ — за один проход.")
        query = gr.Textbox(label="Query", placeholder="Claude новинки за неделю")
        with gr.Row():
            languages = gr.Textbox(label="Languages (CSV)", value="ru,en")
            days = gr.Number(label="Days", value=30, precision=0)
            limit = gr.Number(label="Limit", value=20, precision=0)
        match_text = gr.Textbox(label="--match (substring)", value="")
        filter_text = gr.Textbox(label="--filter (LLM)", value="")
        backend = gr.Dropdown(
            label="Transcription backend",
            choices=["smart", "subtitles", "whisper-local",
                      "gemini", "groq", "openai", "deepgram", "assemblyai"],
            value="smart",
        )
        with gr.Row():
            analyze_backend = gr.Dropdown(
                label="Analyze LLM",
                choices=["gemini", "claude", "openai", "ollama"],
                value="gemini",
            )
            filter_backend = gr.Dropdown(
                label="Filter LLM",
                choices=["gemini", "claude", "openai", "ollama"],
                value="gemini",
            )
        prompt = gr.Textbox(label="Analyze prompt", lines=4)
        no_analyze = gr.Checkbox(label="Skip analyze (just transcribe)",
                                  value=False)
        submit = gr.Button("Run research", variant="primary")
        output = gr.Textbox(label="Output path", interactive=False, lines=2)

        submit.click(
            fn=_handle_research_submit,
            inputs=[query, languages, days, limit,
                    match_text, filter_text,
                    no_analyze, gr.State(True),  # yes always True in UI
                    prompt, analyze_backend, filter_backend, backend],
            outputs=[output],
        )


def _handle_research_submit(
    query, languages_csv, days, limit, match_text, filter_text,
    no_analyze, yes, prompt, analyze_backend, filter_backend, backend,
):
    """Webui callback — delegate to pipeline.run_research."""
    from datetime import date as _date
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    languages = [s.strip() for s in (languages_csv or "ru,en").split(",")]
    api_keys = {
        "gemini": get_api_key("gemini"),
        "anthropic": get_api_key("anthropic"),
        "openai": get_api_key("openai"),
        "ollama": None,
    }
    batch_opts = {"backend": backend} if backend else {}
    result = run_research(
        query=query or None,
        queries_by_language=None,
        languages=languages,
        days=int(days) if days else 30,
        since=None, until=None,
        limit=int(limit) if limit else 20,
        match=match_text or None,
        filter_text=filter_text or None,
        in_subscribes=False, group=None,
        yes=bool(yes), no_analyze=bool(no_analyze),
        prompt=prompt or None, prompt_file=None,
        analyze_backend=analyze_backend,
        filter_backend=filter_backend,
        translate_backend=analyze_backend,
        ollama_model="llama3.2:3b",
        ollama_host="http://localhost:11434",
        no_stdout=True,
        output_dir=cfg.output_dir if cfg else "./transcripts",
        batch_name=f"webui_research_{int(__import__('time').time())}",
        api_keys=api_keys,
        batch_opts=batch_opts,
    )
    return f"✓ Result: {result}" if result else "Nothing produced"
```

Найди `def build_ui()` и в его теле, после существующего таба, добавь вызов `build_research_tab(gr)` внутри тех же `with gr.Blocks(...) as demo:`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_webui_research_tab.py -v`
Expected: 2 passed (или skipped если gradio не доступен).

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/webui/app.py \
        tests/test_webui_research_tab.py
git commit -m "feat(v0.7): webui — Research tab (Gradio)"
```

---

### Task 29: webui Subscribes tab

**Files:**
- Modify: `skills/youtube_transcribe/webui/app.py` (add Subscribes tab)
- Create: `tests/test_webui_subscribes_tab.py`

- [ ] **Step 1: Write failing tests**

`tests/test_webui_subscribes_tab.py`:

```python
"""Tests for the Subscribes tab in webui/app.py."""
from pathlib import Path
from unittest.mock import patch


def test_subscribes_tab_builder_exists():
    try:
        from skills.youtube_transcribe.webui.app import build_subscribes_tab
    except ImportError:
        import pytest
        pytest.skip("gradio not installed")
    assert callable(build_subscribes_tab)


def test_subscribes_add_handler():
    try:
        from skills.youtube_transcribe.webui.app import (
            _handle_subscribes_add,
        )
    except ImportError:
        import pytest
        pytest.skip("gradio not installed")
    from skills.youtube_transcribe.subscribes.channel_resolver import (
        ResolvedChannel,
    )
    with patch(
        "skills.youtube_transcribe.subscribes.cli.resolve_channel",
        return_value=ResolvedChannel(
            url="https://www.youtube.com/@A", handle="@A",
            channel_id="UC_a", title="A",
        ),
    ), patch(
        "skills.youtube_transcribe.subscribes.cli.add_channel",
    ) as mock_add:
        msg = _handle_subscribes_add(
            "https://www.youtube.com/@A", group="ai",
        )
    mock_add.assert_called_once()
    assert "@A" in msg or "Added" in msg


def test_subscribes_update_handler_delegates():
    try:
        from skills.youtube_transcribe.webui.app import (
            _handle_subscribes_update,
        )
    except ImportError:
        import pytest
        pytest.skip("gradio not installed")
    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.run_subscribes_update",
        return_value=Path("/tmp/fake"),
    ) as mock_pipe:
        out = _handle_subscribes_update(
            group="", days=7, no_analyze=True, yes=True,
            prompt="", analyze_backend="gemini", backend="subtitles",
        )
    mock_pipe.assert_called_once()
    assert "fake" in str(out)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_webui_subscribes_tab.py -v`
Expected: FAIL.

- [ ] **Step 3: Add Subscribes tab to `webui/app.py`**

```python
from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
from skills.youtube_transcribe.subscribes.store import (
    load_subscribes, Channel,
)
from skills.youtube_transcribe.subscribes.cli import (
    SUBSCRIBES_PATH, resolve_channel, add_channel, remove_channel,
)


def build_subscribes_tab(gr):
    with gr.Tab("Subscribes"):
        gr.Markdown("# Subscribes\nManage and update your channel list.")
        with gr.Row():
            url_input = gr.Textbox(label="Channel URL or @handle",
                                    placeholder="https://www.youtube.com/@AnthropicAI")
            group_input = gr.Textbox(label="Group (optional)")
            add_btn = gr.Button("Add channel")
        list_output = gr.Textbox(label="Channels", lines=10, interactive=False)
        refresh_btn = gr.Button("Refresh list")

        gr.Markdown("---\n## Run update")
        with gr.Row():
            update_group = gr.Textbox(label="--group (filter, optional)")
            update_days = gr.Number(label="--days (override, optional)", value=0, precision=0)
        update_prompt = gr.Textbox(label="Analyze prompt", lines=3)
        update_no_analyze = gr.Checkbox(label="--no-analyze", value=False)
        update_backend = gr.Dropdown(
            label="Transcription backend",
            choices=["smart", "subtitles", "whisper-local", "gemini"],
            value="smart",
        )
        update_analyze_backend = gr.Dropdown(
            label="Analyze LLM",
            choices=["gemini", "claude", "openai", "ollama"],
            value="gemini",
        )
        update_btn = gr.Button("Run subscribes update", variant="primary")
        update_output = gr.Textbox(label="Result", interactive=False, lines=2)

        add_btn.click(
            fn=_handle_subscribes_add,
            inputs=[url_input, group_input],
            outputs=[list_output],
        )
        refresh_btn.click(
            fn=_handle_subscribes_list,
            outputs=[list_output],
        )
        update_btn.click(
            fn=_handle_subscribes_update,
            inputs=[update_group, update_days, update_no_analyze,
                    gr.State(True),  # yes
                    update_prompt, update_analyze_backend, update_backend],
            outputs=[update_output],
        )


def _handle_subscribes_add(channel_url, group):
    from datetime import date
    if not channel_url:
        return "Empty URL"
    try:
        resolved = resolve_channel(channel_url)
    except ValueError as e:
        return f"Resolution failed: {e}"
    add_channel(SUBSCRIBES_PATH, Channel(
        url=resolved.url, handle=resolved.handle,
        channel_id=resolved.channel_id,
        group=group or None,
        added=date.today().isoformat(),
    ))
    return _handle_subscribes_list()


def _handle_subscribes_list():
    chans = load_subscribes(SUBSCRIBES_PATH)
    if not chans:
        return "(no channels)"
    lines = []
    for c in chans:
        lines.append(
            f"{c.handle or c.url}  [{c.group or '—'}]  "
            f"last_seen={c.last_seen_published or '—'}"
        )
    return "\n".join(lines)


def _handle_subscribes_update(group, days, no_analyze, yes,
                               prompt, analyze_backend, backend):
    api_keys = {
        "gemini": get_api_key("gemini"),
        "anthropic": get_api_key("anthropic"),
        "openai": get_api_key("openai"),
        "ollama": None,
    }
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    output_dir = cfg.output_dir if cfg else "./transcripts"
    batch_opts = {"backend": backend} if backend else {}
    try:
        result = run_subscribes_update(
            subscribes_path=SUBSCRIBES_PATH,
            group=group or None,
            days=int(days) if days else None,
            since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=bool(yes),
            no_analyze=bool(no_analyze),
            prompt=prompt or None, prompt_file=None,
            analyze_backend=analyze_backend,
            filter_backend=analyze_backend,
            ollama_model="llama3.2:3b",
            ollama_host="http://localhost:11434",
            no_stdout=True,
            output_dir=output_dir,
            api_keys=api_keys,
            batch_opts=batch_opts,
        )
        return f"✓ Result: {result}" if result else "Nothing produced"
    except Exception as e:
        return f"Error: {e}"
```

Не забудь вызвать `build_subscribes_tab(gr)` внутри `build_ui()` рядом с `build_research_tab(gr)`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_webui_subscribes_tab.py -v`
Expected: 3 passed (или skipped).

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/webui/app.py \
        tests/test_webui_subscribes_tab.py
git commit -m "feat(v0.7): webui — Subscribes tab (Gradio)"
```

---

# Phase 11 — Docs + release

### Task 30: README sections + CHANGELOG entry

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add README section "Research a topic"**

В `README.md` после раздела `## Analyze — free-form LLM analysis...` (от v0.6) добавь:

````markdown
## Research a topic (v0.7)

Discover and analyze new videos on a topic in one command. YouTube
ranking decides relevance, you decide period + analysis angle.

```bash
# Default — last 30 days, ru+en search, top 20 results
yt-tr research "Claude новинки" \
  --prompt "Сделай конспект ключевых идей" \
  --analyze-backend gemini

# Narrower: 7 days, single language, fewer videos
yt-tr research "AI agents 2026" \
  --days 7 --languages en --limit 10 \
  --prompt "Compare design choices"

# Historical: specific window
yt-tr research "LangChain release" \
  --since 2024-06-01 --until 2024-08-31 \
  --prompt "Что нового"

# Substring + LLM filter combo
yt-tr research "machine learning" \
  --match "tutorial" --filter "обучающие для новичков" \
  --prompt "Что общего, что уникального"

# Just transcripts, no analyze
yt-tr research "новинки 2026" --no-analyze

# Cross-pollination: only from my subscribed channels
yt-tr research "Claude" --in-subscribes --group ai-research \
  --days 14 --prompt "Свежие фишки"
```

## Subscribes — channels you follow (v0.7)

```bash
# Add channels
yt-tr subscribes add https://www.youtube.com/@AnthropicAI --group ai
yt-tr subscribes add https://www.youtube.com/@lexfridman --group philosophy

# List
yt-tr subscribes list
yt-tr subscribes list --group ai

# Edit subscribes.toml manually (cross-OS $EDITOR)
yt-tr subscribes edit

# Remove
yt-tr subscribes remove @AnthropicAI

# Update: incremental (stateful per channel)
yt-tr subscribes update --prompt "Что обсуждалось"

# Update: force window
yt-tr subscribes update --days 7 --group ai \
  --filter "только про новые модели" \
  --prompt "Сравни подходы"

# Generate scheduler snippet (no automatic install)
yt-tr subscribes schedule install --every 1h --prompt "Твой обычный prompt"
# → prints launchd/cron/systemd/Task Scheduler snippet + install instructions

# View past runs
yt-tr history list
yt-tr history list --type research --last 5
yt-tr history show <run-id>
```

The `subscribes` store lives at `~/.youtube-transcribe/subscribes.toml`
and is safe to hand-edit; CLI mutations preserve your comments via
`tomlkit`.
````

- [ ] **Step 2: Add CHANGELOG entry**

В `CHANGELOG.md` сверху, над `## [0.6.0]`, добавить:

```markdown
## [0.7.0] — 2026-05-12

### Added
- `research "query"` — broad topic discovery: multi-language YouTube
  search (LLM-translates query into each `--languages`), date window
  (`--days N` or `--since/--until`), substring `--match` and LLM
  `--filter` pre-screens, optional TTY checkpoint, batch transcribe,
  optional analyze. Also supports `--in-subscribes` to source from
  your subscribed channels instead of global search.
- `subscribes` command group (`add`/`remove`/`list`/`edit`/`update`)
  for tracking favourite channels. Stateful incremental updates
  (`last_seen_video_id` per channel in subscribes.toml). Override
  with `--days`/`--since`/`--until` runs ad-hoc without disturbing
  state. RSS-first discovery (~10× faster than yt-dlp scraping);
  yt-dlp fallback for `--no-rss` and duration-filtered runs.
- `subscribes schedule install` — generates cron / launchd /
  systemd / Windows Task Scheduler snippet + install instructions.
  Does NOT install automatically.
- `history list` / `history show` — persistent log of research and
  subscribes runs in `~/.youtube-transcribe/history.toml`.
- Web UI extensions — Research and Subscribes tabs in `yt-tr webui`.
- Channel groups in subscribes.toml (`group = "ai-research"`).
  `subscribes list --group X` and `subscribes update --group X`.

### Changed
- `batch_cmd` refactored: post-args-resolution core extracted as
  `_run_batch_pipeline(targets, cfg, opts)` so research/subscribes
  pipelines reuse it without duplication. External behavior of
  `youtube-transcribe batch` preserved byte-for-byte (all 614 v0.6
  tests stay green).

### Dependencies
- No new runtime dependencies. RSS via stdlib `xml.etree.ElementTree`
  + `urllib.request`. Everything else already in v0.2/v0.6 deps.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs(v0.7): README sections for research/subscribes + CHANGELOG entry"
```

---

### Task 31: SKILL.md update for Claude awareness

**Files:**
- Modify: `SKILL.md` (or `skills/youtube_transcribe/SKILL.md` — wherever it lives)

The `SKILL.md` is what Claude Code reads when invoking the skill. It must describe the new commands so Claude can use them automatically when a user says "use the skill to research X".

- [ ] **Step 1: Find SKILL.md location**

Run: `find . -name "SKILL.md" -not -path "*/node_modules/*"`

Expected: one file (likely `SKILL.md` or under `skills/youtube_transcribe/`).

- [ ] **Step 2: Add v0.7 command sections to SKILL.md**

Open the SKILL.md file. After the existing sections describing `transcribe` / `batch` / `analyze` / `summarize`, add:

````markdown
## research (v0.7)

Use `research` when the user asks to "investigate", "find recent videos",
"do research", "make a digest", or any phrasing implying broad topical
discovery rather than a single known URL.

```bash
yt-tr research "<query>" --prompt "<analyze-prompt>"
```

Key options Claude should consider when constructing the command:
- `--days N` — default 30. Narrow to 7 for "this week", widen to 90+
  for "this quarter".
- `--languages ru,en` — default. Change if user wants single language.
- `--limit N` — default 20. Smaller for quick scans (10), bigger for
  comprehensive research (50).
- `--match "substring"` — for hard string filter.
- `--filter "phrase"` — for soft LLM-based filter when user says
  "only the ones about X".
- `--no-analyze` — when user just wants transcripts collected, no
  immediate summary.

## subscribes (v0.7)

Use `subscribes` when the user mentions "my channels", "the channels
I follow", "what's new from [author]", etc.

```bash
yt-tr subscribes add <channel-url>      # adding a new channel
yt-tr subscribes list                   # showing current list
yt-tr subscribes update --prompt "<…>"  # fetching new uploads
```

- `subscribes update` without `--days` etc. → incremental (since last
  run per channel). First-run for a channel needs `--days N` explicit.
- `--group <name>` — partition channels.
- `--filter "<…>"` — LLM pre-screening of new uploads (when 50+ new
  in a week and user wants just the relevant ones).

## history (v0.7)

```bash
yt-tr history list           # recent runs
yt-tr history show <run-id>  # full details for one
```

When user asks "what did I research last week" / "what's that batch
I made yesterday" — use this.
````

- [ ] **Step 3: Commit**

```bash
git add SKILL.md   # or skills/youtube_transcribe/SKILL.md
git commit -m "docs(v0.7): SKILL.md — describe research/subscribes/history for Claude"
```

---

### Task 32: Version bump + CI matrix + final release

**Files:**
- Modify: `pyproject.toml` (0.7.0-dev → 0.7.0)
- Modify: `skills/youtube_transcribe/__init__.py`
- Modify: `.github/workflows/test.yml` (add Python 3.13)

- [ ] **Step 1: Add Python 3.13 to CI matrix**

In `.github/workflows/test.yml`, change:

```yaml
matrix:
  os: [ubuntu-latest, macos-14, windows-latest]
  python: ["3.11", "3.12"]
```

To:

```yaml
matrix:
  os: [ubuntu-latest, macos-14, windows-latest]
  python: ["3.11", "3.12", "3.13"]
```

(Project's `requires-python = ">=3.11,<3.14"` already allows 3.13.)

- [ ] **Step 2: Drop `-dev` suffix**

`pyproject.toml`:
```toml
version = "0.7.0"
```

`skills/youtube_transcribe/__init__.py`:
```python
"""youtube-transcribe — universal transcription skill."""
__version__ = "0.7.0"
```

- [ ] **Step 3: Run full suite one last time**

Run: `uv run pytest --tb=no -q | grep -E "passed|failed"`
Expected: `1 failed, ~690 passed, 2 skipped` (1 = pre-existing webui).

- [ ] **Step 4: Smoke check the CLI is invokable**

Run: `uv run youtube-transcribe --version`
Expected: `youtube-transcribe, version 0.7.0`

Run: `uv run youtube-transcribe --help`
Expected: includes `research`, `subscribes`, `history` in the command list.

- [ ] **Step 5: Code-reviewer + security-review (per git-cross-os rule)**

Run mental review of the entire commit range:

```bash
git log --oneline feb83b7..HEAD
```

Expected: 30+ commits with `feat(v0.7)` / `test(v0.7)` / `refactor(v0.7)` / `docs(v0.7)` / `build(v0.7)`.

Check:
- No API keys hardcoded.
- No `shell=True` in subprocess.
- All file ops via `pathlib`.
- No `Co-Authored-By` in commit messages.
- `uv.lock` and `.python-version` not in any commit.

- [ ] **Step 6: Final release commit**

```bash
git add pyproject.toml skills/youtube_transcribe/__init__.py \
        .github/workflows/test.yml
git commit -m "$(cat <<'EOF'
release: v0.7.0 — research + subscribes

Two new commands sharing a common core pipeline:

- `research "query"` — broad topic discovery with multi-language search
  (LLM translation), date filter, optional substring/LLM pre-screen,
  TTY checkpoint, transcribe + analyze. Also supports cross-pollination
  via `--in-subscribes`.

- `subscribes` (add/remove/list/edit/update + schedule install/uninstall)
  — persistent channel tracking with stateful incremental updates.
  RSS-first discovery (~10× faster than yt-dlp scraping). Cross-OS
  scheduler snippet generation (cron/launchd/systemd/Task Scheduler).

- `history list/show` — persistent log of past research/subscribes runs.

- Web UI extensions: Research and Subscribes tabs.

Refactor: extracted _run_batch_pipeline from monolithic batch_cmd
so research/subscribes reuse it without duplication. v0.6 batch_cmd
behavior preserved byte-for-byte — all 614 v0.6 tests stay green.

CI matrix expanded to include Python 3.13 on Linux/macOS/Windows.

No new runtime dependencies. RSS uses stdlib xml.etree + urllib.
EOF
)"
```

- [ ] **Step 7: Optional — push to remote**

```bash
git push origin main
# or, if working on a branch:
# git push origin v0.7-research-subscribes
```

---

## Acceptance criteria — final shake-down

Manual TTY checks (after suite green):

- [ ] `yt-tr --version` → `0.7.0`.
- [ ] `yt-tr research --help` shows all 18+ options.
- [ ] `yt-tr research "Claude новинки" --days 7 --no-analyze --yes --backend subtitles`
      → выполняет search (с auto-translation на en), скачивает, транскрибирует.
- [ ] `yt-tr research "X" --in-subscribes --no-analyze --yes` (с пустым subscribes.toml)
      → friendly message «Нет каналов».
- [ ] `yt-tr subscribes add https://www.youtube.com/@AnthropicAI` → канал в TOML с channel_id.
- [ ] `yt-tr subscribes list` → таблица каналов.
- [ ] `yt-tr subscribes update --days 7 --no-analyze --yes --backend subtitles`
      → RSS discovery → транскрибация.
- [ ] `yt-tr subscribes update --no-analyze --yes --backend subtitles` (после первого update)
      → incremental, тянет только дельту.
- [ ] `yt-tr subscribes schedule install --every 1h --prompt "..."` (на Mac)
      → печатает launchd plist + инструкции.
- [ ] `yt-tr history list` → недавние runs.
- [ ] `yt-tr webui` → открывает Gradio, видны табы Research + Subscribes.

## Manual items requiring user action (collected at the end)

- **m1.** Real E2E test of `research` with real LLM (Gemini) — verify multi-language translation actually produces different queries for ru/en.
- **m2.** Real E2E test of `subscribes update` with RSS — verify it actually fetches a real channel feed.
- **m3.** Real install/run of generated launchd plist on macOS to verify the snippet is correct.
- **m4.** Interactive TTY checkpoint — Space/Enter/Ctrl-C in `questionary` (covered by mocks in unit tests).
- **m5.** Push to remote and verify CI matrix green on Linux/macOS/Windows × Python 3.11/3.12/3.13.

## Cross-OS notes (applies throughout)

- All file paths use `pathlib.Path`, never string concatenation with `/`.
- All subprocess calls use argv lists, never `shell=True`.
- `EDITOR` fallback in `subscribes edit`: $EDITOR env var → `vi` (Unix) / `notepad` (Windows).
- RSS fetch uses stdlib `urllib.request` with explicit User-Agent.
- launchd / systemd / cron / Windows Task Scheduler snippet generators tested on all platforms via CI matrix.

