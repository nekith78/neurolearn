# youtube-transcribe v0.6 — `analyze` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить standalone-команду `youtube-transcribe analyze`, которая упаковывает один или несколько уже готовых транскриптов вместе с произвольным prompt'ом пользователя и отправляет в выбранный LLM (gemini/claude/openai/ollama), возвращая ответ в файл и в stdout.

**Architecture:** Новый пакет `skills/youtube_transcribe/analyze/` с пятью маленькими модулями: `select_parser` → `source_resolver` → `prompt_builder` → `runner` → `output_writer`, плюс TTY-only `picker.py` поверх `questionary`. LLM-вызовы переиспользуют уже существующие `_call_*` из `quality/asr_corrector.py` — никаких новых SDK-обёрток. Существующий `summarize` рефакторится в тонкий wrapper над `analyze.runner` с захардкоженым summary-промптом.

**Tech Stack:** Python 3.11+, uv, Click 8, Rich, questionary≥2.0 (новая dep), существующие google-genai / anthropic / openai / urllib (ollama). Никаких новых SDK.

**Spec:** `docs/specs/2026-05-11-youtube-transcribe-v06-analyze-design.md` (commit cbef1fc).

---

## Структура файлов

```
youtube-transcribe/
├── pyproject.toml                                       ← Task 1 (+questionary, version)
├── skills/youtube_transcribe/
│   ├── __init__.py                                      ← Task 1 (version bump)
│   ├── transcribe.py                                    ← Tasks 9, 10, 11, 12, 13
│   ├── quality/
│   │   └── summarizer.py                                ← Task 12 (thin wrapper)
│   ├── utils/
│   │   └── transcript_loader.py                         ← (reused as-is)
│   └── analyze/                                         ← NEW package
│       ├── __init__.py                                  ← Task 2
│       ├── select_parser.py                             ← Task 3
│       ├── source_resolver.py                           ← Task 4
│       ├── prompt_builder.py                            ← Task 5
│       ├── runner.py                                    ← Task 6
│       ├── output_writer.py                             ← Task 7
│       └── picker.py                                    ← Task 8
└── tests/
    ├── test_analyze_select_parser.py                    ← Task 3
    ├── test_analyze_source_resolver.py                  ← Task 4
    ├── test_analyze_prompt_builder.py                   ← Task 5
    ├── test_analyze_runner.py                           ← Task 6
    ├── test_analyze_output.py                           ← Task 7
    ├── test_cli_analyze.py                              ← Tasks 9, 10, 11
    ├── test_summarize_uses_analyze.py                   ← Task 12
    └── test_cli_summarize.py                            ← (must remain green)
```

## Phases

- **Phase 1 (Tasks 1–2):** Bootstrap — dep, version bump, scaffolding.
- **Phase 2 (Tasks 3–6):** Pure logic, no I/O — select parser, source resolver, prompt builder, runner.
- **Phase 3 (Task 7):** Output writer (analysis-*.md + append).
- **Phase 4 (Task 8):** Interactive picker (questionary, TTY-gated).
- **Phase 5 (Tasks 9–11):** CLI `analyze_cmd` — skeleton, batch-sources, picker + append + stdout polish.
- **Phase 6 (Task 12):** Refactor `summarize_cmd` в тонкий wrapper над runner.
- **Phase 7 (Task 13):** `batch_cmd --then-analyze` integration.
- **Phase 8 (Tasks 14–15):** README/CHANGELOG, release prep, security/code review, v0.6.0 commit.

---

## Pre-flight (один раз перед началом)

- [ ] Убедиться что v0.5.2 в working state и все тесты зелёные:

  Run: `git log --oneline -3`
  Expected: видны коммиты `752251d` (v0.5.2) или новее.

  Run: `uv run pytest -q`
  Expected: 544 passed (или больше).

- [ ] Опционально создать ветку для v0.6:

  ```bash
  git checkout -b v0.6-analyze
  ```

  Альтернатива — работа в `main` (стиль проекта greenfield).

---

# Phase 1 — Bootstrap v0.6

### Task 1: pyproject.toml + version bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `skills/youtube_transcribe/__init__.py`

- [ ] **Step 1: Bump version в `pyproject.toml`**

В `[project] version` изменить:

```toml
version = "0.6.0-dev"
```

- [ ] **Step 2: Добавить `questionary` в core dependencies**

В блок `[project] dependencies` после `"tomlkit>=0.13.0",` добавить:

```toml
    # === v0.6: interactive picker for `analyze` command ===
    "questionary>=2.0",
```

- [ ] **Step 3: Bump version в `__init__.py`**

`skills/youtube_transcribe/__init__.py`:

```python
"""youtube-transcribe — universal transcription skill."""
__version__ = "0.6.0-dev"
```

- [ ] **Step 4: Установить новую dep**

Run: `uv sync --extra dev`
Expected: `questionary` ставится, остальное без изменений.

- [ ] **Step 5: Проверить импорт**

Run: `uv run python -c "import questionary; print(questionary.__version__)"`
Expected: версия `2.x`.

- [ ] **Step 6: Запустить существующие тесты, убедиться что ничего не сломалось**

Run: `uv run pytest -q`
Expected: 544 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml skills/youtube_transcribe/__init__.py
git commit -m "$(cat <<'EOF'
build(v0.6): bump to 0.6.0-dev, add questionary dep

questionary>=2.0 powers the interactive checkbox picker in the new
`analyze` sub-command (TTY-gated; non-TTY falls back to flag-driven
selection).
EOF
)"
```

---

### Task 2: Scaffold `analyze/` package

**Files:**
- Create: `skills/youtube_transcribe/analyze/__init__.py`
- Create: `tests/test_analyze_scaffolding.py`

- [ ] **Step 1: Создать пакет**

```bash
mkdir -p skills/youtube_transcribe/analyze
```

Содержимое `skills/youtube_transcribe/analyze/__init__.py`:

```python
"""analyze — bridge to external LLMs for free-form analysis of transcripts (v0.6)."""
```

- [ ] **Step 2: Написать smoke-тест**

`tests/test_analyze_scaffolding.py`:

```python
"""Smoke test: analyze module skeleton exists and imports cleanly."""


def test_analyze_module_imports():
    import skills.youtube_transcribe.analyze  # noqa: F401


def test_version_is_v06():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.6.")
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_analyze_scaffolding.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add skills/youtube_transcribe/analyze/__init__.py tests/test_analyze_scaffolding.py
git commit -m "feat(v0.6): scaffold analyze/ package"
```

---

# Phase 2 — Pure logic (no I/O)

### Task 3: select_parser.py — `"1,3,5-7"` → indices

**Files:**
- Create: `skills/youtube_transcribe/analyze/select_parser.py`
- Create: `tests/test_analyze_select_parser.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_analyze_select_parser.py`:

```python
"""Tests for analyze.select_parser — parse 1-based comma/range strings."""
import pytest

from skills.youtube_transcribe.analyze.select_parser import parse_select


def test_single_index():
    assert parse_select("3", total=10) == [2]


def test_comma_separated():
    assert parse_select("1,3,5", total=10) == [0, 2, 4]


def test_range():
    assert parse_select("2-5", total=10) == [1, 2, 3, 4]


def test_mixed():
    assert parse_select("1,3,5-7", total=10) == [0, 2, 4, 5, 6]


def test_dedups_and_sorts():
    assert parse_select("5,3,5,3-4", total=10) == [2, 3, 4]


def test_whitespace_tolerant():
    assert parse_select(" 1 , 3 - 5 ", total=10) == [0, 2, 3, 4]


def test_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_select("", total=10)


def test_zero_raises():
    with pytest.raises(ValueError, match="1-based"):
        parse_select("0", total=10)


def test_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        parse_select("1,15", total=10)


def test_reverse_range_raises():
    with pytest.raises(ValueError, match="invalid range"):
        parse_select("5-3", total=10)


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_select("abc", total=10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analyze_select_parser.py -v`
Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `select_parser.py`**

`skills/youtube_transcribe/analyze/select_parser.py`:

```python
"""Parse `--select` strings like `"1,3,5-7"` to 0-based index lists."""
from __future__ import annotations


def parse_select(spec: str, *, total: int) -> list[int]:
    """Parse 1-based selection string, return sorted 0-based unique indices.

    Format: comma-separated tokens, each either `N` or `A-B`.
    Raises ValueError on empty input, 0 / negative index, out-of-range
    index, reverse range (`5-3`), or garbage tokens.
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("empty selection string")

    indices: set[int] = set()
    for raw_token in spec.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if "-" in token:
            a_str, b_str = (p.strip() for p in token.split("-", 1))
            try:
                a, b = int(a_str), int(b_str)
            except ValueError as e:
                raise ValueError(f"bad range token: {token!r}") from e
            if a > b:
                raise ValueError(f"invalid range (reverse): {token!r}")
            for n in range(a, b + 1):
                _add_one_based(indices, n, total)
        else:
            try:
                n = int(token)
            except ValueError as e:
                raise ValueError(f"bad token: {token!r}") from e
            _add_one_based(indices, n, total)

    if not indices:
        raise ValueError("empty selection string")
    return sorted(indices)


def _add_one_based(acc: set[int], n: int, total: int) -> None:
    if n < 1:
        raise ValueError(f"indices are 1-based, got {n}")
    if n > total:
        raise ValueError(f"index {n} out of range (have {total})")
    acc.add(n - 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_analyze_select_parser.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/analyze/select_parser.py \
        tests/test_analyze_select_parser.py
git commit -m "feat(v0.6): analyze.select_parser — '1,3,5-7' to 0-based indices"
```

---

### Task 4: source_resolver.py — SOURCE → list of transcripts

**Files:**
- Create: `skills/youtube_transcribe/analyze/source_resolver.py`
- Create: `tests/test_analyze_source_resolver.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_analyze_source_resolver.py`:

```python
"""Tests for analyze.source_resolver — path/batch/--latest → VideoSource list."""
import json
import time
from pathlib import Path

import pytest

from skills.youtube_transcribe.analyze.source_resolver import (
    VideoSource,
    resolve_source,
    pick_latest_batch,
)


def _write_manifest(folder: Path, videos: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(
        json.dumps({
            "batch_name": folder.name,
            "created_at": "2026-05-11T14:42:00",
            "stats": {"total": len(videos), "ok": len(videos), "failed": 0},
            "videos": videos,
        }),
        encoding="utf-8",
    )


def test_single_txt_file(tmp_path: Path):
    f = tmp_path / "video.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    out = resolve_source(f, outputs_dir=tmp_path, latest=False)
    assert len(out) == 1
    assert out[0].transcript_path == f
    assert out[0].title is None


def test_single_json_file(tmp_path: Path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "hi"}]}),
                 encoding="utf-8")
    out = resolve_source(f, outputs_dir=tmp_path, latest=False)
    assert len(out) == 1
    assert out[0].transcript_path == f


def test_batch_folder_with_manifest(tmp_path: Path):
    batch = tmp_path / "batch_001"
    (batch / "vid.txt").parent.mkdir(parents=True, exist_ok=True)
    (batch / "vid.txt").write_text("[00:00:00.000 --> 00:00:01.000] hi\n",
                                   encoding="utf-8")
    _write_manifest(batch, [{
        "index": 1, "url": "https://youtu.be/x", "video_id": "x",
        "title": "Hello world", "upload_date": "2026-05-09",
        "duration_sec": 222, "channel": "ch", "language_detected": "en",
        "files": {"txt": "vid.txt"}, "status": "ok",
    }])
    out = resolve_source(batch, outputs_dir=tmp_path, latest=False)
    assert len(out) == 1
    assert out[0].title == "Hello world"
    assert out[0].upload_date == "2026-05-09"
    assert out[0].duration_sec == 222
    assert out[0].language == "en"
    assert out[0].url == "https://youtu.be/x"
    assert out[0].transcript_path == batch / "vid.txt"


def test_batch_folder_without_manifest(tmp_path: Path):
    folder = tmp_path / "loose"
    folder.mkdir()
    (folder / "a.txt").write_text("[00:00:00.000 --> 00:00:01.000] a\n",
                                  encoding="utf-8")
    (folder / "b.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nb\n", encoding="utf-8")
    out = resolve_source(folder, outputs_dir=tmp_path, latest=False)
    assert len(out) == 2
    names = sorted(v.transcript_path.name for v in out)
    assert names == ["a.txt", "b.srt"]
    assert all(v.title is None for v in out)


def test_missing_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_source(tmp_path / "nope", outputs_dir=tmp_path, latest=False)


def test_pick_latest_batch(tmp_path: Path):
    older = tmp_path / "b1"
    newer = tmp_path / "b2"
    older.mkdir()
    newer.mkdir()
    (older / "manifest.json").write_text("{}", encoding="utf-8")
    (newer / "manifest.json").write_text("{}", encoding="utf-8")
    # bump newer's mtime
    later = time.time() + 60
    import os
    os.utime(newer, (later, later))
    assert pick_latest_batch(tmp_path) == newer


def test_pick_latest_batch_empty(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="no batches"):
        pick_latest_batch(tmp_path)


def test_latest_flag_uses_pick(tmp_path: Path):
    b = tmp_path / "the_only_batch"
    (b / "vid.txt").parent.mkdir(parents=True, exist_ok=True)
    (b / "vid.txt").write_text("[00:00:00.000 --> 00:00:01.000] x\n",
                               encoding="utf-8")
    _write_manifest(b, [{
        "index": 1, "url": None, "video_id": None,
        "title": "T", "upload_date": None, "duration_sec": None,
        "channel": None, "language_detected": None,
        "files": {"txt": "vid.txt"}, "status": "ok",
    }])
    out = resolve_source(None, outputs_dir=tmp_path, latest=True)
    assert len(out) == 1
    assert out[0].title == "T"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_analyze_source_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `source_resolver.py`**

`skills/youtube_transcribe/analyze/source_resolver.py`:

```python
"""Resolve `analyze` SOURCE argument into a list of transcript files.

SOURCE может быть:
 - путь к файлу (.txt/.json/.srt) → один VideoSource без metadata
 - путь к папке с manifest.json → videos из manifest
 - путь к папке без manifest → все *.txt/*.json/*.srt отсортированные
 - None + latest=True → берём свежайшую подпапку с manifest.json
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

_TRANSCRIPT_EXTS = {".txt", ".json", ".srt"}


@dataclass
class VideoSource:
    """Один транскрипт + метаданные (если есть)."""
    transcript_path: Path
    title: str | None = None
    upload_date: str | None = None   # ISO YYYY-MM-DD
    duration_sec: int | None = None
    language: str | None = None
    url: str | None = None


def resolve_source(
    source: Path | None,
    *,
    outputs_dir: Path,
    latest: bool,
) -> list[VideoSource]:
    """Return list of VideoSource based on SOURCE / --latest.

    Raises FileNotFoundError if SOURCE doesn't exist or no batches found.
    Returns empty list if folder has no transcripts.
    """
    if source is None:
        if not latest:
            raise FileNotFoundError(
                "no SOURCE and --latest not set — cannot resolve"
            )
        source = pick_latest_batch(outputs_dir)

    if not source.exists():
        raise FileNotFoundError(f"SOURCE does not exist: {source}")

    if source.is_file():
        return [VideoSource(transcript_path=source)]

    manifest = source / "manifest.json"
    if manifest.exists():
        return _from_manifest(source, manifest)

    # Folder without manifest — pick up loose transcripts.
    files = sorted(
        p for p in source.iterdir()
        if p.is_file() and p.suffix.lower() in _TRANSCRIPT_EXTS
    )
    return [VideoSource(transcript_path=p) for p in files]


def pick_latest_batch(outputs_dir: Path) -> Path:
    """Return the most-recently-modified subdir containing manifest.json."""
    if not outputs_dir.exists():
        raise FileNotFoundError(f"outputs dir does not exist: {outputs_dir}")
    candidates = [
        p for p in outputs_dir.iterdir()
        if p.is_dir() and (p / "manifest.json").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"no batches with manifest.json in {outputs_dir}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _from_manifest(batch_dir: Path, manifest: Path) -> list[VideoSource]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    out: list[VideoSource] = []
    for v in data.get("videos") or []:
        if v.get("status") != "ok":
            continue
        files = v.get("files") or {}
        # Prefer .txt, fall back to .json, then .srt.
        rel = files.get("txt") or files.get("json") or files.get("srt")
        if not rel:
            continue
        path = batch_dir / rel
        if not path.exists():
            continue
        out.append(VideoSource(
            transcript_path=path,
            title=v.get("title"),
            upload_date=v.get("upload_date"),
            duration_sec=v.get("duration_sec"),
            language=v.get("language_detected"),
            url=v.get("url"),
        ))
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_analyze_source_resolver.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/analyze/source_resolver.py \
        tests/test_analyze_source_resolver.py
git commit -m "feat(v0.6): analyze.source_resolver — SOURCE → VideoSource list"
```

---

### Task 5: prompt_builder.py — final prompt assembly

**Files:**
- Create: `skills/youtube_transcribe/analyze/prompt_builder.py`
- Create: `tests/test_analyze_prompt_builder.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_analyze_prompt_builder.py`:

```python
"""Tests for analyze.prompt_builder."""
import json
from pathlib import Path

from skills.youtube_transcribe.analyze.prompt_builder import (
    SYSTEM_PROMPT,
    build_prompt,
)
from skills.youtube_transcribe.analyze.source_resolver import VideoSource


def test_system_prompt_is_neutral():
    assert "assistant" in SYSTEM_PROMPT.lower()
    assert "transcript" in SYSTEM_PROMPT.lower()


def test_user_prompt_appears_verbatim(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="WHAT IS THIS ABOUT?",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "WHAT IS THIS ABOUT?" in out
    assert SYSTEM_PROMPT in out


def test_per_video_section_with_metadata(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(
            transcript_path=f,
            title="Cool Talk",
            upload_date="2026-05-09",
            duration_sec=222,
            language="en",
            url="https://youtu.be/abc",
        )],
    )
    assert "[1] Cool Talk" in out
    assert "2026-05-09" in out
    assert "en" in out
    assert "https://youtu.be/abc" in out
    assert "hi" in out


def test_fallback_to_filename_without_manifest(tmp_path: Path):
    f = tmp_path / "video-no-meta.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] x\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "video-no-meta" in out


def test_multiple_videos_get_indexed(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("[00:00:00.000 --> 00:00:01.000] aaa\n", encoding="utf-8")
    b.write_text("[00:00:00.000 --> 00:00:01.000] bbb\n", encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[
            VideoSource(transcript_path=a, title="A"),
            VideoSource(transcript_path=b, title="B"),
        ],
    )
    assert "[1] A" in out
    assert "[2] B" in out


def test_truncation_at_max_chars(tmp_path: Path):
    long_txt = "[00:00:00.000 --> 00:00:01.000] " + ("x" * 5000) + "\n"
    f = tmp_path / "long.txt"
    f.write_text(long_txt, encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
        max_chars=200,
    )
    assert "[...truncated...]" in out


def test_json_transcript_format(tmp_path: Path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello json"}],
    }), encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "hello json" in out


def test_srt_transcript_format(tmp_path: Path):
    f = tmp_path / "t.srt"
    f.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello srt\n",
                 encoding="utf-8")
    out = build_prompt(
        user_prompt="P",
        videos=[VideoSource(transcript_path=f)],
    )
    assert "hello srt" in out


def test_unreadable_file_silently_skipped(tmp_path: Path):
    """If one file fails to load — keep going, others should appear."""
    good = tmp_path / "good.txt"
    good.write_text("[00:00:00.000 --> 00:00:01.000] g\n", encoding="utf-8")
    missing = tmp_path / "gone.txt"  # never created
    out = build_prompt(
        user_prompt="P",
        videos=[
            VideoSource(transcript_path=missing, title="MISSING"),
            VideoSource(transcript_path=good, title="GOOD"),
        ],
    )
    assert "GOOD" in out
    assert "g" in out
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_analyze_prompt_builder.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `prompt_builder.py`**

`skills/youtube_transcribe/analyze/prompt_builder.py`:

```python
"""Build the final prompt sent to the LLM for `analyze`.

Concatenates a neutral system instruction, the user's free-form prompt,
and a numbered list of transcript sections with metadata headers.
"""
from __future__ import annotations

from pathlib import Path

from skills.youtube_transcribe.analyze.source_resolver import VideoSource
from skills.youtube_transcribe.utils.transcript_loader import (
    load_transcript_segments,
)
from skills.youtube_transcribe.utils.output_writer import Segment


SYSTEM_PROMPT = (
    "You are an assistant that answers user questions about the content "
    "of the provided video transcripts. Reply in the language of the "
    "user query."
)


def build_prompt(
    user_prompt: str,
    videos: list[VideoSource],
    *,
    max_chars: int = 60_000,
) -> str:
    """Render the full prompt string.

    Layout:
        {SYSTEM_PROMPT}

        {user_prompt}

        ---
        Транскрипты:

        ### [1] {title} ({date}, {duration}, {lang})
        Source: {url}

        {body}

        ---

        ### [2] ...

    Bodies are read from disk via transcript_loader. Each body is
    soft-truncated at `max_chars` with a `[...truncated...]` marker.
    Unreadable files contribute a `(failed to load)` placeholder so the
    LLM still sees the rest of the batch.
    """
    parts = [SYSTEM_PROMPT, "", user_prompt, "", "---", "Транскрипты:", ""]

    for idx, v in enumerate(videos, start=1):
        parts.append(_video_header(idx, v))
        parts.append("")
        parts.append(_video_body(v, max_chars))
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _video_header(idx: int, v: VideoSource) -> str:
    title = v.title or v.transcript_path.stem
    bits: list[str] = []
    if v.upload_date:
        bits.append(v.upload_date)
    if v.duration_sec is not None:
        bits.append(_fmt_duration(v.duration_sec))
    if v.language:
        bits.append(v.language)
    suffix = f" ({', '.join(bits)})" if bits else ""
    head = f"### [{idx}] {title}{suffix}"
    if v.url:
        head += f"\nSource: {v.url}"
    return head


def _fmt_duration(sec: int) -> str:
    mm, ss = divmod(sec, 60)
    hh, mm = divmod(mm, 60)
    return f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"


def _video_body(v: VideoSource, max_chars: int) -> str:
    """Read transcript from disk and format. Truncate at max_chars."""
    try:
        segs, _ = load_transcript_segments(v.transcript_path)
    except Exception as e:
        return f"(failed to load {v.transcript_path.name}: {e})"

    if not segs:
        return "(empty transcript)"

    # If the original .txt has time-prefixed lines, prefer those as-is.
    if v.transcript_path.suffix.lower() == ".txt":
        raw = v.transcript_path.read_text(encoding="utf-8")
        return _truncate(raw, max_chars)

    return _truncate(_format_segments(segs), max_chars)


def _format_segments(segs: list[Segment]) -> str:
    lines = []
    for s in segs:
        h = int(s.start // 3600)
        m = int((s.start % 3600) // 60)
        sec = int(s.start % 60)
        lines.append(f"[{h:02d}:{m:02d}:{sec:02d}] {s.text.strip()}")
    return "\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n[...truncated...]"
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_analyze_prompt_builder.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/analyze/prompt_builder.py \
        tests/test_analyze_prompt_builder.py
git commit -m "feat(v0.6): analyze.prompt_builder — system+user+transcripts assembly"
```

---

### Task 6: runner.py — wrap existing _call_* LLM functions

**Files:**
- Create: `skills/youtube_transcribe/analyze/runner.py`
- Create: `tests/test_analyze_runner.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_analyze_runner.py`:

```python
"""Tests for analyze.runner — wrap _call_* LLM funcs."""
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.analyze.runner import run_analysis


def test_gemini_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        return_value="ANSWER",
    ) as mock:
        out = run_analysis("PROMPT", backend="gemini", api_key="sk-abc")
    mock.assert_called_once_with("PROMPT", "sk-abc")
    assert out == "ANSWER"


def test_claude_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_claude",
        return_value="A",
    ) as mock:
        out = run_analysis("P", backend="claude", api_key="key")
    mock.assert_called_once_with("P", "key")
    assert out == "A"


def test_openai_called_with_prompt():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_openai",
        return_value="A",
    ) as mock:
        out = run_analysis("P", backend="openai", api_key="key")
    mock.assert_called_once_with("P", "key")
    assert out == "A"


def test_ollama_passes_model_and_host():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_ollama",
        return_value="A",
    ) as mock:
        out = run_analysis(
            "P", backend="ollama", api_key=None,
            ollama_model="qwen2:7b",
            ollama_host="http://example:11434",
        )
    mock.assert_called_once_with(
        "P", model="qwen2:7b", host="http://example:11434",
    )
    assert out == "A"


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown backend"):
        run_analysis("P", backend="bogus", api_key="x")


def test_exception_returns_empty():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        side_effect=RuntimeError("boom"),
    ):
        out = run_analysis("P", backend="gemini", api_key="key")
    assert out == ""


def test_empty_response_returned_as_is():
    with patch(
        "skills.youtube_transcribe.analyze.runner._call_gemini",
        return_value="",
    ):
        out = run_analysis("P", backend="gemini", api_key="k")
    assert out == ""
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_analyze_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `runner.py`**

`skills/youtube_transcribe/analyze/runner.py`:

```python
"""Send a fully-built prompt to one of the four LLM backends.

Thin wrapper over the existing _call_* helpers in quality/asr_corrector.py.
No retries; on exception returns empty string so the CLI layer can
translate that into exit code 4 with a friendly hint.
"""
from __future__ import annotations

from skills.youtube_transcribe.quality.asr_corrector import (
    _call_claude, _call_gemini, _call_ollama, _call_openai,
)

_KNOWN = {"gemini", "claude", "openai", "ollama"}


def run_analysis(
    full_prompt: str,
    *,
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Return LLM response text, or "" on failure / empty response."""
    if backend not in _KNOWN:
        raise ValueError(f"unknown backend: {backend!r}")

    try:
        if backend == "gemini":
            return _call_gemini(full_prompt, api_key or "")
        if backend == "claude":
            return _call_claude(full_prompt, api_key or "")
        if backend == "openai":
            return _call_openai(full_prompt, api_key or "")
        if backend == "ollama":
            return _call_ollama(
                full_prompt, model=ollama_model, host=ollama_host,
            )
    except Exception:
        return ""
    return ""
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_analyze_runner.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/analyze/runner.py \
        tests/test_analyze_runner.py
git commit -m "feat(v0.6): analyze.runner — thin wrapper over _call_* LLM helpers"
```

---

# Phase 3 — Output writer

### Task 7: analyze/output_writer.py — write/append analysis-*.md

**Files:**
- Create: `skills/youtube_transcribe/analyze/output_writer.py`
- Create: `tests/test_analyze_output.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_analyze_output.py`:

```python
"""Tests for analyze.output_writer — analysis-*.md writer + --append-to."""
from datetime import datetime
from pathlib import Path

from skills.youtube_transcribe.analyze.output_writer import (
    analysis_filename,
    write_analysis,
    append_analysis,
)
from skills.youtube_transcribe.analyze.source_resolver import VideoSource


def _src(title: str) -> VideoSource:
    return VideoSource(transcript_path=Path("/tmp") / f"{title}.txt", title=title)


def test_filename_pattern():
    t = datetime(2026, 5, 11, 14, 42)
    assert analysis_filename(t) == "analysis-2026-05-11-1442.md"


def test_write_new_file(tmp_path: Path):
    out = write_analysis(
        out_path=tmp_path / "analysis-2026-05-11-1442.md",
        body="HELLO WORLD",
        user_prompt="What was discussed?",
        backend_label="gemini (gemini-2.5-flash)",
        videos=[_src("V1"), _src("V2")],
        total_videos=5,
        now=datetime(2026, 5, 11, 14, 42),
    )
    txt = out.read_text(encoding="utf-8")
    assert txt.startswith("# Analysis — 2026-05-11 14:42")
    assert "gemini (gemini-2.5-flash)" in txt
    assert "**Videos:** 2 of 5" in txt
    assert "- V1" in txt
    assert "- V2" in txt
    assert "What was discussed?" in txt
    assert "HELLO WORLD" in txt


def test_write_truncates_long_prompt_quote(tmp_path: Path):
    long = "x" * 1000
    out = write_analysis(
        out_path=tmp_path / "a.md",
        body="B",
        user_prompt=long,
        backend_label="gemini",
        videos=[_src("V")],
        total_videos=1,
        now=datetime(2026, 5, 11, 14, 42),
    )
    txt = out.read_text(encoding="utf-8")
    # Quote section should not include the entire 1000-char string.
    assert "..." in txt
    assert "x" * 1000 not in txt


def test_write_collision_appends_suffix(tmp_path: Path):
    target = tmp_path / "analysis-2026-05-11-1442.md"
    target.write_text("existing", encoding="utf-8")
    out = write_analysis(
        out_path=target,
        body="NEW",
        user_prompt="P",
        backend_label="gemini",
        videos=[_src("V")],
        total_videos=1,
        now=datetime(2026, 5, 11, 14, 42),
    )
    assert out.name == "analysis-2026-05-11-1442-2.md"
    assert out.read_text(encoding="utf-8").endswith("NEW\n") or "NEW" in out.read_text("utf-8")


def test_append_creates_new_file_with_header(tmp_path: Path):
    target = tmp_path / "combined.md"
    out = append_analysis(
        target=target,
        body="FIRST",
        user_prompt="P",
        backend_label="gemini",
        videos=[_src("V")],
        total_videos=1,
        now=datetime(2026, 5, 11, 14, 42),
    )
    txt = out.read_text(encoding="utf-8")
    assert txt.startswith("# Combined analyses")
    assert "## Analysis — 2026-05-11 14:42" in txt
    assert "FIRST" in txt


def test_append_to_existing_file(tmp_path: Path):
    target = tmp_path / "combined.md"
    target.write_text(
        "# Combined analyses\n\n## Analysis — 2026-05-10 10:00\n\nOLD\n",
        encoding="utf-8",
    )
    append_analysis(
        target=target,
        body="NEW",
        user_prompt="P",
        backend_label="gemini",
        videos=[_src("V")],
        total_videos=1,
        now=datetime(2026, 5, 11, 14, 42),
    )
    txt = target.read_text(encoding="utf-8")
    assert txt.count("## Analysis — ") == 2
    assert "OLD" in txt
    assert "NEW" in txt
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_analyze_output.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `analyze/output_writer.py`**

`skills/youtube_transcribe/analyze/output_writer.py`:

```python
"""Write `analysis-*.md` files for the `analyze` sub-command."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from skills.youtube_transcribe.analyze.source_resolver import VideoSource

_PROMPT_QUOTE_MAX = 200


def analysis_filename(now: datetime) -> str:
    """Default `analysis-YYYY-MM-DD-HHMM.md` filename."""
    return f"analysis-{now:%Y-%m-%d-%H%M}.md"


def write_analysis(
    *,
    out_path: Path,
    body: str,
    user_prompt: str,
    backend_label: str,
    videos: list[VideoSource],
    total_videos: int,
    now: datetime,
) -> Path:
    """Write a fresh analysis file. Resolves filename collisions with `-N`."""
    out_path = _resolve_collision(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _render_block(
            heading=f"# Analysis — {now:%Y-%m-%d %H:%M}",
            body=body,
            user_prompt=user_prompt,
            backend_label=backend_label,
            videos=videos,
            total_videos=total_videos,
        ),
        encoding="utf-8",
    )
    return out_path


def append_analysis(
    *,
    target: Path,
    body: str,
    user_prompt: str,
    backend_label: str,
    videos: list[VideoSource],
    total_videos: int,
    now: datetime,
) -> Path:
    """Append a block to `target`. Creates with `# Combined analyses` if new."""
    target.parent.mkdir(parents=True, exist_ok=True)
    block = _render_block(
        heading=f"## Analysis — {now:%Y-%m-%d %H:%M}",
        body=body,
        user_prompt=user_prompt,
        backend_label=backend_label,
        videos=videos,
        total_videos=total_videos,
    )
    if target.exists():
        with target.open("a", encoding="utf-8") as f:
            f.write("\n")
            f.write(block)
    else:
        target.write_text(
            "# Combined analyses\n\n" + block,
            encoding="utf-8",
        )
    return target


def _resolve_collision(path: Path) -> Path:
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    for n in range(2, 1000):
        candidate = path.with_name(f"{stem}-{n}{ext}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"too many collisions for {path}")


def _render_block(
    *,
    heading: str,
    body: str,
    user_prompt: str,
    backend_label: str,
    videos: list[VideoSource],
    total_videos: int,
) -> str:
    quote = user_prompt.strip().splitlines()
    quote_text = " ".join(quote)
    if len(quote_text) > _PROMPT_QUOTE_MAX:
        quote_text = quote_text[:_PROMPT_QUOTE_MAX].rstrip() + "..."
    titles_lines = "\n".join(
        f"- {v.title or v.transcript_path.stem}" for v in videos
    )
    return (
        f"{heading}\n\n"
        f"**Backend:** {backend_label}\n"
        f"**Videos:** {len(videos)} of {total_videos}\n"
        f"{titles_lines}\n\n"
        f"**Prompt:**\n> {quote_text}\n\n"
        f"---\n\n"
        f"{body.rstrip()}\n"
    )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_analyze_output.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/analyze/output_writer.py \
        tests/test_analyze_output.py
git commit -m "feat(v0.6): analyze.output_writer — analysis-*.md + --append-to"
```

---

# Phase 4 — Interactive picker

### Task 8: picker.py — questionary checkbox UI

**Files:**
- Create: `skills/youtube_transcribe/analyze/picker.py`

This module is **not unit-tested directly** (TTY-only, depends on terminal state). It's exercised through mocks in CLI tests. Manual smoke test is part of acceptance criteria.

- [ ] **Step 1: Implement `picker.py`**

`skills/youtube_transcribe/analyze/picker.py`:

```python
"""Interactive selection of batch + videos via questionary.

TTY-gated. Caller is expected to check sys.stdin.isatty() before calling.
"""
from __future__ import annotations

from pathlib import Path

from skills.youtube_transcribe.analyze.source_resolver import (
    VideoSource,
    pick_latest_batch,
)


class PickerCancelled(Exception):
    """User hit Ctrl-C / esc in the picker."""


def pick_batch(outputs_dir: Path) -> Path:
    """Single-select picker over subfolders containing manifest.json.

    Newest first. Raises PickerCancelled if user aborts.
    Raises FileNotFoundError if no batches exist.
    """
    import questionary
    import json

    candidates = sorted(
        (p for p in outputs_dir.iterdir()
         if p.is_dir() and (p / "manifest.json").exists()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no batches with manifest.json in {outputs_dir}")

    choices = []
    for b in candidates:
        try:
            meta = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
            stats = meta.get("stats", {})
            ok = stats.get("ok", "?")
            total = stats.get("total", "?")
            backend = meta.get("config", {}).get("backend", "?")
            label = f"{b.name}  {ok}/{total} ok  {backend}"
        except Exception:
            label = b.name
        choices.append(questionary.Choice(title=label, value=str(b)))

    answer = questionary.select(
        "Выбери batch:", choices=choices,
    ).ask()
    if answer is None:
        raise PickerCancelled()
    return Path(answer)


def pick_videos(videos: list[VideoSource]) -> list[VideoSource]:
    """Multi-select checkbox over videos. Returns chosen subset.

    Raises PickerCancelled if user aborts.
    """
    import questionary

    if not videos:
        return []

    choices = []
    for i, v in enumerate(videos, start=1):
        title = v.title or v.transcript_path.stem
        title = title if len(title) <= 60 else title[:57] + "..."
        date = v.upload_date or "—"
        dur = _fmt_duration(v.duration_sec)
        label = f"{date}  {dur:>6}  {title}"
        choices.append(questionary.Choice(title=label, value=i - 1, checked=True))

    answer = questionary.checkbox(
        "Выбери видео для анализа (Space=toggle, Enter=ok):",
        choices=choices,
    ).ask()
    if answer is None:
        raise PickerCancelled()
    return [videos[i] for i in answer]


def _fmt_duration(sec: int | None) -> str:
    if sec is None:
        return "—"
    mm, ss = divmod(sec, 60)
    hh, mm = divmod(mm, 60)
    return f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"


__all__ = ["pick_batch", "pick_videos", "PickerCancelled"]
```

- [ ] **Step 2: Smoke-import test (catches typos / missing imports)**

`tests/test_analyze_scaffolding.py` — добавить тест в существующий файл (рядом с уже добавленным `test_analyze_module_imports`):

```python
def test_picker_imports():
    """Picker module imports cleanly even outside a TTY."""
    from skills.youtube_transcribe.analyze import picker
    assert hasattr(picker, "pick_batch")
    assert hasattr(picker, "pick_videos")
    assert hasattr(picker, "PickerCancelled")
```

Run: `uv run pytest tests/test_analyze_scaffolding.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add skills/youtube_transcribe/analyze/picker.py \
        tests/test_analyze_scaffolding.py
git commit -m "feat(v0.6): analyze.picker — questionary-based interactive UI"
```

---

# Phase 5 — CLI command

### Task 9: analyze_cmd — skeleton + single-file + --all path

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py` (add `analyze_cmd`)
- Create: `tests/test_cli_analyze.py`

- [ ] **Step 1: Написать failing tests**

`tests/test_cli_analyze.py`:

```python
"""Tests for `youtube-transcribe analyze` CLI."""
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def test_analyze_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["analyze", "--help"])
    assert res.exit_code == 0
    assert "--prompt" in res.output
    assert "--prompt-file" in res.output
    assert "--backend" in res.output
    assert "--latest" in res.output
    assert "--all" in res.output
    assert "--select" in res.output


def test_analyze_requires_prompt(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(cli, ["analyze", str(f), "--backend", "ollama"],
                        catch_exceptions=False)
    assert res.exit_code == 2
    assert "prompt" in res.output.lower()


def test_analyze_prompt_and_prompt_file_mutex(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("hi\n", encoding="utf-8")
    pf = tmp_path / "p.md"
    pf.write_text("PROMPT", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(cli, [
        "analyze", str(f),
        "--prompt", "x", "--prompt-file", str(pf),
        "--backend", "ollama",
    ], catch_exceptions=False)
    assert res.exit_code == 2


def test_analyze_single_file_ollama(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hello\n", encoding="utf-8")

    captured = {}

    def fake_run(full_prompt, **kw):
        captured["prompt"] = full_prompt
        captured.update(kw)
        return "## Result\nOK"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        side_effect=fake_run,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "summarize",
            "--backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 0
    assert captured["backend"] == "ollama"
    assert captured["api_key"] is None
    assert "summarize" in captured["prompt"]
    assert "hello" in captured["prompt"]
    # File written next to source
    out = list(tmp_path.glob("t.analysis-*.md"))
    assert len(out) == 1
    assert "## Result" in out[0].read_text(encoding="utf-8")
    # stdout dump
    assert "## Result" in res.output


def test_analyze_missing_key_exit_4(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.transcribe.get_api_key",
        return_value=None,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "x", "--backend", "gemini",
        ], catch_exceptions=False)
    assert res.exit_code == 4
    assert "gemini" in res.output.lower() or "key" in res.output.lower()


def test_analyze_missing_source_exit_3(tmp_path: Path):
    runner = CliRunner()
    res = runner.invoke(cli, [
        "analyze", str(tmp_path / "nope.txt"),
        "--prompt", "x", "--backend", "ollama",
    ], catch_exceptions=False)
    assert res.exit_code == 3


def test_analyze_empty_llm_exit_4(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "x", "--backend", "ollama",
        ], catch_exceptions=False)
    assert res.exit_code == 4
    assert "llm" in res.output.lower() or "ответ" in res.output.lower()


def test_analyze_prompt_file_read(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    pf = tmp_path / "p.md"
    pf.write_text("PROMPT FROM FILE", encoding="utf-8")

    captured = {}

    def fake_run(full_prompt, **kw):
        captured["prompt"] = full_prompt
        return "OK"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        side_effect=fake_run,
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt-file", str(pf),
            "--backend", "ollama",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    assert "PROMPT FROM FILE" in captured["prompt"]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_analyze.py -v`
Expected: FAIL — `analyze` command not registered.

- [ ] **Step 3: Implement `analyze_cmd` в `transcribe.py`**

В `skills/youtube_transcribe/transcribe.py` после `summarize_cmd` (перед `__all__`) добавить:

```python
@cli.command(name="analyze")
@click.argument("source", required=False,
                type=click.Path(path_type=Path))
@click.option("--prompt", "prompt_inline", default=None,
              help="User query passed verbatim to the LLM.")
@click.option("--prompt-file", "prompt_file", default=None,
              type=click.Path(exists=True, path_type=Path),
              help="Read prompt text from this file (.md/.txt).")
@click.option("--backend", "backend_opt",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini", show_default=True,
              help="LLM provider.")
@click.option("--latest", is_flag=True, default=False,
              help="Use the most recently modified batch under output-dir.")
@click.option("--all", "all_opt", is_flag=True, default=False,
              help="Analyze every video in the batch — skip the picker.")
@click.option("--select", "select_opt", default=None,
              help='1-based selection like "1,3,5-7" — skips the picker.')
@click.option("--append-to", "append_to", default=None,
              type=click.Path(path_type=Path),
              help="Append the block to this markdown file instead of "
                   "creating a new one.")
@click.option("--output", "output_opt", default=None,
              type=click.Path(path_type=Path),
              help="Override output file path.")
@click.option("--ollama-model", "ollama_model_opt", default=None,
              help="Ollama model tag (default: llama3.2:3b).")
@click.option("--ollama-host", "ollama_host_opt", default=None,
              help="Ollama HTTP host (default: http://localhost:11434).")
@click.option("--no-stdout", "no_stdout", is_flag=True, default=False,
              help="Don't print the LLM response to stdout (file only).")
@click.option("--max-chars", "max_chars", type=int, default=60_000,
              show_default=True,
              help="Per-transcript soft truncation in characters.")
def analyze_cmd(
    source: Path | None,
    prompt_inline: str | None,
    prompt_file: Path | None,
    backend_opt: str,
    latest: bool,
    all_opt: bool,
    select_opt: str | None,
    append_to: Path | None,
    output_opt: Path | None,
    ollama_model_opt: str | None,
    ollama_host_opt: str | None,
    no_stdout: bool,
    max_chars: int,
) -> None:
    """Analyze one or more transcripts via an external LLM."""
    from datetime import datetime
    from skills.youtube_transcribe.analyze.source_resolver import (
        resolve_source,
    )
    from skills.youtube_transcribe.analyze.prompt_builder import build_prompt
    from skills.youtube_transcribe.analyze import runner as analyze_runner
    from skills.youtube_transcribe.analyze.output_writer import (
        analysis_filename, write_analysis, append_analysis,
    )

    # 1. Validate prompt args (exactly one required).
    if bool(prompt_inline) == bool(prompt_file):
        console.print(
            "[red]Нужен ровно один из[/red] --prompt / --prompt-file."
        )
        sys.exit(2)
    if prompt_inline is not None:
        user_prompt = prompt_inline
    else:
        user_prompt = prompt_file.read_text(encoding="utf-8")

    # 2. API-key check (ollama is local, no key).
    if backend_opt == "ollama":
        api_key: str | None = None
    else:
        key_lookup = {
            "gemini": "gemini", "claude": "anthropic", "openai": "openai",
        }[backend_opt]
        api_key = get_api_key(key_lookup)
        if not api_key:
            console.print(
                f"[red]Нет ключа для backend={backend_opt}[/red]. "
                f"Установи через `youtube-transcribe config set-key {key_lookup}` "
                f"или используй --backend ollama (локально)."
            )
            sys.exit(4)

    # 3. Resolve SOURCE → list[VideoSource].
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    outputs_dir = Path(
        (cfg.output_dir if cfg else "./transcripts")
    ).expanduser()
    try:
        videos = resolve_source(source, outputs_dir=outputs_dir, latest=latest)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(3)
    if not videos:
        console.print("[red]Не найдено ни одного транскрипта в источнике.[/red]")
        sys.exit(3)

    total_videos = len(videos)
    # 4. Subset selection (--all / --select / picker — task 10 wires picker).
    if all_opt:
        chosen = videos
    elif select_opt:
        from skills.youtube_transcribe.analyze.select_parser import parse_select
        try:
            indices = parse_select(select_opt, total=total_videos)
        except ValueError as e:
            console.print(f"[red]--select: {e}[/red]")
            sys.exit(2)
        chosen = [videos[i] for i in indices]
    elif source is not None and source.is_file():
        # Single-file SOURCE: no picker, just use it.
        chosen = videos
    else:
        # Interactive picker — added in Task 10.
        console.print(
            "[red]Не указано --all / --select / --latest, а интерактив пока выключен.[/red]"
        )
        sys.exit(3)

    if not chosen:
        console.print("[red]Пустой выбор — нечего отправлять.[/red]")
        sys.exit(3)

    # 5. Build the full prompt.
    full_prompt = build_prompt(user_prompt, chosen, max_chars=max_chars)

    # 6. Call LLM.
    response = analyze_runner.run_analysis(
        full_prompt,
        backend=backend_opt,
        api_key=api_key,
        ollama_model=ollama_model_opt or "llama3.2:3b",
        ollama_host=ollama_host_opt or "http://localhost:11434",
    )
    if not response.strip():
        console.print(
            "[red]LLM не вернул ответ.[/red] Возможно, нет сети, "
            "истекла квота, или `ollama serve` не запущен."
        )
        sys.exit(4)

    # 7. Write file (append vs new).
    now = datetime.now()
    backend_label = backend_opt
    if append_to is not None:
        target = append_analysis(
            target=append_to,
            body=response,
            user_prompt=user_prompt,
            backend_label=backend_label,
            videos=chosen,
            total_videos=total_videos,
            now=now,
        )
    else:
        if output_opt is not None:
            out_path = output_opt
        elif source is not None and source.is_file():
            out_path = source.with_name(
                f"{source.stem}.{analysis_filename(now)}"
            )
        else:
            base_dir = source if source is not None else videos[0].transcript_path.parent
            out_path = base_dir / analysis_filename(now)
        target = write_analysis(
            out_path=out_path,
            body=response,
            user_prompt=user_prompt,
            backend_label=backend_label,
            videos=chosen,
            total_videos=total_videos,
            now=now,
        )

    # 8. stdout dump (unless --no-stdout).
    if not no_stdout:
        click.echo(response)
    console.print(f"[green]✓[/green] analysis via {backend_opt}")
    console.print(f"  [bold]{target}[/bold]")
```

В `__all__` (last lines файла) добавить `"analyze_cmd"`:

```python
__all__ = [
    "cli", "transcribe_cmd", "batch_cmd", "config",
    "webui_cmd", "summarize_cmd", "analyze_cmd",
]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_analyze.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run full suite, ensure nothing else broke**

Run: `uv run pytest -q`
Expected: ≥552 passed (was 544, +8 in this task).

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py tests/test_cli_analyze.py
git commit -m "$(cat <<'EOF'
feat(v0.6): `analyze` CLI — single-file + --all / --select paths

- Required exactly-one --prompt / --prompt-file
- Backend gating (api key for cloud; ollama free)
- SOURCE: file → use directly; folder → --all / --select (picker comes
  in next task)
- Writes <source>.analysis-*.md or <batch>/analysis-*.md
- stdout dump by default (--no-stdout to suppress)
- Exit codes: 0/2 (cli)/3 (source missing)/4 (key/empty llm)
EOF
)"
```

---

### Task 10: --latest + interactive picker integration

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py` (replace "interactive picker is off" stub)
- Modify: `tests/test_cli_analyze.py` (add picker-mock tests)

- [ ] **Step 1: Написать failing tests**

В конец `tests/test_cli_analyze.py` добавить:

```python
def test_analyze_latest_skips_picker(tmp_path: Path):
    """--latest picks newest batch and uses all its videos without picker."""
    batch = tmp_path / "batch_1"
    batch.mkdir()
    (batch / "v.txt").write_text("[00:00:00.000 --> 00:00:01.000] hi\n",
                                 encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "batch_1",
        "created_at": "2026-05-11T14:00:00",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "X",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")

    captured = {}

    def fake_run(full_prompt, **kw):
        captured["prompt"] = full_prompt
        return "RESULT"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        side_effect=fake_run,
    ), patch(
        "skills.youtube_transcribe.transcribe.CONFIG_PATH",
        new=tmp_path / "no-config.toml",
    ), patch(
        "skills.youtube_transcribe.transcribe.load_config",
        return_value=type("Cfg", (), {"output_dir": str(tmp_path)})(),
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", "--latest",
            "--prompt", "P", "--backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 0
    out_files = list(batch.glob("analysis-*.md"))
    assert len(out_files) == 1


def test_analyze_picker_called_when_no_flags(tmp_path: Path):
    """Folder SOURCE + no --all/--select → picker is invoked."""
    batch = tmp_path / "b"
    batch.mkdir()
    (batch / "v.txt").write_text("[00:00:00.000 --> 00:00:01.000] hi\n",
                                 encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "b", "created_at": "x",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "X",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")

    def fake_pick(videos):
        return videos  # accept all

    with patch(
        "skills.youtube_transcribe.analyze.picker.pick_videos",
        side_effect=fake_pick,
    ), patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="OK",
    ), patch(
        "skills.youtube_transcribe.transcribe.sys.stdin",
    ) as fake_stdin:
        fake_stdin.isatty.return_value = True
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(batch),
            "--prompt", "P", "--backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 0


def test_analyze_picker_cancel_exits_5(tmp_path: Path):
    batch = tmp_path / "b"
    batch.mkdir()
    (batch / "v.txt").write_text("[00:00:00.000 --> 00:00:01.000] hi\n",
                                 encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "b", "created_at": "x",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "X",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")

    from skills.youtube_transcribe.analyze.picker import PickerCancelled

    with patch(
        "skills.youtube_transcribe.analyze.picker.pick_videos",
        side_effect=PickerCancelled(),
    ), patch(
        "skills.youtube_transcribe.transcribe.sys.stdin",
    ) as fake_stdin:
        fake_stdin.isatty.return_value = True
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(batch),
            "--prompt", "P", "--backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 5


def test_analyze_no_tty_no_flags_exits_3(tmp_path: Path):
    """Folder SOURCE, non-TTY, no --all/--select → exit 3 with hint."""
    batch = tmp_path / "b"
    batch.mkdir()
    (batch / "v.txt").write_text("[00:00:00.000 --> 00:00:01.000] hi\n",
                                 encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "b", "created_at": "x",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "X",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")

    with patch(
        "skills.youtube_transcribe.transcribe.sys.stdin",
    ) as fake_stdin:
        fake_stdin.isatty.return_value = False
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(batch),
            "--prompt", "P", "--backend", "ollama",
        ], catch_exceptions=False)

    assert res.exit_code == 3
    assert "--all" in res.output or "--latest" in res.output


def test_analyze_select_mutex_with_all(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] x\n", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(cli, [
        "analyze", str(f),
        "--prompt", "P", "--backend", "ollama",
        "--all", "--select", "1",
    ], catch_exceptions=False)
    assert res.exit_code == 2
    assert "взаимоисключ" in res.output.lower() or "mutex" in res.output.lower() or "exclusive" in res.output.lower()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_cli_analyze.py -v`
Expected: 5 new tests FAIL (picker not yet wired).

- [ ] **Step 3: Wire picker into `analyze_cmd`**

В `skills/youtube_transcribe/transcribe.py`, в начале `analyze_cmd` (после validation prompt'а, перед "API-key check") добавить взаимоисключение флагов выбора:

```python
    # --latest / --all / --select are pairwise mutually exclusive.
    sel_flags = sum(1 for x in (latest, all_opt, bool(select_opt)) if x)
    if sel_flags > 1:
        console.print(
            "[red]--latest / --all / --select взаимоисключающи (exclusive).[/red]"
        )
        sys.exit(2)
```

Затем заменить блок выбора source/subset (от секции `# 3. Resolve SOURCE` до конца секции `# 4. Subset selection`) на следующее:

```python
    # 3. Resolve SOURCE → list[VideoSource].
    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else None
    outputs_dir = Path(
        (cfg.output_dir if cfg else "./transcripts")
    ).expanduser()

    # If SOURCE is omitted and --latest is not set, offer batch picker in TTY.
    if source is None and not latest:
        if not sys.stdin.isatty():
            console.print(
                "[red]Не указан SOURCE и нет --latest, "
                "а stdin не TTY — picker недоступен.[/red]"
            )
            sys.exit(3)
        from skills.youtube_transcribe.analyze.picker import (
            pick_batch, PickerCancelled,
        )
        try:
            source = pick_batch(outputs_dir)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(3)
        except PickerCancelled:
            console.print("[yellow]Отменено.[/yellow]")
            sys.exit(5)

    try:
        videos = resolve_source(source, outputs_dir=outputs_dir, latest=latest)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(3)
    if not videos:
        console.print("[red]Не найдено ни одного транскрипта в источнике.[/red]")
        sys.exit(3)

    total_videos = len(videos)

    # 4. Subset selection: --all / --select / single-file / picker.
    if all_opt or latest:
        chosen = videos
    elif select_opt:
        from skills.youtube_transcribe.analyze.select_parser import parse_select
        try:
            indices = parse_select(select_opt, total=total_videos)
        except ValueError as e:
            console.print(f"[red]--select: {e}[/red]")
            sys.exit(2)
        chosen = [videos[i] for i in indices]
    elif source is not None and source.is_file():
        chosen = videos
    else:
        if not sys.stdin.isatty():
            console.print(
                "[red]Не указано --all / --select / --latest, "
                "а stdin не TTY — picker недоступен.[/red]"
            )
            sys.exit(3)
        from skills.youtube_transcribe.analyze.picker import (
            pick_videos, PickerCancelled,
        )
        try:
            chosen = pick_videos(videos)
        except PickerCancelled:
            console.print("[yellow]Отменено.[/yellow]")
            sys.exit(5)
```

Note: `--latest` теперь implicitly включает `chosen = videos` (как `--all`), потому что после `pick_latest_batch` пользователь не имеет шанса дальше отбирать через picker — он уже выразил намерение «весь свежий batch». Это соответствует тому что было в Task 9 spec.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_analyze.py -v`
Expected: 13 passed (8 old + 5 new).

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -q`
Expected: ≥557 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py tests/test_cli_analyze.py
git commit -m "$(cat <<'EOF'
feat(v0.6): analyze CLI — --latest + interactive picker integration

- TTY → questionary checkbox; non-TTY → exit 3 with hint
- Picker cancellation (Ctrl-C) → exit 5
- --latest / --all / --select are mutually exclusive (exit 2)
EOF
)"
```

---

### Task 11: --append-to polish + integration covers

**Files:**
- Modify: `tests/test_cli_analyze.py` (extra coverage)

This task hardens edge cases that were touched but not directly tested in 9–10: `--append-to` integration, `--output` override, `--no-stdout`, batch-folder SOURCE writes file inside the batch.

- [ ] **Step 1: Add tests**

В конец `tests/test_cli_analyze.py` добавить:

```python
def test_analyze_append_to_creates_new(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    target = tmp_path / "combined.md"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="FIRST",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "P", "--backend", "ollama",
            "--append-to", str(target),
        ], catch_exceptions=False)

    assert res.exit_code == 0
    assert target.exists()
    txt = target.read_text(encoding="utf-8")
    assert txt.startswith("# Combined analyses")
    assert "FIRST" in txt


def test_analyze_append_to_existing(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    target = tmp_path / "combined.md"
    target.write_text("# Combined analyses\n\n## Analysis — 2026-05-10 00:00\n\nOLD\n",
                      encoding="utf-8")

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="NEW",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "P", "--backend", "ollama",
            "--append-to", str(target),
        ], catch_exceptions=False)

    assert res.exit_code == 0
    txt = target.read_text(encoding="utf-8")
    assert "OLD" in txt
    assert "NEW" in txt
    assert txt.count("## Analysis — ") == 2


def test_analyze_explicit_output_path(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    custom = tmp_path / "my-analysis.md"

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="HELLO",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "P", "--backend", "ollama",
            "--output", str(custom),
        ], catch_exceptions=False)

    assert res.exit_code == 0
    assert custom.exists()
    assert "HELLO" in custom.read_text(encoding="utf-8")


def test_analyze_no_stdout_suppresses_response(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="VERY UNIQUE STRING ZZ",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(f),
            "--prompt", "P", "--backend", "ollama",
            "--no-stdout",
        ], catch_exceptions=False)

    assert res.exit_code == 0
    assert "VERY UNIQUE STRING ZZ" not in res.output
    # But the file should still contain it.
    out = list(tmp_path.glob("t.analysis-*.md"))
    assert "VERY UNIQUE STRING ZZ" in out[0].read_text(encoding="utf-8")


def test_analyze_batch_folder_writes_inside(tmp_path: Path):
    batch = tmp_path / "batch_x"
    batch.mkdir()
    (batch / "v.txt").write_text(
        "[00:00:00.000 --> 00:00:01.000] hi\n", encoding="utf-8")
    (batch / "manifest.json").write_text(json.dumps({
        "batch_name": "batch_x", "created_at": "x",
        "stats": {"total": 1, "ok": 1, "failed": 0},
        "videos": [{
            "index": 1, "url": None, "video_id": None, "title": "X",
            "upload_date": None, "duration_sec": None, "channel": None,
            "language_detected": None,
            "files": {"txt": "v.txt"}, "status": "ok",
        }],
    }), encoding="utf-8")

    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="OK",
    ):
        runner = CliRunner()
        res = runner.invoke(cli, [
            "analyze", str(batch),
            "--prompt", "P", "--backend", "ollama", "--all",
        ], catch_exceptions=False)

    assert res.exit_code == 0
    files = list(batch.glob("analysis-*.md"))
    assert len(files) == 1
```

- [ ] **Step 2: Run tests, verify they pass**

Run: `uv run pytest tests/test_cli_analyze.py -v`
Expected: 18 passed (5 new + 13 existing).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_analyze.py
git commit -m "test(v0.6): cover --append-to / --output / --no-stdout / batch folder"
```

---

# Phase 6 — Refactor `summarize` over runner

### Task 12: summarize_cmd becomes a thin wrapper

**Files:**
- Modify: `skills/youtube_transcribe/quality/summarizer.py`
- Create: `tests/test_summarize_uses_analyze.py`
- Verify: `tests/test_cli_summarize.py` still passes byte-for-byte.

- [ ] **Step 1: Написать failing tests**

`tests/test_summarize_uses_analyze.py`:

```python
"""After refactor, summarizer goes through analyze.runner."""
from unittest.mock import patch

from skills.youtube_transcribe.quality.summarizer import summarize_transcript
from skills.youtube_transcribe.utils.output_writer import Segment


def test_summarize_calls_run_analysis():
    segs = [Segment(start=0.0, end=1.0, text="hello")]
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="## TL;DR\nOK",
    ) as mock:
        out = summarize_transcript(
            segs, language="en",
            api_key="fake", backend="gemini",
        )
    assert out == "## TL;DR\nOK"
    mock.assert_called_once()
    full_prompt = mock.call_args.args[0]
    # The hardcoded summary template must still be present.
    assert "TL;DR" in full_prompt
    assert "Key points" in full_prompt
    assert "Notable quotes" in full_prompt
    # And the transcript text must be there.
    assert "hello" in full_prompt


def test_summarize_ollama_path():
    segs = [Segment(start=0.0, end=1.0, text="hi")]
    with patch(
        "skills.youtube_transcribe.analyze.runner.run_analysis",
        return_value="X",
    ) as mock:
        out = summarize_transcript(
            segs, language="ru",
            api_key=None, backend="ollama",
            ollama_model="llama3.2:3b",
            ollama_host="http://localhost:11434",
        )
    assert out == "X"
    kwargs = mock.call_args.kwargs
    assert kwargs["backend"] == "ollama"
    assert kwargs["api_key"] is None
    assert kwargs["ollama_model"] == "llama3.2:3b"
    assert kwargs["ollama_host"] == "http://localhost:11434"


def test_summarize_empty_segments_returns_empty():
    out = summarize_transcript([], language="en", api_key="k", backend="gemini")
    assert out == ""
```

- [ ] **Step 2: Run new tests, verify they fail**

Run: `uv run pytest tests/test_summarize_uses_analyze.py -v`
Expected: FAIL — `summarize_transcript` currently calls `_call_*` directly, not `analyze.runner`.

- [ ] **Step 3: Refactor `quality/summarizer.py`**

Replace content of `skills/youtube_transcribe/quality/summarizer.py`:

```python
"""LLM-based summary of transcripts.

Thin wrapper over analyze.runner with a hardcoded structured
TL;DR + key points + notable quotes prompt template. Kept as a
separate entry point for backwards compatibility with v0.5 callers
and the existing `youtube-transcribe summarize` CLI.
"""
from __future__ import annotations

from skills.youtube_transcribe.utils.output_writer import Segment
from skills.youtube_transcribe.analyze import runner as analyze_runner


_SUMMARY_PROMPT = """\
You are summarizing a video transcript. Produce a structured Markdown
summary in {language}.

Format (use these EXACT section headers):

## TL;DR
<one paragraph, 2-4 sentences>

## Key points
- <bullet 1>
- <bullet 2>
- ...

## Notable quotes
- [HH:MM:SS] "<quote>"
- ...

Rules:
- Be concise. Don't repeat the same idea twice.
- Quotes should be exact spans from the transcript (not paraphrased).
- Timestamps in `HH:MM:SS` (no fractional seconds).
- 3–7 key points; 0–5 notable quotes.

Transcript (with timecodes in seconds):
{transcript_text}

Output ONLY the markdown summary. No preamble, no code fence.
"""


def _format_transcript_for_summary(segments: list[Segment]) -> str:
    """Compact `[HH:MM:SS] text` lines, truncated at 60k chars."""
    lines = []
    total = 0
    for s in segments:
        h = int(s.start // 3600)
        m = int((s.start % 3600) // 60)
        sec = int(s.start % 60)
        line = f"[{h:02d}:{m:02d}:{sec:02d}] {s.text.strip()}"
        if total + len(line) > 60_000:
            lines.append("[...truncated...]")
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def summarize_transcript(
    segments: list[Segment],
    language: str = "en",
    *,
    api_key: str | None,
    backend: str = "gemini",
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Return Markdown summary or empty string on failure."""
    if not segments:
        return ""

    prompt = _SUMMARY_PROMPT.format(
        language=language or "en",
        transcript_text=_format_transcript_for_summary(segments),
    )
    return analyze_runner.run_analysis(
        prompt,
        backend=backend,
        api_key=api_key,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
    )
```

- [ ] **Step 4: Run new tests, verify they pass**

Run: `uv run pytest tests/test_summarize_uses_analyze.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify pre-existing `tests/test_cli_summarize.py` still passes**

Run: `uv run pytest tests/test_cli_summarize.py -v`
Expected: 7 passed (no change in behavior).

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -q`
Expected: ≥568 passed.

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/quality/summarizer.py \
        tests/test_summarize_uses_analyze.py
git commit -m "$(cat <<'EOF'
refactor(v0.6): summarize_transcript routes through analyze.runner

Same external contract (exit codes, output, kwargs) — internal call
path now goes through the shared analyze.runner.run_analysis helper
instead of dispatching to _call_* directly. The hardcoded TL;DR
template stays here as a backwards-compatible preset.
EOF
)"
```

---

# Phase 7 — `batch --then-analyze`

### Task 13: --then-analyze flag in batch_cmd

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py` (batch_cmd: add 4 new options + call hook at the end; add module-level `_run_then_analyze` helper)
- Create: `tests/test_batch_then_analyze.py`

Strategy: do NOT refactor the ~400-line `batch_cmd` body. Instead extract only the post-batch hook into a new module-level helper `_run_then_analyze` and inject one call at the end of `batch_cmd` after all outputs are written. Tests exercise `_run_then_analyze` directly + a smoke test of the CLI plumbing.

- [ ] **Step 1: Написать failing tests**

`tests/test_batch_then_analyze.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_batch_then_analyze.py -v`
Expected: ImportError on `_run_then_analyze` or unknown `--then-analyze` flag.

- [ ] **Step 3: Add module-level `_run_then_analyze` to `transcribe.py`**

Открой `skills/youtube_transcribe/transcribe.py`. Перед декоратором `@cli.command(name="batch")` (~ строка 478) добавить новый helper:

```python
def _run_then_analyze(
    *,
    batch_folder: Path,
    prompt_inline: str | None,
    prompt_file: Path | None,
    backend: str,
) -> None:
    """Post-batch hook for `batch --then-analyze`.

    Resolves transcripts from `batch_folder/manifest.json`, builds a prompt
    from `prompt_inline` or `prompt_file`, calls the LLM, writes
    `analysis-*.md` inside `batch_folder`. In TTY mode an interactive
    picker is shown; in non-TTY all videos are used. No-op (with a warning)
    on missing transcripts or empty LLM response. Calls `sys.exit(4)` only
    on missing API key — other failures degrade gracefully so the batch
    itself stays reported as successful.
    """
    from datetime import datetime
    from skills.youtube_transcribe.analyze.source_resolver import resolve_source
    from skills.youtube_transcribe.analyze.prompt_builder import build_prompt
    from skills.youtube_transcribe.analyze import runner as analyze_runner
    from skills.youtube_transcribe.analyze.output_writer import (
        analysis_filename, write_analysis,
    )

    user_prompt = (
        prompt_inline if prompt_inline is not None
        else prompt_file.read_text(encoding="utf-8")
    )

    if backend == "ollama":
        api_key: str | None = None
    else:
        key_lookup = {
            "gemini": "gemini", "claude": "anthropic", "openai": "openai",
        }[backend]
        api_key = get_api_key(key_lookup)
        if not api_key:
            console.print(
                f"[red]--then-analyze: нет ключа для backend={backend}[/red]."
            )
            sys.exit(4)

    try:
        videos = resolve_source(
            batch_folder, outputs_dir=batch_folder.parent, latest=False,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return
    if not videos:
        console.print(
            "[yellow]Batch не содержит транскриптов — analyze пропущен.[/yellow]"
        )
        return

    if sys.stdin.isatty():
        from skills.youtube_transcribe.analyze.picker import (
            pick_videos, PickerCancelled,
        )
        try:
            chosen = pick_videos(videos)
        except PickerCancelled:
            console.print("[yellow]analyze отменён.[/yellow]")
            return
    else:
        chosen = videos
    if not chosen:
        console.print("[yellow]Пустой выбор — analyze пропущен.[/yellow]")
        return

    full_prompt = build_prompt(user_prompt, chosen)
    response = analyze_runner.run_analysis(
        full_prompt, backend=backend, api_key=api_key,
    )
    if not response.strip():
        console.print("[red]LLM не вернул ответ (then-analyze).[/red]")
        return

    now = datetime.now()
    out_path = batch_folder / analysis_filename(now)
    target = write_analysis(
        out_path=out_path, body=response, user_prompt=user_prompt,
        backend_label=backend, videos=chosen, total_videos=len(videos),
        now=now,
    )
    click.echo(response)
    console.print(f"[green]✓[/green] then-analyze via {backend}")
    console.print(f"  [bold]{target}[/bold]")
```

- [ ] **Step 4: Add `--then-analyze` Click options to the batch_cmd decorator stack**

Сразу перед `def batch_cmd(...)` (после последнего из existing `@click.option(...)` — той что про `--vision-prompt`) добавь:

```python
@click.option("--then-analyze", "then_analyze", is_flag=True, default=False,
              help="After batch completes, run `analyze` on the produced folder.")
@click.option("--prompt", "analyze_prompt", default=None,
              help="Prompt for --then-analyze (verbatim).")
@click.option("--prompt-file", "analyze_prompt_file",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Read --then-analyze prompt from file.")
@click.option("--analyze-backend", "analyze_backend",
              type=click.Choice(["gemini", "claude", "openai", "ollama"]),
              default="gemini", show_default=True,
              help="LLM backend for --then-analyze.")
```

- [ ] **Step 5: Wire prompt validation + post-batch call inside `batch_cmd`**

In `batch_cmd`, right after the function signature opens (top of body — before `if not CONFIG_PATH.exists()`), add the early-exit prompt-validation:

```python
def batch_cmd(
    inputs: tuple[str, ...],
    from_file: Path | None,
    limit: int,
    batch_name: str | None,
    no_combined: bool,
    fail_fast: bool,
    **opts,
) -> None:
    """Batch-транскрибация: пачка URL, канал/плейлист, или --from-file."""
    # === v0.6: extract analyze-related options before anything else ===
    then_analyze = opts.pop("then_analyze", False)
    analyze_prompt = opts.pop("analyze_prompt", None)
    analyze_prompt_file = opts.pop("analyze_prompt_file", None)
    analyze_backend = opts.pop("analyze_backend", "gemini")

    if then_analyze and not (analyze_prompt or analyze_prompt_file):
        console.print(
            "[red]--then-analyze требует --prompt или --prompt-file.[/red]"
        )
        sys.exit(2)

    if not CONFIG_PATH.exists():
        run_wizard()
    # ... (rest of the original body stays untouched)
```

At the very end of `batch_cmd` (after the last write-outputs/summary print line, before the function returns), add:

```python
    # === v0.6: post-batch analyze hook ===
    if then_analyze:
        batch_folder = output_root / batch_name  # batch_name is final from earlier in the body
        if batch_folder.exists():
            _run_then_analyze(
                batch_folder=batch_folder,
                prompt_inline=analyze_prompt,
                prompt_file=analyze_prompt_file,
                backend=analyze_backend,
            )
```

(`output_root` and `batch_name` are both already defined earlier in `batch_cmd` — `output_root` at the path-resolution stage, `batch_name` after auto-name derivation. If they have different names in current code, use the actual names — the goal is to reference the final batch output folder.)

- [ ] **Step 6: Run tests, verify they pass**

Run: `uv run pytest tests/test_batch_then_analyze.py -v`
Expected: 5 passed.

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -q`
Expected: ≥573 passed (was 568 after Task 12; +5 here).

- [ ] **Step 8: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py tests/test_batch_then_analyze.py
git commit -m "$(cat <<'EOF'
feat(v0.6): batch --then-analyze for continuous batch→analyze flow

After a successful batch, when --then-analyze is set, runs the analyze
pipeline on the produced folder. TTY → picker, non-TTY → --all. Prompt
sourced from --prompt or --prompt-file (one required, else exit 2).
Backend picked via --analyze-backend (default: gemini). Implemented as
a post-batch hook (`_run_then_analyze`) — no refactor of the existing
~400-line batch_cmd body.
EOF
)"
```

---

# Phase 8 — Release prep

### Task 14: README + CHANGELOG

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add README section**

Открой `README.md`, найди раздел про `summarize` (или раздел про CLI команды). Сразу после него добавь:

````markdown
## Analyze — free-form LLM analysis over transcripts

The skill produces transcripts; analysis is an explicit second step you
trigger when you want it. `analyze` packages one or more existing
transcripts together with your own free-form prompt and sends them to
the LLM of your choice.

```bash
# Analyze a single transcript
youtube-transcribe analyze ./transcripts/x.txt \
  --prompt "Extract the main argument and counter-examples." \
  --backend gemini

# Analyze the most recent batch (skips picker)
youtube-transcribe analyze --latest --all \
  --prompt-file my-prompt.md --backend claude

# Pick a subset of videos in a folder interactively
youtube-transcribe analyze ./transcripts/batch_2026-05-11_claude/ \
  --prompt "Compare how each speaker frames the problem." \
  --backend openai

# Append a new analysis block to an existing combined.md
youtube-transcribe analyze --latest --all \
  --prompt "Now extract every URL mentioned." \
  --append-to ./transcripts/batch_X/notes.md

# Local LLM, no API keys
youtube-transcribe analyze ./transcripts/x.json \
  --prompt "Summarize for a 12-year-old." \
  --backend ollama --ollama-model llama3.2:3b
```

Output is written to `<batch>/analysis-YYYY-MM-DD-HHMM.md` (or rendered
next to the source file for single-file mode), and the response is also
printed to stdout so it's visible inline when invoked from Claude Code.

`batch --then-analyze` chains a batch with an immediate analyze pass:

```bash
youtube-transcribe batch https://www.youtube.com/@channel --limit 5 \
  --backend smart \
  --then-analyze --prompt "Bullet the main takeaways from each video." \
  --analyze-backend gemini
```
````

- [ ] **Step 2: Add CHANGELOG entry**

В `CHANGELOG.md` сверху, под существующим заголовком, добавить:

```markdown
## [0.6.0] — 2026-05-11

### Added
- `youtube-transcribe analyze [SOURCE]` — free-form LLM analysis over
  one or more existing transcripts. Supports `--prompt`/`--prompt-file`,
  `--backend gemini|claude|openai|ollama`, `--latest`, `--all`,
  `--select "1,3,5-7"`, `--append-to <md>`, `--output <path>`,
  `--no-stdout`, `--max-chars`.
- Interactive `questionary` checkbox picker for video selection when
  SOURCE is a folder and no `--all`/`--select`/`--latest` is given.
- `batch --then-analyze --prompt "..."` runs analyze on the produced
  batch folder immediately after the batch completes.

### Changed
- `summarize` now routes through `analyze.runner` internally (same
  hardcoded TL;DR + key points + notable quotes template; same exit
  codes; same output file format). No user-visible behavior change.

### Dependencies
- New: `questionary>=2.0` (powers the analyze picker).
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs(v0.6): README usage examples + CHANGELOG entry for analyze"
```

---

### Task 15: Version bump + code-reviewer + security-review

**Files:**
- Modify: `pyproject.toml` (0.6.0-dev → 0.6.0)
- Modify: `skills/youtube_transcribe/__init__.py`

- [ ] **Step 1: Drop the `-dev` suffix**

`pyproject.toml`:

```toml
version = "0.6.0"
```

`skills/youtube_transcribe/__init__.py`:

```python
"""youtube-transcribe — universal transcription skill."""
__version__ = "0.6.0"
```

- [ ] **Step 2: Run full test suite one last time**

Run: `uv run pytest -q`
Expected: ≥570 passed. All green.

- [ ] **Step 3: Run code-reviewer skill**

Выполнить локальное ревью изменений всего v0.6 (через скилл `code-reviewer` если доступен, либо вручную пройтись по всем коммитам Tasks 1–14):

```bash
git log --oneline cbef1fc..HEAD
```

Ожидаемо: ~14 коммитов вида `feat(v0.6)` / `test(v0.6)` / `refactor(v0.6)` / `docs(v0.6)` / `build(v0.6)`.

Что проверить:
- Нет ли утечек API-ключей в логах / stdout (особенно когда `--verbose`).
- Закрываются ли file handles (с `pathlib.Path.write_text` они закрываются автоматически, но в `append_analysis` используется `open(...)` — убедиться что в context manager'е).
- Не падает ли импорт `questionary` в headless окружениях (он не должен — импортируется лениво внутри `picker.py`).
- `analyze.runner.run_analysis` ловит `Exception` — это намеренно (см. summarizer). Не маскируем системные ошибки типа `KeyboardInterrupt` потому что `except Exception` их пропускает.

- [ ] **Step 4: Run security-review skill**

Проверки:
- `--prompt-file` читает произвольный путь — но он gated через `click.Path(exists=True)`, опасности path traversal нет (читаем как user-provided text).
- `--append-to` записывает в произвольный путь — это намеренно (user-controlled), но убедиться что не создаются файлы вне ожидаемых дир без явного указания.
- LLM-output попадает в stdout и в файл as-is — это OK для текстовых ответов, но если LLM вернёт код с управляющими последовательностями, Rich/Click их не парсят (мы используем `click.echo`, не `rich.print` на response body).

- [ ] **Step 5: Final commit + tag**

```bash
git add pyproject.toml skills/youtube_transcribe/__init__.py
git commit -m "$(cat <<'EOF'
release: v0.6.0 — `analyze` sub-command

Skill is the data producer; analyze is the explicit bridge step that
packages existing transcripts together with a user's free-form prompt
and sends them to a chosen LLM (gemini/claude/openai/ollama). Source
selection via path, --latest, or interactive checkbox picker
(questionary). Output written to <batch>/analysis-*.md and printed
to stdout. summarize remains as a thin wrapper over the same runner.
batch gains --then-analyze for one-shot transcribe-then-analyze flow.

~570 unit tests green (was 544; +26).
EOF
)"
```

- [ ] **Step 6: Push to remote (optional, follow git-cross-os skill)**

```bash
git push origin main
# or, if working on a branch:
# git push origin v0.6-analyze
```

---

## Acceptance criteria — final shake-down

Ручной прогон в TTY (после успеха всех тестов):

- [ ] `youtube-transcribe analyze --help` показывает все 13 опций из спеки §2.2.
- [ ] `analyze <path-to-txt> --prompt "Что обсуждалось?" --backend ollama` — работает без API-ключей, пишет файл рядом с источником.
- [ ] `analyze <batch> --all --prompt "..." --backend gemini` — пишет `analysis-*.md` в папку batch'а, печатает ответ в stdout.
- [ ] `analyze <batch> --prompt "..."` в TTY запускает picker; после выбора — пишет файл.
- [ ] `analyze --latest --all --prompt "..." --backend ollama` — берёт самый свежий batch без интерактива.
- [ ] `analyze <batch> --select "1" --prompt "..." --backend ollama` — обходит picker.
- [ ] `analyze <batch> --all --prompt "..." --backend ollama --append-to combined.md` — дописывает блок.
- [ ] `summarize <transcript>` продолжает работать (existing test_cli_summarize.py все 7 тестов green).
- [ ] `batch ... --then-analyze --prompt "..." --analyze-backend ollama` — запускает analyze сразу после batch.
- [ ] `pytest -q` зелёный на macOS arm64 (Mac handoff остаётся валидным).
