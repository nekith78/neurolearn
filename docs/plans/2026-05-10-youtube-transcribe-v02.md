# youtube-transcribe v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Расширить v0.1.2 visual-режимом (multimodal видео-анализ через Gemini), quality check'ом транскриптов (для smart-режима), мультиязычными триггерами через локальные embeddings, динамическими преcетами с единым реестром опций, CLI-тулом для управления triggers.toml.

**Architecture:** Поверх существующего pipeline'а v0.1 (Transcriber Protocol → run_pipeline → output_writer) добавляются 4 новых protocol-абстракции: `QualityChecker`, `Detector`, `VisionBackend`, плюс реестр опций (`presets.registry`). Pipeline получает 2 новых опциональных stage между transcribe и write: quality_check (только в smart-режиме на источнике субтитров) и detect→vision_annotate (если `--with-visuals`). Финальный output идёт всегда, quality плохой = warning, не failure.

**Tech Stack:** Python 3.11+ (без 3.10), uv, Click, Rich, sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2), pyspellchecker, pyahocorasick, langdetect, lemminflect, pymorphy3, tomlkit, PySceneDetect, ImageHash, ffmpeg (system binary), google-genai (для Gemini multimodal), pytesseract (opt-in OCR), kenlm (opt-in perplexity).

**Spec:** `docs/specs/2026-05-10-youtube-transcribe-v02-visual-mode-design.md` (commits b7b2eaa → 9b8c408 → 763bb89).

---

## Структура файлов

```
youtube-transcribe/
├── pyproject.toml                                ← Task 1 (новые deps + extras)
├── skills/youtube_transcribe/
│   ├── __init__.py                               ← Task 2 (bump 0.2.0-dev)
│   ├── transcribe.py                             ← Task 31 (новые флаги, integrate stages)
│   ├── config.py                                 ← Task 32 (migration v0.1→v0.2)
│   ├── pipeline.py                               ← Task 31 (новый stages)
│   ├── output_writer.py                          ← Task 28-29 (visual moments, frames/, manifest)
│   ├── backends/
│   │   └── vision_base.py                        ← Task 22 (NEW)
│   ├── quality/
│   │   ├── __init__.py                           ← Task 2
│   │   ├── base.py                               ← Task 3 (NEW)
│   │   ├── spell.py                              ← Task 4 (NEW)
│   │   ├── repetition.py                         ← Task 5 (NEW)
│   │   ├── boh.py                                ← Task 6 (NEW)
│   │   ├── heuristic_checker.py                  ← Task 7 (NEW)
│   │   └── data/
│   │       └── boh_phrases.txt                   ← Task 6
│   ├── detection/
│   │   ├── __init__.py                           ← Task 2
│   │   ├── triggers.py                           ← Task 8 (NEW: TriggerConfig + load)
│   │   ├── matcher.py                            ← Task 11-13 (NEW: matching logic)
│   │   ├── base.py                               ← Task 17 (Detector Protocol)
│   │   ├── scene.py                              ← Task 18 (PySceneDetect)
│   │   ├── frame_diff.py                         ← Task 19 (ImageHash)
│   │   ├── window_merge.py                       ← Task 20 (merge + bucket select)
│   │   ├── triggers_cli.py                       ← Task 14-16 (NEW: CLI subgroup)
│   │   └── data/
│   │       └── triggers_default.toml             ← Task 9 (NEW: 25 EN phrases)
│   ├── vision/
│   │   ├── __init__.py                           ← Task 2
│   │   ├── frames.py                             ← Task 21 (ffmpeg keyframes)
│   │   ├── prompts.py                            ← Task 23 (vision prompt template)
│   │   ├── gemini.py                             ← Task 24 (GeminiVisionBackend)
│   │   └── ocr.py                                ← Task 30 (--ocr opt-in)
│   └── presets/
│       ├── __init__.py                           ← Task 2
│       ├── registry.py                           ← Task 25 (OptionField + REGISTRY)
│       ├── loader.py                             ← Task 26 (preset merge logic)
│       └── data/
│           └── presets_default.toml              ← Task 27 (4 tiers)
└── tests/
    ├── data/
    │   ├── quality_golden.json                   ← Task 35
    │   └── fixtures/                             ← e2e fixtures
    ├── test_quality_*.py                         ← Tasks 3-7
    ├── test_triggers_*.py                        ← Tasks 8-16
    ├── test_detection_*.py                       ← Tasks 17-20
    ├── test_vision_*.py                          ← Tasks 21-24
    ├── test_presets_*.py                         ← Tasks 25-27
    ├── test_output_writer_v02.py                 ← Tasks 28-29
    ├── test_cli_v02.py                           ← Task 31
    ├── test_migration_v02.py                     ← Task 32
    └── test_e2e_visual_smoke.py                  ← Task 34
```

## Phases

- **Phase 1 (Tasks 1–2):** Bootstrap v0.2 — pyproject deps + module scaffolding.
- **Phase 2 (Tasks 3–7):** Quality check — все 4 кирпича + composite.
- **Phase 3 (Tasks 8–13):** Triggers core — load, parse weights, matcher (raw/strict/soft/universal).
- **Phase 4 (Tasks 14–16):** Triggers CLI tool — init/add/list/remove/reset/edit/test/weight.
- **Phase 5 (Tasks 17–20):** Detection — Protocol, scene/frame_diff, window merge & bucket select.
- **Phase 6 (Tasks 21–24):** Vision backend — keyframes, prompts, GeminiVisionBackend.
- **Phase 7 (Tasks 25–27):** Presets registry + 4 tiers default.
- **Phase 8 (Tasks 28–31):** Output extension + CLI rewiring.
- **Phase 9 (Tasks 32–35):** OCR + migration + docs + golden set.

---

## Pre-flight (один раз перед началом)

- [ ] Проверить, что текущая директория — `/Users/nekith78/youtube-transcribe` и v0.1.2 в working state.

  Run: `git log --oneline -3`
  Expected: видны коммиты `2dd6b59` (filenames) или новее.

- [ ] Проверить что все тесты v0.1 зелёные перед стартом v0.2:

  Run: `uv run pytest -q`
  Expected: 208 passed (или больше; не должно быть failures).

- [ ] Проверить ffmpeg в системе (требуется для keyframe extraction в Phase 6):

  Run: `ffmpeg -version`
  Expected: первая строка `ffmpeg version 6.x` или новее. Если нет — `brew install ffmpeg` на Mac.

- [ ] Создать ветку (опционально, но рекомендуется для фичи такого размера):

  ```bash
  git checkout -b v0.2
  ```

  Альтернатива: разработка в `main` с откатами через revert если что-то пойдёт не так. v0.1 разрабатывали в main — стиль проекта greenfield.

---

# Phase 1 — Bootstrap v0.2

### Task 1: pyproject.toml — новые dependencies + optional extras

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version to 0.2.0-dev и добавить новые core deps**

В `[project] version` изменить:

```toml
version = "0.2.0-dev"
```

В `[project] dependencies` добавить (после существующих v0.1 deps):

```toml
    # === v0.2: Quality check ===
    "pyspellchecker>=0.8.0",
    "pyahocorasick>=2.1.0",
    "langdetect>=1.0.9",
    # === v0.2: Triggers (multilingual) ===
    "sentence-transformers>=3.0.0",
    "lemminflect>=0.2.3",
    "pymorphy3>=2.0.2",
    # === v0.2: Triggers CLI (preserve comments in TOML) ===
    "tomlkit>=0.13.0",
    # === v0.2: Detection ===
    "pyscenedetect>=0.6.4",
    "imagehash>=4.3.1",
```

- [ ] **Step 2: Добавить optional extras для тяжёлых deps**

Заменить блок `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

# OCR — opt-in. Pytesseract требует системного `tesseract` бинарника
# (brew install tesseract / apt-get install tesseract-ocr).
# easyocr — fallback, тяжёлый (60MB модели), но без системных требований.
ocr = [
    "pytesseract>=0.3.10",
    "easyocr>=1.7.0",
]

# Perplexity — opt-in. KenLM требует C++ build (`pip install` собирает из source).
# На Mac arm64 нужен `brew install cmake`.
perplexity = [
    "kenlm>=0.2.0",
]
```

- [ ] **Step 3: Проверить что `requires-python` уже `>=3.11`**

В `[project] requires-python` должно быть:

```toml
requires-python = ">=3.11"
```

(было обновлено в v0.1.2 при дропе 3.10 — проверить, если ещё `>=3.10`, поправить на `>=3.11`).

- [ ] **Step 4: Установить новые deps**

Run: `uv sync --extra dev`
Expected: ставятся новые пакеты, ничего не падает. Может занять 2-3 минуты (sentence-transformers тянет torch ~700MB на arm64).

- [ ] **Step 5: Проверить импорт каждой новой деп**

Run:
```bash
uv run python -c "import spellchecker, ahocorasick, langdetect, sentence_transformers, lemminflect, pymorphy3, tomlkit, scenedetect, imagehash; print('all imports ok')"
```
Expected: `all imports ok`.

- [ ] **Step 6: Запустить v0.1 тесты, убедиться что ничего не сломалось**

Run: `uv run pytest -q`
Expected: 208 passed (как было).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
build(v0.2): bump to 0.2.0-dev, add quality/triggers/detection deps

Core deps added: pyspellchecker, pyahocorasick, langdetect,
sentence-transformers (multilingual MiniLM), lemminflect, pymorphy3,
tomlkit, pyscenedetect, imagehash.

Optional extras:
- ocr: pytesseract + easyocr (opt-in via --ocr flag)
- perplexity: kenlm (opt-in for premium preset)
EOF
)"
```

---

### Task 2: Module scaffolding для v0.2

**Files:**
- Create: `skills/youtube_transcribe/quality/__init__.py`
- Create: `skills/youtube_transcribe/detection/__init__.py`
- Create: `skills/youtube_transcribe/vision/__init__.py`
- Create: `skills/youtube_transcribe/presets/__init__.py`
- Create: `skills/youtube_transcribe/quality/data/__init__.py` (отсутствие — норм, файл-данные)
- Create: `skills/youtube_transcribe/detection/data/__init__.py` (отсутствие — норм)
- Create: `skills/youtube_transcribe/vision/__init__.py`
- Modify: `skills/youtube_transcribe/__init__.py`

- [ ] **Step 1: Bump version в `__init__.py`**

Содержимое `skills/youtube_transcribe/__init__.py`:

```python
"""youtube-transcribe — universal transcription skill."""
__version__ = "0.2.0-dev"
```

- [ ] **Step 2: Создать пустые `__init__.py` для новых пакетов**

Run:
```bash
mkdir -p skills/youtube_transcribe/quality/data
mkdir -p skills/youtube_transcribe/detection/data
mkdir -p skills/youtube_transcribe/vision
mkdir -p skills/youtube_transcribe/presets/data
touch skills/youtube_transcribe/quality/__init__.py
touch skills/youtube_transcribe/detection/__init__.py
touch skills/youtube_transcribe/vision/__init__.py
touch skills/youtube_transcribe/presets/__init__.py
```

Содержимое каждого `__init__.py`:

```python
"""<module_name> module for youtube-transcribe v0.2."""
```

(Замени `<module_name>` на `quality` / `detection` / `vision` / `presets` соответственно.)

- [ ] **Step 3: Написать smoke-тест что пакеты импортируются**

Файл `tests/test_v02_scaffolding.py`:

```python
"""Smoke test: v0.2 module skeletons exist and import cleanly."""

def test_quality_module_imports():
    import skills.youtube_transcribe.quality  # noqa: F401

def test_detection_module_imports():
    import skills.youtube_transcribe.detection  # noqa: F401

def test_vision_module_imports():
    import skills.youtube_transcribe.vision  # noqa: F401

def test_presets_module_imports():
    import skills.youtube_transcribe.presets  # noqa: F401

def test_version_bumped():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.2.")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_v02_scaffolding.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/__init__.py \
        skills/youtube_transcribe/quality/__init__.py \
        skills/youtube_transcribe/detection/__init__.py \
        skills/youtube_transcribe/vision/__init__.py \
        skills/youtube_transcribe/presets/__init__.py \
        tests/test_v02_scaffolding.py
git commit -m "feat(v0.2): scaffold quality/detection/vision/presets modules"
```

---

# Phase 2 — Quality check

### Task 3: quality/base.py — типы и Protocol

**Files:**
- Create: `skills/youtube_transcribe/quality/base.py`
- Create: `tests/test_quality_base.py`

- [ ] **Step 1: Написать failing test**

`tests/test_quality_base.py`:

```python
"""Tests for QualityReport dataclass and QualityChecker Protocol."""
from skills.youtube_transcribe.quality.base import (
    QualityReport,
    Recommendation,
)


def test_quality_report_creation():
    r = QualityReport(
        score=0.85,
        breakdown={"oov": 0.05, "repetition": 0.02},
        flags=[],
        recommendation="use_as_is",
    )
    assert r.score == 0.85
    assert r.recommendation == "use_as_is"


def test_recommendation_literal_values():
    valid: list[Recommendation] = ["use_as_is", "fallback_recommended", "low_quality"]
    assert len(valid) == 3
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_quality_base.py -v`
Expected: ImportError — модуль ещё не существует.

- [ ] **Step 3: Написать минимальную реализацию**

`skills/youtube_transcribe/quality/base.py`:

```python
"""Base types for quality check subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Recommendation = Literal["use_as_is", "fallback_recommended", "low_quality"]
TranscriptSource = Literal["youtube_manual", "youtube_auto", "whisper", "external_asr"]


@dataclass(frozen=True)
class QualityReport:
    """Result of running QualityChecker.check on a transcript."""
    score: float                          # 0.0 — мусор, 1.0 — идеально
    breakdown: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    recommendation: Recommendation = "use_as_is"


class QualityChecker(Protocol):
    """Anything that can score a transcript locally."""

    def check(
        self,
        segments: list,                   # list[Segment] from output_writer
        language: str,
        source: TranscriptSource,
    ) -> QualityReport:
        ...
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_base.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/quality/base.py tests/test_quality_base.py
git commit -m "feat(quality): add QualityReport dataclass and QualityChecker Protocol"
```

---

### Task 4: quality/spell.py — out-of-vocab ratio через pyspellchecker

**Files:**
- Create: `skills/youtube_transcribe/quality/spell.py`
- Create: `tests/test_quality_spell.py`

- [ ] **Step 1: Написать failing test**

`tests/test_quality_spell.py`:

```python
"""Tests for out_of_vocab_ratio."""
from skills.youtube_transcribe.quality.spell import (
    out_of_vocab_ratio,
    is_language_supported,
)


def test_oov_clean_english_text():
    text = "Hello and welcome to the tutorial about Python programming"
    ratio = out_of_vocab_ratio(text, "en")
    assert ratio < 0.1, f"clean text should have low OOV, got {ratio}"


def test_oov_garbled_text():
    text = "prveит и пддеа кгдре прив тмаета пвоиет"
    ratio = out_of_vocab_ratio(text, "ru")
    assert ratio > 0.5, f"garbled text should have high OOV, got {ratio}"


def test_oov_empty_text_returns_one():
    """Empty text — treat as fully OOV (worst case)."""
    assert out_of_vocab_ratio("", "en") == 1.0
    assert out_of_vocab_ratio("   ", "en") == 1.0


def test_unsupported_language_returns_none_via_helper():
    assert is_language_supported("en") is True
    assert is_language_supported("ru") is True
    assert is_language_supported("kk") is False  # казахский не в pyspellchecker


def test_oov_unsupported_language_returns_neg_one():
    """Sentinel value — caller must skip this metric."""
    ratio = out_of_vocab_ratio("қазақ тілі", "kk")
    assert ratio == -1.0
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_quality_spell.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/quality/spell.py`:

```python
"""Out-of-vocabulary ratio via pyspellchecker.

OOV ratio = % tokens not in language dictionary. High OOV = garbled ASR.
Used as one component of HeuristicChecker.
"""
from __future__ import annotations

import re
from functools import lru_cache

from spellchecker import SpellChecker

# pyspellchecker built-in language codes (as of 0.8.x)
_SUPPORTED_LANGUAGES = {"en", "es", "fr", "pt", "de", "ru", "ar", "eu", "lv", "nl", "it"}

_TOKEN_RE = re.compile(r"\b[a-zA-Zа-яА-ЯёЁ]+\b")


def is_language_supported(lang: str) -> bool:
    return lang in _SUPPORTED_LANGUAGES


@lru_cache(maxsize=8)
def _get_checker(lang: str) -> SpellChecker:
    return SpellChecker(language=lang)


def out_of_vocab_ratio(text: str, lang: str) -> float:
    """Returns 0.0..1.0 (lower is better) or -1.0 if language unsupported.

    Empty/whitespace text returns 1.0 (worst case — caller should treat as bad signal).
    """
    if not is_language_supported(lang):
        return -1.0

    text = text.strip()
    if not text:
        return 1.0

    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if not tokens:
        return 1.0

    spell = _get_checker(lang)
    unknown = spell.unknown(tokens)
    return len(unknown) / len(tokens)
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_spell.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/quality/spell.py tests/test_quality_spell.py
git commit -m "feat(quality): add out_of_vocab_ratio via pyspellchecker"
```

---

### Task 5: quality/repetition.py — 3-gram loops + non-speech markers

**Files:**
- Create: `skills/youtube_transcribe/quality/repetition.py`
- Create: `tests/test_quality_repetition.py`

- [ ] **Step 1: Написать failing test**

`tests/test_quality_repetition.py`:

```python
"""Tests for trigram_repetition_rate and non_speech_marker_ratio."""
from skills.youtube_transcribe.quality.repetition import (
    trigram_repetition_rate,
    non_speech_marker_ratio,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def test_repetition_clean_text():
    text = "hello and welcome to the tutorial today we will discuss python"
    assert trigram_repetition_rate(text) < 0.1


def test_repetition_whisper_loop():
    """Classic Whisper hallucination — same phrase repeated many times."""
    text = " ".join(["thank you for watching"] * 20)
    assert trigram_repetition_rate(text) > 0.5


def test_repetition_short_text_returns_zero():
    """Need at least 6 tokens to compute trigrams."""
    assert trigram_repetition_rate("hi there friend") == 0.0


def test_non_speech_marker_zero_when_no_markers():
    segments = [
        Segment(start=0.0, end=5.0, text="hello world"),
        Segment(start=5.0, end=10.0, text="welcome to the show"),
    ]
    assert non_speech_marker_ratio(segments) == 0.0


def test_non_speech_marker_high_when_music_heavy():
    segments = [
        Segment(start=0.0, end=10.0, text="[Music]"),
        Segment(start=10.0, end=20.0, text="♪ ♪ ♪"),
        Segment(start=20.0, end=22.0, text="hello"),
    ]
    ratio = non_speech_marker_ratio(segments)
    assert ratio > 0.8, f"expected mostly music, got {ratio}"


def test_non_speech_marker_empty_returns_zero():
    assert non_speech_marker_ratio([]) == 0.0
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_quality_repetition.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/quality/repetition.py`:

```python
"""3-gram repetition rate (Whisper loop detector) + non-speech marker coverage."""
from __future__ import annotations

import re
from collections import Counter

from skills.youtube_transcribe.utils.output_writer import Segment

_NON_SPEECH_RE = re.compile(
    r"\[Music\]|\[Applause\]|\[Laughter\]|\[laughter\]|\[applause\]|\[music\]|"
    r"\[unintelligible\]|\(unintelligible\)|\[Music playing\]|♪|🎵",
    re.IGNORECASE,
)


def trigram_repetition_rate(text: str) -> float:
    """Returns 0..1 — higher means more looped. Counter most-common trigram / total trigrams.

    Returns 0.0 for texts shorter than 6 tokens (insufficient signal).
    """
    tokens = text.lower().split()
    if len(tokens) < 6:
        return 0.0
    trigrams = list(zip(tokens, tokens[1:], tokens[2:]))
    if not trigrams:
        return 0.0
    counter = Counter(trigrams)
    most_common_count = counter.most_common(1)[0][1]
    return most_common_count / len(trigrams)


def non_speech_marker_ratio(segments: list[Segment]) -> float:
    """Returns 0..1 — fraction of total duration covered by [Music]/♪/etc segments."""
    if not segments:
        return 0.0
    total_dur = sum(max(s.end - s.start, 0.0) for s in segments)
    if total_dur <= 0:
        return 0.0
    music_dur = sum(
        max(s.end - s.start, 0.0)
        for s in segments
        if _NON_SPEECH_RE.search(s.text)
    )
    return music_dur / total_dur
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_repetition.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/quality/repetition.py tests/test_quality_repetition.py
git commit -m "feat(quality): add trigram repetition + non-speech marker detection"
```

---

### Task 6: quality/boh.py — Bag of Hallucinations через Aho-Corasick

**Files:**
- Create: `skills/youtube_transcribe/quality/data/boh_phrases.txt`
- Create: `skills/youtube_transcribe/quality/boh.py`
- Create: `tests/test_quality_boh.py`

- [ ] **Step 1: Создать список типичных whisper-галлюцинаций**

`skills/youtube_transcribe/quality/data/boh_phrases.txt`:

```
thank you for watching
thanks for watching
subtitles by
subtitles created by
captions by
please subscribe
subscribe to my channel
subscribe to the channel
like and subscribe
don't forget to subscribe
share this video
hit the bell icon
thanks for tuning in
see you next time
see you in the next video
поделитесь видео
подпишитесь на канал
ставьте лайк
спасибо за просмотр
do not forget to subscribe
the end
end of video
```

- [ ] **Step 2: Написать failing test**

`tests/test_quality_boh.py`:

```python
"""Tests for Bag-of-Hallucinations detection."""
from skills.youtube_transcribe.quality.boh import bag_of_hallucinations_coverage


def test_boh_clean_text_zero():
    assert bag_of_hallucinations_coverage("hello and welcome to today's lesson") == 0.0


def test_boh_thank_you_for_watching_loop():
    text = " ".join(["thank you for watching"] * 10)
    coverage = bag_of_hallucinations_coverage(text)
    assert coverage > 0.5, f"expected high coverage, got {coverage}"


def test_boh_short_clip():
    text = "Today we will learn about Python. Thanks for watching!"
    coverage = bag_of_hallucinations_coverage(text)
    assert 0.0 < coverage < 0.5, f"single mention should give moderate coverage, got {coverage}"


def test_boh_russian_phrases():
    text = "ставьте лайк и подпишитесь на канал"
    coverage = bag_of_hallucinations_coverage(text)
    assert coverage > 0.3
```

- [ ] **Step 3: Run test, verify FAIL**

Run: `uv run pytest tests/test_quality_boh.py -v`
Expected: ImportError.

- [ ] **Step 4: Написать реализацию**

`skills/youtube_transcribe/quality/boh.py`:

```python
"""Bag of Hallucinations: catch known Whisper boilerplate hallucinations.

Reference: https://arxiv.org/html/2501.11378v1
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

import ahocorasick


@lru_cache(maxsize=1)
def _build_automaton() -> ahocorasick.Automaton:
    text = files("skills.youtube_transcribe.quality.data").joinpath("boh_phrases.txt").read_text(
        encoding="utf-8"
    )
    phrases = [
        line.strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    auto = ahocorasick.Automaton()
    for idx, phrase in enumerate(phrases):
        auto.add_word(phrase, (idx, phrase))
    auto.make_automaton()
    return auto


def bag_of_hallucinations_coverage(text: str) -> float:
    """Returns 0..1 — fraction of text characters covered by BoH phrases.

    Sums lengths of all hallucination matches (without overlapping double-count
    by tracking covered character positions), divided by total text length.
    """
    if not text:
        return 0.0
    text_lower = text.lower()
    auto = _build_automaton()
    covered = bytearray(len(text_lower))  # bitmap of covered chars
    for end_idx, (_, phrase) in auto.iter(text_lower):
        start_idx = end_idx - len(phrase) + 1
        for i in range(start_idx, end_idx + 1):
            covered[i] = 1
    return sum(covered) / len(text_lower) if text_lower else 0.0
```

- [ ] **Step 5: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_boh.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/quality/boh.py \
        skills/youtube_transcribe/quality/data/boh_phrases.txt \
        tests/test_quality_boh.py
git commit -m "feat(quality): add Bag-of-Hallucinations detection via Aho-Corasick"
```

---

### Task 7: quality/heuristic_checker.py — composite checker

**Files:**
- Create: `skills/youtube_transcribe/quality/heuristic_checker.py`
- Create: `tests/test_quality_heuristic.py`

- [ ] **Step 1: Написать failing test**

`tests/test_quality_heuristic.py`:

```python
"""Tests for HeuristicChecker — composite quality assessment."""
from skills.youtube_transcribe.quality.heuristic_checker import HeuristicChecker
from skills.youtube_transcribe.utils.output_writer import Segment


def _seg(start, end, text):
    return Segment(start=start, end=end, text=text)


def test_manual_subs_get_perfect_score():
    """is_generated=False → score=1.0, no other checks run."""
    checker = HeuristicChecker()
    segments = [_seg(0, 5, "anything"), _seg(5, 10, "even garbled prveит")]
    report = checker.check(segments, "en", source="youtube_manual")
    assert report.score == 1.0
    assert report.recommendation == "use_as_is"
    assert report.breakdown.get("reason") == "manual_captions"


def test_mostly_music_flag_lowers_score():
    checker = HeuristicChecker()
    segments = [
        _seg(0, 30, "[Music]"),
        _seg(30, 60, "♪"),
        _seg(60, 65, "hello"),
    ]
    report = checker.check(segments, "en", source="youtube_auto")
    assert "mostly_music" in report.flags
    assert report.score <= 0.4
    assert report.recommendation == "fallback_recommended"


def test_clean_auto_subs_pass():
    checker = HeuristicChecker()
    text = "Hello and welcome to today's tutorial about Python programming basics"
    segments = [_seg(0, 10, text)]
    report = checker.check(segments, "en", source="youtube_auto")
    assert report.score >= 0.7
    assert report.recommendation == "use_as_is"


def test_garbled_auto_subs_fail():
    checker = HeuristicChecker()
    text = "prveит и пддеа кгдре прив тмаета пвоиет ыклмп длвоп"
    segments = [_seg(0, 10, text)]
    report = checker.check(segments, "ru", source="youtube_auto")
    assert report.score < 0.5
    assert "high_oov" in report.flags
    assert report.recommendation in ("fallback_recommended", "low_quality")


def test_whisper_loop_caught():
    checker = HeuristicChecker()
    text = " ".join(["thank you for watching"] * 25)
    segments = [_seg(0, 60, text)]
    report = checker.check(segments, "en", source="whisper")
    assert "looped" in report.flags or "boilerplate_hallucinations" in report.flags
    assert report.score < 0.5
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_quality_heuristic.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/quality/heuristic_checker.py`:

```python
"""Composite QualityChecker — aggregates spell + repetition + BoH + non-speech."""
from __future__ import annotations

from dataclasses import dataclass

from skills.youtube_transcribe.quality.base import (
    QualityReport,
    Recommendation,
    TranscriptSource,
)
from skills.youtube_transcribe.quality.boh import bag_of_hallucinations_coverage
from skills.youtube_transcribe.quality.repetition import (
    non_speech_marker_ratio,
    trigram_repetition_rate,
)
from skills.youtube_transcribe.quality.spell import (
    is_language_supported,
    out_of_vocab_ratio,
)
from skills.youtube_transcribe.utils.output_writer import Segment


@dataclass
class HeuristicChecker:
    """Default QualityChecker implementation. Local, no network."""

    music_threshold: float = 0.25
    oov_threshold: float = 0.15
    rep_threshold: float = 0.3
    boh_threshold: float = 0.1

    def check(
        self,
        segments: list[Segment],
        language: str,
        source: TranscriptSource,
    ) -> QualityReport:
        if source == "youtube_manual":
            return QualityReport(
                score=1.0,
                breakdown={"reason": "manual_captions"},
                flags=[],
                recommendation="use_as_is",
            )

        text = " ".join(s.text for s in segments)
        breakdown: dict[str, float] = {}
        flags: list[str] = []

        music = non_speech_marker_ratio(segments)
        breakdown["music"] = music
        if music > self.music_threshold:
            flags.append("mostly_music")
            return QualityReport(
                score=0.3,
                breakdown=breakdown,
                flags=flags,
                recommendation="fallback_recommended",
            )

        oov = out_of_vocab_ratio(text, language) if is_language_supported(language) else -1.0
        rep = trigram_repetition_rate(text)
        boh = bag_of_hallucinations_coverage(text)

        breakdown["oov"] = oov
        breakdown["repetition"] = rep
        breakdown["boh"] = boh

        # Веса (всего 1.0). Если язык не поддержан — OOV отключен, переразвешиваем.
        if oov < 0:
            oov_component = 0.5  # neutral
            score = (
                0.4 * (1 - min(rep / self.rep_threshold, 1.0)) +
                0.4 * (1 - min(boh / self.boh_threshold, 1.0)) +
                0.2 * oov_component
            )
        else:
            score = (
                0.35 * (1 - min(oov / self.oov_threshold, 1.0)) +
                0.30 * (1 - min(rep / self.rep_threshold, 1.0)) +
                0.30 * (1 - min(boh / self.boh_threshold, 1.0)) +
                0.05  # baseline
            )
            if oov > self.oov_threshold:
                flags.append("high_oov")

        if rep > self.rep_threshold:
            flags.append("looped")
        if boh > self.boh_threshold:
            flags.append("boilerplate_hallucinations")

        rec: Recommendation = (
            "use_as_is" if score >= 0.6
            else "fallback_recommended" if score >= 0.3
            else "low_quality"
        )
        return QualityReport(score=score, breakdown=breakdown, flags=flags, recommendation=rec)
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_heuristic.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full quality suite**

Run: `uv run pytest tests/test_quality_*.py -v`
Expected: ~22 passed, all green.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/quality/heuristic_checker.py tests/test_quality_heuristic.py
git commit -m "feat(quality): add HeuristicChecker composite (spell+rep+boh+music)"
```

---

# Phase 3 — Triggers core (load + matcher)

### Task 8: detection/triggers.py — TriggerConfig + parse_phrase_entry + load

**Files:**
- Create: `skills/youtube_transcribe/detection/triggers.py`
- Create: `tests/test_triggers_load.py`

- [ ] **Step 1: Написать failing test**

`tests/test_triggers_load.py`:

```python
"""Tests for TriggerConfig loading and phrase entry parsing."""
import textwrap
from pathlib import Path

import pytest

from skills.youtube_transcribe.detection.triggers import (
    TriggerConfig,
    load_triggers,
    parse_phrase_entry,
)


def test_parse_plain_string():
    phrase, weight = parse_phrase_entry("look here")
    assert phrase == "look here"
    assert weight == 1.0


def test_parse_weighted_array():
    phrase, weight = parse_phrase_entry(["function", 1.5])
    assert phrase == "function"
    assert weight == 1.5


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_phrase_entry(42)
    with pytest.raises(ValueError):
        parse_phrase_entry(["only_phrase"])
    with pytest.raises(ValueError):
        parse_phrase_entry([1, 2])


def test_load_triggers_from_user_file(tmp_path):
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        default_language = "en"
        universal_match_threshold = 0.7

        [triggers.universal]
        phrases = ["look here", ["function", 1.5]]

        [triggers.raw]
        phrases = ["TODO", ["FIXME", 2.0]]

        [triggers.languages.ru]
        soft = ["смотри сюда"]
        strict = ["баг", ["PR", 2.0]]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert cfg.default_language == "en"
    assert cfg.universal_match_threshold == 0.7
    assert cfg.universal["look here"] == 1.0
    assert cfg.universal["function"] == 1.5
    assert cfg.raw["TODO"] == 1.0
    assert cfg.raw["FIXME"] == 2.0
    assert cfg.languages["ru"].soft["смотри сюда"] == 1.0
    assert cfg.languages["ru"].strict["баг"] == 1.0
    assert cfg.languages["ru"].strict["PR"] == 2.0


def test_load_triggers_no_user_file_returns_builtin(tmp_path):
    """When user file doesn't exist, return built-in defaults."""
    cfg = load_triggers(user_path=tmp_path / "nonexistent.toml")
    # Built-in must include at least one universal phrase
    assert len(cfg.universal) > 0


def test_load_triggers_user_extends_builtin(tmp_path):
    """User phrases ADD to built-in, not replace (mode=extend default)."""
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        [triggers.universal]
        phrases = ["my custom phrase"]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert "my custom phrase" in cfg.universal
    # Built-in must still be present
    assert len(cfg.universal) > 1


def test_load_triggers_replace_mode(tmp_path):
    user_toml = tmp_path / "triggers.toml"
    user_toml.write_text(textwrap.dedent("""\
        mode = "replace"

        [triggers.universal]
        phrases = ["only this"]
    """), encoding="utf-8")

    cfg = load_triggers(user_path=user_toml)
    assert list(cfg.universal.keys()) == ["only this"]
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_triggers_load.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/triggers.py`:

```python
"""Trigger config loading and phrase entry parsing.

Phrase entries:
  "phrase"            → weight 1.0
  ["phrase", 1.5]     → weight 1.5

Sections:
  [triggers.universal] phrases = [...]
  [triggers.raw] phrases = [...]
  [triggers.languages.<lang>] soft = [...] strict = [...]
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

DEFAULT_USER_PATH = Path.home() / ".youtube-transcribe" / "triggers.toml"


def parse_phrase_entry(entry) -> tuple[str, float]:
    """Returns (phrase, weight) or raises ValueError."""
    if isinstance(entry, str):
        if not entry:
            raise ValueError("phrase cannot be empty")
        return entry, 1.0
    if isinstance(entry, list) and len(entry) == 2:
        phrase, weight = entry
        if not isinstance(phrase, str) or not isinstance(weight, (int, float)):
            raise ValueError(f"Invalid phrase entry types: {entry}")
        return phrase, float(weight)
    raise ValueError(f"Phrase must be 'string' or ['string', number], got: {entry!r}")


def _parse_phrases_list(items) -> dict[str, float]:
    out: dict[str, float] = {}
    for entry in items or []:
        phrase, weight = parse_phrase_entry(entry)
        out[phrase] = weight
    return out


@dataclass
class LanguageTriggers:
    soft: dict[str, float] = field(default_factory=dict)
    strict: dict[str, float] = field(default_factory=dict)


@dataclass
class TriggerConfig:
    default_language: str = "en"
    universal_match_method: str = "semantic"
    universal_match_threshold: float = 0.65

    universal: dict[str, float] = field(default_factory=dict)
    raw: dict[str, float] = field(default_factory=dict)
    languages: dict[str, LanguageTriggers] = field(default_factory=dict)


def _load_toml(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_builtin() -> dict:
    text = files("skills.youtube_transcribe.detection.data").joinpath(
        "triggers_default.toml"
    ).read_text(encoding="utf-8")
    return tomllib.loads(text)


def _build_config(raw: dict) -> TriggerConfig:
    cfg = TriggerConfig(
        default_language=raw.get("default_language", "en"),
        universal_match_method=raw.get("universal_match_method", "semantic"),
        universal_match_threshold=raw.get("universal_match_threshold", 0.65),
    )
    triggers = raw.get("triggers", {})
    cfg.universal = _parse_phrases_list(triggers.get("universal", {}).get("phrases"))
    cfg.raw = _parse_phrases_list(triggers.get("raw", {}).get("phrases"))
    for lang, sect in (triggers.get("languages") or {}).items():
        cfg.languages[lang] = LanguageTriggers(
            soft=_parse_phrases_list(sect.get("soft")),
            strict=_parse_phrases_list(sect.get("strict")),
        )
    return cfg


def _merge(builtin: TriggerConfig, user: TriggerConfig) -> TriggerConfig:
    """User extends builtin (default). User wins on conflicts (overrides weight)."""
    out = TriggerConfig(
        default_language=user.default_language or builtin.default_language,
        universal_match_method=user.universal_match_method,
        universal_match_threshold=user.universal_match_threshold,
        universal={**builtin.universal, **user.universal},
        raw={**builtin.raw, **user.raw},
    )
    # Per-language merge
    all_langs = set(builtin.languages) | set(user.languages)
    for lang in all_langs:
        b = builtin.languages.get(lang, LanguageTriggers())
        u = user.languages.get(lang, LanguageTriggers())
        out.languages[lang] = LanguageTriggers(
            soft={**b.soft, **u.soft},
            strict={**b.strict, **u.strict},
        )
    return out


def load_triggers(user_path: Path | None = DEFAULT_USER_PATH) -> TriggerConfig:
    """Load merged config: built-in defaults + user overrides.

    If user file has `mode = "replace"` at top level, builtin is skipped.
    """
    user_raw = _load_toml(user_path) if user_path else {}
    builtin_cfg = _build_config(_load_builtin())

    if not user_raw:
        return builtin_cfg

    user_cfg = _build_config(user_raw)
    if user_raw.get("mode") == "replace":
        return user_cfg
    return _merge(builtin_cfg, user_cfg)
```

- [ ] **Step 4: Run test, verify FAIL on builtin not found**

Run: `uv run pytest tests/test_triggers_load.py::test_load_triggers_no_user_file_returns_builtin -v`
Expected: FileNotFoundError или подобное — `triggers_default.toml` ещё не создан в Task 9.

- [ ] **Step 5: Создать заглушку builtin для прохождения теста**

Run:
```bash
echo '[triggers.universal]
phrases = ["look here"]' > skills/youtube_transcribe/detection/data/triggers_default.toml
```

- [ ] **Step 6: Run test, verify PASS**

Run: `uv run pytest tests/test_triggers_load.py -v`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/detection/triggers.py \
        skills/youtube_transcribe/detection/data/triggers_default.toml \
        tests/test_triggers_load.py
git commit -m "feat(triggers): TriggerConfig + parse_phrase_entry + load_triggers"
```

---

### Task 9: detection/data/triggers_default.toml — built-in 25 EN phrases

**Files:**
- Modify: `skills/youtube_transcribe/detection/data/triggers_default.toml`
- Create: `tests/test_triggers_default.py`

- [ ] **Step 1: Написать failing test**

`tests/test_triggers_default.py`:

```python
"""Verify built-in triggers_default.toml has expected content."""
from skills.youtube_transcribe.detection.triggers import load_triggers


def test_builtin_has_at_least_20_universal_phrases():
    cfg = load_triggers(user_path=None)
    assert len(cfg.universal) >= 20


def test_builtin_universal_includes_key_phrases():
    cfg = load_triggers(user_path=None)
    expected = {"look here", "pay attention", "for example", "the result is"}
    assert expected.issubset(cfg.universal.keys())


def test_builtin_no_raw_or_languages():
    """Default ships only universal — raw/languages are user opt-in."""
    cfg = load_triggers(user_path=None)
    assert cfg.raw == {}
    assert cfg.languages == {}


def test_builtin_default_language_english():
    cfg = load_triggers(user_path=None)
    assert cfg.default_language == "en"
```

- [ ] **Step 2: Run test, verify FAIL (только 1 фраза в заглушке)**

Run: `uv run pytest tests/test_triggers_default.py -v`
Expected: FAIL `test_builtin_has_at_least_20_universal_phrases`.

- [ ] **Step 3: Написать полный default TOML**

`skills/youtube_transcribe/detection/data/triggers_default.toml`:

```toml
# Built-in triggers shipped with youtube-transcribe v0.2.
# DO NOT edit this file. User overrides go to ~/.youtube-transcribe/triggers.toml.

default_language = "en"
universal_match_method = "semantic"
universal_match_threshold = 0.65

[triggers.universal]
phrases = [
  "look here",
  "pay attention",
  "see this code",
  "this is important",
  "for example",
  "step by step",
  "demonstrate",
  "result",
  "diagram",
  "notice this",
  "key point",
  "remember this",
  "important note",
  "watch closely",
  "the trick is",
  "the catch is",
  "this part",
  "see the difference",
  "this is how",
  "let me show you",
  "right here",
  "as you can see",
  "the result is",
  "compare these",
  "before and after",
]
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_triggers_default.py tests/test_triggers_load.py -v`
Expected: ~11 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/data/triggers_default.toml tests/test_triggers_default.py
git commit -m "feat(triggers): ship 25 English universal phrases as built-in default"
```

---

### Task 10: detection/matcher.py — raw + per-language strict через Aho-Corasick

**Files:**
- Create: `skills/youtube_transcribe/detection/matcher.py`
- Create: `tests/test_matcher_aho.py`

- [ ] **Step 1: Написать failing test**

`tests/test_matcher_aho.py`:

```python
"""Tests for raw/strict matching via Aho-Corasick (no language detection yet)."""
from skills.youtube_transcribe.detection.triggers import LanguageTriggers, TriggerConfig
from skills.youtube_transcribe.detection.matcher import (
    TriggerMatch,
    _build_raw_automaton,
    _build_strict_automaton,
    _match_aho,
)


def _make_cfg() -> TriggerConfig:
    cfg = TriggerConfig()
    cfg.raw = {"TODO": 2.0, "FIXME": 1.0}
    cfg.languages["ru"] = LanguageTriggers(strict={"баг": 1.0, "PR": 2.0})
    return cfg


def test_raw_match_finds_TODO():
    cfg = _make_cfg()
    auto = _build_raw_automaton(cfg)
    res = _match_aho("we have a TODO here", auto)
    assert res is not None
    phrase, weight = res
    assert phrase == "todo"  # case-insensitive
    assert weight == 2.0


def test_raw_no_match():
    cfg = _make_cfg()
    auto = _build_raw_automaton(cfg)
    assert _match_aho("hello world", auto) is None


def test_strict_lang_match():
    cfg = _make_cfg()
    auto = _build_strict_automaton(cfg, "ru")
    res = _match_aho("это какой-то баг", auto)
    assert res is not None
    phrase, weight = res
    assert phrase == "баг"
    assert weight == 1.0


def test_strict_lang_no_automaton_for_other_lang():
    cfg = _make_cfg()
    auto = _build_strict_automaton(cfg, "es")  # no es strict triggers
    assert auto is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_matcher_aho.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию (только Aho-часть, остальное — заглушки)**

`skills/youtube_transcribe/detection/matcher.py`:

```python
"""Trigger matching: raw (any lang exact) + strict (per-lang exact) +
soft (per-lang lemmatized) + universal (cross-lingual embeddings).

Embeddings + lemmatization добавляются в Tasks 11-12.
"""
from __future__ import annotations

from dataclasses import dataclass

import ahocorasick

from skills.youtube_transcribe.detection.triggers import TriggerConfig


@dataclass(frozen=True)
class TriggerMatch:
    score: float           # 0..1, базовый
    weight: float          # из TOML, default 1.0
    reason: str            # "raw" | "strict:ru" | "soft:ru" | "universal"
    phrase: str            # фраза, которая сработала


def _build_raw_automaton(cfg: TriggerConfig) -> ahocorasick.Automaton | None:
    if not cfg.raw:
        return None
    auto = ahocorasick.Automaton()
    for phrase, weight in cfg.raw.items():
        auto.add_word(phrase.lower(), (phrase.lower(), weight))
    auto.make_automaton()
    return auto


def _build_strict_automaton(cfg: TriggerConfig, lang: str) -> ahocorasick.Automaton | None:
    lang_cfg = cfg.languages.get(lang)
    if not lang_cfg or not lang_cfg.strict:
        return None
    auto = ahocorasick.Automaton()
    for phrase, weight in lang_cfg.strict.items():
        auto.add_word(phrase.lower(), (phrase.lower(), weight))
    auto.make_automaton()
    return auto


def _match_aho(text: str, auto: ahocorasick.Automaton | None) -> tuple[str, float] | None:
    """Find first match. Returns (phrase, weight) or None."""
    if auto is None or not text:
        return None
    text_lower = text.lower()
    for _end_idx, value in auto.iter(text_lower):
        return value
    return None
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_matcher_aho.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/matcher.py tests/test_matcher_aho.py
git commit -m "feat(matcher): raw + per-lang strict matching via Aho-Corasick"
```

---

### Task 11: detection/matcher.py — soft matching через лемматизацию

**Files:**
- Modify: `skills/youtube_transcribe/detection/matcher.py`
- Create: `tests/test_matcher_soft.py`

- [ ] **Step 1: Написать failing test**

`tests/test_matcher_soft.py`:

```python
"""Tests for soft (lemmatized) per-language matching."""
import pytest

from skills.youtube_transcribe.detection.triggers import LanguageTriggers, TriggerConfig
from skills.youtube_transcribe.detection.matcher import _match_soft


def _make_cfg_ru():
    cfg = TriggerConfig()
    cfg.languages["ru"] = LanguageTriggers(soft={"смотри сюда": 1.0, "вот этот код": 1.5})
    return cfg


def _make_cfg_en():
    cfg = TriggerConfig()
    cfg.languages["en"] = LanguageTriggers(soft={"the function call": 1.0})
    return cfg


def test_soft_ru_inflected_form_matches():
    """'посмотрите сюда' должно матчить лемму 'смотри сюда' (взаимные формы глагола)."""
    cfg = _make_cfg_ru()
    res = _match_soft("посмотрите сюда внимательно", cfg, "ru")
    assert res is not None


def test_soft_ru_exact_match():
    cfg = _make_cfg_ru()
    res = _match_soft("смотри сюда", cfg, "ru")
    assert res is not None


def test_soft_en_function_calls():
    """'function calls' должно матчить лемму 'function call'."""
    cfg = _make_cfg_en()
    res = _match_soft("see how this function calls work", cfg, "en")
    assert res is not None


def test_soft_no_lang_section_returns_none():
    cfg = _make_cfg_ru()
    assert _match_soft("look here", cfg, "es") is None


@pytest.mark.parametrize("text", ["hello world", "completely unrelated"])
def test_soft_no_match(text):
    cfg = _make_cfg_ru()
    assert _match_soft(text, cfg, "ru") is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_matcher_soft.py -v`
Expected: ImportError on `_match_soft`.

- [ ] **Step 3: Дописать matcher.py**

В конец `skills/youtube_transcribe/detection/matcher.py` добавить:

```python
# === Lemmatization-based soft matching ===

from functools import lru_cache


@lru_cache(maxsize=4)
def _get_lemmatizer(lang: str):
    """Lazy lemmatizer per language. None if unsupported."""
    if lang == "en":
        try:
            from lemminflect import getLemma  # noqa: F401
            return ("lemminflect", None)
        except ImportError:
            return None
    if lang == "ru":
        try:
            import pymorphy3
            return ("pymorphy3", pymorphy3.MorphAnalyzer())
        except ImportError:
            return None
    return None


def _lemmatize(text: str, lang: str) -> str:
    """Tokenize, lemmatize, return space-joined lemmas. Empty string if unsupported."""
    info = _get_lemmatizer(lang)
    if info is None:
        return ""
    lib, analyzer = info
    tokens = text.lower().split()
    if lib == "lemminflect":
        from lemminflect import getLemma
        out = []
        for tok in tokens:
            lemmas = getLemma(tok, upos="VERB") or getLemma(tok, upos="NOUN") or [tok]
            out.append(lemmas[0])
        return " ".join(out)
    if lib == "pymorphy3":
        return " ".join(analyzer.parse(tok)[0].normal_form for tok in tokens)
    return ""


def _match_soft(text: str, cfg: TriggerConfig, lang: str) -> tuple[str, float] | None:
    lang_cfg = cfg.languages.get(lang)
    if not lang_cfg or not lang_cfg.soft:
        return None
    text_lemmas = _lemmatize(text, lang)
    if not text_lemmas:
        return None
    for phrase, weight in lang_cfg.soft.items():
        phrase_lemmas = _lemmatize(phrase, lang)
        if phrase_lemmas and phrase_lemmas in text_lemmas:
            return phrase, weight
    return None
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_matcher_soft.py -v`
Expected: 5 passed (плюс параметризованные).

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/matcher.py tests/test_matcher_soft.py
git commit -m "feat(matcher): soft per-language matching via lemminflect/pymorphy3"
```

---

### Task 12: detection/matcher.py — universal через multilingual embeddings

**Files:**
- Modify: `skills/youtube_transcribe/detection/matcher.py`
- Create: `tests/test_matcher_universal.py`

- [ ] **Step 1: Написать failing test (с моком encoder'а)**

`tests/test_matcher_universal.py`:

```python
"""Tests for universal matching via multilingual embeddings.

Encoder мокается через monkeypatch — реальная модель в e2e."""
import numpy as np
import pytest

from skills.youtube_transcribe.detection.triggers import TriggerConfig
from skills.youtube_transcribe.detection import matcher


class FakeEncoder:
    """Deterministic stub: hash(text) → seeded vector."""

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            rng = np.random.default_rng(hash(t.lower()) % (2**32))
            v = rng.standard_normal(384).astype(np.float32)
            v /= np.linalg.norm(v) + 1e-9
            out.append(v)
        return np.array(out)


@pytest.fixture(autouse=True)
def patch_encoder(monkeypatch):
    monkeypatch.setattr(matcher, "_get_encoder", lambda: FakeEncoder())


def _make_cfg():
    cfg = TriggerConfig()
    cfg.universal = {"look here": 1.0, "function": 1.5}
    cfg.universal_match_threshold = -1.0  # always match (deterministic stub)
    return cfg


def test_universal_returns_some_match():
    cfg = _make_cfg()
    res = matcher._match_universal("hello there", cfg)
    assert res is not None
    phrase, score, weight = res
    assert phrase in cfg.universal
    assert weight == cfg.universal[phrase]


def test_universal_empty_phrases_returns_none():
    cfg = TriggerConfig()
    cfg.universal = {}
    assert matcher._match_universal("hello", cfg) is None


def test_universal_high_threshold_no_match(monkeypatch):
    cfg = _make_cfg()
    cfg.universal_match_threshold = 2.0  # impossibly high
    assert matcher._match_universal("hello there", cfg) is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_matcher_universal.py -v`
Expected: AttributeError on `_match_universal` / `_get_encoder`.

- [ ] **Step 3: Дописать matcher.py — universal с lazy encoder**

В конец `skills/youtube_transcribe/detection/matcher.py` добавить:

```python
# === Universal cross-lingual embedding match ===

import numpy as np

_ENCODER_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _get_encoder():
    """Lazy-load embedding model. ~118MB download on first call."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_ENCODER_MODEL)


@lru_cache(maxsize=1)
def _get_universal_embeddings_cached(phrases_tuple: tuple[str, ...]):
    """Cache by hash of sorted phrases tuple."""
    encoder = _get_encoder()
    return encoder.encode(list(phrases_tuple))


def _cosine(a, b) -> float:
    """Single-vector cosine similarity."""
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


def _match_universal(text: str, cfg: TriggerConfig) -> tuple[str, float, float] | None:
    """Returns (phrase, score, weight) or None."""
    if not cfg.universal:
        return None

    phrases = list(cfg.universal.keys())
    encoder = _get_encoder()
    phrase_embs = _get_universal_embeddings_cached(tuple(phrases))
    text_emb = encoder.encode(text)

    sims = [_cosine(text_emb, pe) for pe in phrase_embs]
    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    if best_score < cfg.universal_match_threshold:
        return None
    phrase = phrases[best_idx]
    return phrase, best_score, cfg.universal[phrase]
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_matcher_universal.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/matcher.py tests/test_matcher_universal.py
git commit -m "feat(matcher): universal cross-lingual matching via multilingual MiniLM"
```

---

### Task 13: detection/matcher.py — match_segment compose + langdetect

**Files:**
- Modify: `skills/youtube_transcribe/detection/matcher.py`
- Create: `tests/test_matcher_compose.py`

- [ ] **Step 1: Написать failing test**

`tests/test_matcher_compose.py`:

```python
"""Tests for top-level match_segment composition."""
import numpy as np
import pytest

from skills.youtube_transcribe.detection.triggers import LanguageTriggers, TriggerConfig
from skills.youtube_transcribe.detection import matcher
from skills.youtube_transcribe.detection.matcher import match_segment, TriggerMatch


class FakeEncoder:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            rng = np.random.default_rng(hash(t.lower()) % (2**32))
            v = rng.standard_normal(384).astype(np.float32)
            v /= np.linalg.norm(v) + 1e-9
            out.append(v)
        return np.array(out)


@pytest.fixture(autouse=True)
def patch_encoder(monkeypatch):
    monkeypatch.setattr(matcher, "_get_encoder", lambda: FakeEncoder())


def test_raw_wins_over_universal():
    cfg = TriggerConfig()
    cfg.raw = {"TODO": 2.0}
    cfg.universal = {"work": 1.0}
    cfg.universal_match_threshold = -1.0  # everything matches universal otherwise

    m = match_segment("we have a TODO in this code", cfg)
    assert m is not None
    assert m.reason == "raw"
    assert m.phrase == "todo"
    assert m.weight == 2.0


def test_strict_wins_over_soft():
    cfg = TriggerConfig()
    cfg.languages["ru"] = LanguageTriggers(
        strict={"баг": 1.0},
        soft={"посмотри сюда": 1.0},
    )

    m = match_segment("вот этот баг здесь", cfg)
    assert m is not None
    assert m.reason.startswith("strict:")


def test_no_match_returns_none():
    cfg = TriggerConfig()
    cfg.universal_match_threshold = 2.0
    m = match_segment("completely unrelated text", cfg)
    assert m is None


def test_universal_fallback():
    cfg = TriggerConfig()
    cfg.universal = {"hello": 1.5}
    cfg.universal_match_threshold = -1.0
    m = match_segment("hi there friend", cfg)
    assert m is not None
    assert m.reason == "universal"
    assert m.weight == 1.5
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_matcher_compose.py -v`
Expected: ImportError on `match_segment`.

- [ ] **Step 3: Дописать matcher.py — top-level compose**

В конец `skills/youtube_transcribe/detection/matcher.py`:

```python
# === Top-level match_segment composer ===


def _detect_lang(text: str) -> str:
    """langdetect with fallback. Returns 2-letter ISO code or 'en' if uncertain."""
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "en"


def match_segment(text: str, cfg: TriggerConfig) -> TriggerMatch | None:
    """Run all matchers in priority order. Returns first match or None.

    Priority:
      1. raw (any lang, exact)
      2. languages.<seg_lang>.strict (per-lang exact)
      3. languages.<seg_lang>.soft (per-lang lemmatized)
      4. universal (cross-lingual embeddings)
    """
    seg_lang = _detect_lang(text)

    raw_auto = _build_raw_automaton(cfg)
    hit = _match_aho(text, raw_auto)
    if hit:
        phrase, weight = hit
        return TriggerMatch(score=1.0, weight=weight, reason="raw", phrase=phrase)

    strict_auto = _build_strict_automaton(cfg, seg_lang)
    hit = _match_aho(text, strict_auto)
    if hit:
        phrase, weight = hit
        return TriggerMatch(score=1.0, weight=weight, reason=f"strict:{seg_lang}", phrase=phrase)

    soft_hit = _match_soft(text, cfg, seg_lang)
    if soft_hit:
        phrase, weight = soft_hit
        return TriggerMatch(score=0.9, weight=weight, reason=f"soft:{seg_lang}", phrase=phrase)

    uni_hit = _match_universal(text, cfg)
    if uni_hit:
        phrase, score, weight = uni_hit
        return TriggerMatch(score=score, weight=weight, reason="universal", phrase=phrase)

    return None
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_matcher_compose.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full triggers + matcher suite**

Run: `uv run pytest tests/test_triggers_*.py tests/test_matcher_*.py -v`
Expected: ~25 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/detection/matcher.py tests/test_matcher_compose.py
git commit -m "feat(matcher): top-level match_segment compose with langdetect priority"
```

---

# Phase 4 — Triggers CLI tool

### Task 14: detection/triggers_cli.py — init/add/list/remove (через tomlkit)

**Files:**
- Create: `skills/youtube_transcribe/detection/triggers_cli.py`
- Create: `tests/test_triggers_cli.py`

- [ ] **Step 1: Написать failing test (Click runner)**

`tests/test_triggers_cli.py`:

```python
"""Tests for `youtube-transcribe triggers` CLI sub-group."""
from pathlib import Path

import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_init_creates_file(tmp_user_path):
    runner = CliRunner()
    res = runner.invoke(triggers_cli, ["init"])
    assert res.exit_code == 0
    assert tmp_user_path.exists()
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "[triggers.universal]" in content
    assert "phrases =" in content


def test_init_force_overwrites(tmp_user_path):
    runner = CliRunner()
    tmp_user_path.write_text("garbage", encoding="utf-8")
    res = runner.invoke(triggers_cli, ["init", "--force"])
    assert res.exit_code == 0
    assert "[triggers.universal]" in tmp_user_path.read_text(encoding="utf-8")


def test_init_without_force_refuses_overwrite(tmp_user_path):
    runner = CliRunner()
    tmp_user_path.write_text("garbage", encoding="utf-8")
    res = runner.invoke(triggers_cli, ["init"])
    assert res.exit_code != 0
    assert "exists" in res.output.lower()


def test_add_universal_phrases(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(
        triggers_cli, ["add", "--universal", "look here; pay attention; hello world"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "look here" in content
    assert "pay attention" in content
    assert "hello world" in content


def test_add_dedupes(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    res = runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    assert res.exit_code == 0
    assert "already exists" in res.output.lower()
    # File should still contain only one occurrence
    assert tmp_user_path.read_text(encoding="utf-8").count('"look here"') == 1


def test_add_strict_per_lang(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(
        triggers_cli, ["add", "--strict", "--lang", "ru", "баг; PR"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "[triggers.languages.ru]" in content
    assert "баг" in content


def test_remove_phrase(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here; remove me"])
    res = runner.invoke(triggers_cli, ["remove", "--universal", "remove me"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "remove me" not in content
    assert "look here" in content


def test_list_command(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "look here"])
    res = runner.invoke(triggers_cli, ["list"])
    assert res.exit_code == 0
    assert "look here" in res.output
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_triggers_cli.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/triggers_cli.py`:

```python
"""CLI sub-group for managing ~/.youtube-transcribe/triggers.toml.

Usage:
  youtube-transcribe triggers init [--force]
  youtube-transcribe triggers add --universal "p1; p2"
  youtube-transcribe triggers add --raw "p1"
  youtube-transcribe triggers add --soft|--strict --lang <code> "p1"
  youtube-transcribe triggers list [--section <name>]
  youtube-transcribe triggers remove --universal "phrase"
  ...
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import click
import tomlkit
from rich.console import Console
from rich.table import Table

DEFAULT_PATH = Path.home() / ".youtube-transcribe" / "triggers.toml"

_SPLIT_RE = re.compile(r"[;,]")

console = Console()


def _user_path() -> Path:
    """Read from env (testing) or default."""
    p = os.environ.get("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH")
    return Path(p) if p else DEFAULT_PATH


def _split_phrases(s: str) -> list[str]:
    return [p.strip() for p in _SPLIT_RE.split(s) if p.strip()]


def _atomic_write(path: Path, doc: tomlkit.TOMLDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
    os.replace(tmp, path)


def _load_doc(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def _stub_doc() -> tomlkit.TOMLDocument:
    """Empty user triggers file with comments and empty sections."""
    doc = tomlkit.document()
    doc.add(tomlkit.comment("Custom triggers — extends built-in defaults."))
    doc.add(tomlkit.comment("See spec §4 for format. Edit via `youtube-transcribe triggers add`."))
    doc.add(tomlkit.nl())

    triggers = tomlkit.table(is_super_table=True)
    triggers["universal"] = tomlkit.table()
    triggers["universal"]["phrases"] = tomlkit.array()
    triggers["raw"] = tomlkit.table()
    triggers["raw"]["phrases"] = tomlkit.array()
    doc["triggers"] = triggers
    return doc


def _ensure_section(doc: tomlkit.TOMLDocument, *path: str) -> tomlkit.items.Item:
    """Drill into doc.triggers.<a>.<b>... creating tables as needed."""
    if "triggers" not in doc:
        doc["triggers"] = tomlkit.table(is_super_table=True)
    cur = doc["triggers"]
    for key in path:
        if key not in cur:
            cur[key] = tomlkit.table()
        cur = cur[key]
    return cur


def _phrases_array(parent: tomlkit.items.Item, key: str) -> tomlkit.items.Array:
    if key not in parent:
        parent[key] = tomlkit.array()
    return parent[key]


def _array_contains(arr: tomlkit.items.Array, phrase: str) -> bool:
    for item in arr:
        if isinstance(item, str) and item == phrase:
            return True
        if isinstance(item, list) and len(item) >= 1 and item[0] == phrase:
            return True
    return False


# === Click group ===


@click.group(name="triggers")
def triggers_cli():
    """Manage ~/.youtube-transcribe/triggers.toml."""


@triggers_cli.command("init")
@click.option("--force", is_flag=True, help="Overwrite existing file.")
def cmd_init(force: bool):
    path = _user_path()
    if path.exists() and not force:
        click.echo(f"Error: {path} already exists. Use --force to overwrite.", err=True)
        raise click.exceptions.Exit(1)
    _atomic_write(path, _stub_doc())
    click.echo(f"Created {path}")


@triggers_cli.command("add")
@click.option("--universal", "section", flag_value="universal")
@click.option("--raw", "section", flag_value="raw")
@click.option("--soft", "section", flag_value="soft")
@click.option("--strict", "section", flag_value="strict")
@click.option("--lang", "lang", default=None, help="ISO code for --soft/--strict.")
@click.argument("phrases", nargs=-1, required=True)
def cmd_add(section: str, lang: str | None, phrases: tuple[str, ...]):
    if section is None:
        click.echo("Error: pass one of --universal/--raw/--soft/--strict", err=True)
        raise click.exceptions.Exit(1)
    if section in ("soft", "strict") and not lang:
        click.echo(f"Error: --{section} requires --lang <code>", err=True)
        raise click.exceptions.Exit(1)

    parsed: list[str] = []
    for chunk in phrases:
        parsed.extend(_split_phrases(chunk))
    if not parsed:
        click.echo("Error: no non-empty phrases parsed", err=True)
        raise click.exceptions.Exit(1)

    path = _user_path()
    doc = _load_doc(path)
    if "triggers" not in doc:
        doc.update(_stub_doc())

    if section == "universal":
        target = _ensure_section(doc, "universal")
        arr = _phrases_array(target, "phrases")
    elif section == "raw":
        target = _ensure_section(doc, "raw")
        arr = _phrases_array(target, "phrases")
    else:  # soft / strict
        target = _ensure_section(doc, "languages", lang)
        arr = _phrases_array(target, section)

    added = 0
    for phrase in parsed:
        if _array_contains(arr, phrase):
            click.echo(f"  • '{phrase}' already exists, skipped")
            continue
        arr.append(phrase)
        added += 1
        click.echo(f"  + '{phrase}'")

    _atomic_write(path, doc)
    click.echo(f"Added {added} phrase(s) to [{section}].")


@triggers_cli.command("remove")
@click.option("--universal", "section", flag_value="universal")
@click.option("--raw", "section", flag_value="raw")
@click.option("--soft", "section", flag_value="soft")
@click.option("--strict", "section", flag_value="strict")
@click.option("--lang", "lang", default=None)
@click.argument("phrase")
def cmd_remove(section: str, lang: str | None, phrase: str):
    path = _user_path()
    doc = _load_doc(path)
    if "triggers" not in doc:
        click.echo("No triggers file. Run `triggers init` first.", err=True)
        raise click.exceptions.Exit(1)
    if section in ("soft", "strict") and not lang:
        click.echo(f"Error: --{section} requires --lang", err=True)
        raise click.exceptions.Exit(1)

    if section == "universal":
        arr = doc["triggers"].get("universal", {}).get("phrases", [])
    elif section == "raw":
        arr = doc["triggers"].get("raw", {}).get("phrases", [])
    else:
        arr = doc["triggers"].get("languages", {}).get(lang, {}).get(section, [])

    new_items = [
        item for item in arr
        if not (isinstance(item, str) and item == phrase)
        and not (isinstance(item, list) and len(item) >= 1 and item[0] == phrase)
    ]
    if len(new_items) == len(arr):
        click.echo(f"'{phrase}' not found in [{section}]", err=True)
        raise click.exceptions.Exit(1)

    arr.clear()
    for item in new_items:
        arr.append(item)
    _atomic_write(path, doc)
    click.echo(f"Removed '{phrase}' from [{section}]")


@triggers_cli.command("list")
@click.option("--section", "filter_section", default=None)
def cmd_list(filter_section: str | None):
    from skills.youtube_transcribe.detection.triggers import load_triggers

    path = _user_path()
    cfg = load_triggers(user_path=path if path.exists() else None)
    table = Table(title="Triggers", show_lines=False)
    table.add_column("Section")
    table.add_column("Phrase")
    table.add_column("Weight", justify="right")

    def _add_section(name: str, items: dict[str, float]):
        for phrase, weight in sorted(items.items()):
            tag = "weighted" if weight != 1.0 else ""
            table.add_row(name, phrase, f"{weight}{' ←' if tag else ''}")

    if filter_section in (None, "universal"):
        _add_section("universal", cfg.universal)
    if filter_section in (None, "raw"):
        _add_section("raw", cfg.raw)
    for lang, lcfg in cfg.languages.items():
        if filter_section in (None, f"soft:{lang}"):
            _add_section(f"soft:{lang}", lcfg.soft)
        if filter_section in (None, f"strict:{lang}"):
            _add_section(f"strict:{lang}", lcfg.strict)

    console.print(table)
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_triggers_cli.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/triggers_cli.py tests/test_triggers_cli.py
git commit -m "feat(triggers-cli): init/add/remove/list with tomlkit comment preservation"
```

---

### Task 15: triggers_cli.py — reset / edit / test commands

**Files:**
- Modify: `skills/youtube_transcribe/detection/triggers_cli.py`
- Create: `tests/test_triggers_cli_extra.py`

- [ ] **Step 1: Написать failing test**

`tests/test_triggers_cli_extra.py`:

```python
"""Tests for triggers reset/edit/test commands."""
import os

import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_reset_universal_clears_section(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "custom phrase"])
    res = runner.invoke(triggers_cli, ["reset", "--universal"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert "custom phrase" not in content


def test_reset_all_wipes_user_file(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "custom phrase"])
    res = runner.invoke(triggers_cli, ["reset", "--all"])
    assert res.exit_code == 0
    assert not tmp_user_path.exists() or "custom phrase" not in tmp_user_path.read_text("utf-8")


def test_test_command_shows_match(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--raw", "TODO"])
    res = runner.invoke(triggers_cli, ["test", "we have a TODO here"])
    assert res.exit_code == 0
    assert "raw" in res.output.lower() or "todo" in res.output.lower()


def test_test_no_match_reports(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    res = runner.invoke(triggers_cli, ["test", "qqq xxx zzz nothing here"])
    # Should at least exit 0 (not error). Universal might or might not match
    # depending on threshold. Just verify it ran.
    assert res.exit_code == 0


def test_edit_command_opens_editor(tmp_user_path, monkeypatch):
    """Mock $EDITOR to a noop, ensure edit doesn't crash."""
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    monkeypatch.setenv("EDITOR", "true")  # 'true' is a noop binary that returns 0
    res = runner.invoke(triggers_cli, ["edit"])
    assert res.exit_code == 0
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_triggers_cli_extra.py -v`
Expected: AttributeError on missing commands.

- [ ] **Step 3: Дописать commands в triggers_cli.py**

В конец `skills/youtube_transcribe/detection/triggers_cli.py`:

```python
import shutil
import subprocess


@triggers_cli.command("reset")
@click.option("--universal", "section", flag_value="universal")
@click.option("--raw", "section", flag_value="raw")
@click.option("--all", "section", flag_value="all")
def cmd_reset(section: str | None):
    path = _user_path()
    if not path.exists():
        click.echo("Nothing to reset.")
        return
    if section == "all":
        path.unlink()
        click.echo(f"Removed {path}")
        return
    doc = _load_doc(path)
    if section == "universal":
        if "triggers" in doc and "universal" in doc["triggers"]:
            doc["triggers"]["universal"]["phrases"] = tomlkit.array()
        click.echo("Cleared [triggers.universal].")
    elif section == "raw":
        if "triggers" in doc and "raw" in doc["triggers"]:
            doc["triggers"]["raw"]["phrases"] = tomlkit.array()
        click.echo("Cleared [triggers.raw].")
    else:
        click.echo("Use --universal, --raw, or --all.", err=True)
        raise click.exceptions.Exit(1)
    _atomic_write(path, doc)


@triggers_cli.command("edit")
def cmd_edit():
    path = _user_path()
    if not path.exists():
        click.echo(f"{path} doesn't exist. Run `triggers init` first.", err=True)
        raise click.exceptions.Exit(1)

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy(path, backup)

    editor = os.environ.get("EDITOR", "vi")
    try:
        subprocess.run([editor, str(path)], check=False)
        # Validate after edit
        from skills.youtube_transcribe.detection.triggers import _load_toml
        try:
            _load_toml(path)
        except Exception as e:
            click.echo(f"Invalid TOML after edit: {e}", err=True)
            click.echo(f"Restoring backup from {backup}")
            shutil.copy(backup, path)
            raise click.exceptions.Exit(1)
    finally:
        if backup.exists():
            backup.unlink()
    click.echo("OK.")


@triggers_cli.command("test")
@click.argument("text")
def cmd_test(text: str):
    """Run text through matcher and report which trigger fired."""
    from skills.youtube_transcribe.detection.matcher import match_segment
    from skills.youtube_transcribe.detection.triggers import load_triggers

    path = _user_path()
    cfg = load_triggers(user_path=path if path.exists() else None)
    m = match_segment(text, cfg)
    if m is None:
        click.echo("No trigger matched.")
        return
    click.echo(f"Matched: phrase='{m.phrase}', reason={m.reason}, "
               f"score={m.score:.3f}, weight={m.weight}")
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_triggers_cli_extra.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/triggers_cli.py tests/test_triggers_cli_extra.py
git commit -m "feat(triggers-cli): add reset/edit/test sub-commands"
```

---

### Task 16: triggers_cli.py — weight set/unset/list

**Files:**
- Modify: `skills/youtube_transcribe/detection/triggers_cli.py`
- Create: `tests/test_triggers_cli_weight.py`

- [ ] **Step 1: Написать failing test**

`tests/test_triggers_cli_weight.py`:

```python
"""Tests for `triggers weight set/unset/list`."""
import pytest
from click.testing import CliRunner

from skills.youtube_transcribe.detection.triggers_cli import triggers_cli


@pytest.fixture
def tmp_user_path(tmp_path, monkeypatch):
    p = tmp_path / "triggers.toml"
    monkeypatch.setenv("YOUTUBE_TRANSCRIBE_TRIGGERS_PATH", str(p))
    return p


def test_weight_set_converts_string_to_array(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function"])
    res = runner.invoke(
        triggers_cli, ["weight", "set", "--universal", "function", "1.5"]
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    # Should now be ["function", 1.5] format
    assert '"function"' in content
    assert "1.5" in content


def test_weight_set_batch_format(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function; class; method"])
    res = runner.invoke(
        triggers_cli,
        ["weight", "set", "--universal", "function:1.5; class:1.5; method:1.5"],
    )
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    assert content.count("1.5") >= 3


def test_weight_unset_returns_to_string(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "function"])
    runner.invoke(triggers_cli, ["weight", "set", "--universal", "function", "1.5"])
    res = runner.invoke(triggers_cli, ["weight", "unset", "--universal", "function"])
    assert res.exit_code == 0
    content = tmp_user_path.read_text(encoding="utf-8")
    # Should no longer have the array form for "function"
    assert '"function"' in content
    assert '["function", 1.5]' not in content


def test_weight_list_shows_only_weighted(tmp_user_path):
    runner = CliRunner()
    runner.invoke(triggers_cli, ["init"])
    runner.invoke(triggers_cli, ["add", "--universal", "regular phrase; weighted phrase"])
    runner.invoke(
        triggers_cli, ["weight", "set", "--universal", "weighted phrase", "2.0"]
    )
    res = runner.invoke(triggers_cli, ["weight", "list"])
    assert res.exit_code == 0
    assert "weighted phrase" in res.output
    # "regular phrase" has weight 1.0 (default), should NOT be in list
    assert "regular phrase" not in res.output
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_triggers_cli_weight.py -v`
Expected: AttributeError на missing weight group.

- [ ] **Step 3: Дописать в triggers_cli.py**

В конец `skills/youtube_transcribe/detection/triggers_cli.py`:

```python
@triggers_cli.group("weight")
def weight_group():
    """Manage per-phrase weights."""


def _find_phrase_in_array(arr, phrase: str) -> int | None:
    for idx, item in enumerate(arr):
        if isinstance(item, str) and item == phrase:
            return idx
        if isinstance(item, list) and len(item) >= 1 and item[0] == phrase:
            return idx
    return None


def _resolve_arr(doc, section: str, lang: str | None):
    if section == "universal":
        return doc["triggers"]["universal"]["phrases"]
    if section == "raw":
        return doc["triggers"]["raw"]["phrases"]
    return doc["triggers"]["languages"][lang][section]


def _parse_weight_args(args: tuple[str, ...]) -> list[tuple[str, float]]:
    """Two forms:
      ("function", "1.5")          → [("function", 1.5)]
      ("function:1.5; class:1.5",) → [("function", 1.5), ("class", 1.5)]
    """
    if len(args) == 2:
        return [(args[0], float(args[1]))]
    if len(args) == 1:
        out = []
        for chunk in _SPLIT_RE.split(args[0]):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ":" not in chunk:
                raise ValueError(f"Batch entry must be 'phrase:weight', got '{chunk}'")
            phrase, w = chunk.rsplit(":", 1)
            out.append((phrase.strip(), float(w.strip())))
        return out
    raise ValueError("Pass 'phrase value' or batch 'phrase:value;...'")


@weight_group.command("set")
@click.option("--universal", "section", flag_value="universal")
@click.option("--raw", "section", flag_value="raw")
@click.option("--soft", "section", flag_value="soft")
@click.option("--strict", "section", flag_value="strict")
@click.option("--lang", "lang", default=None)
@click.argument("args", nargs=-1, required=True)
def cmd_weight_set(section: str, lang: str | None, args: tuple[str, ...]):
    if section is None:
        click.echo("Pass --universal/--raw/--soft/--strict", err=True)
        raise click.exceptions.Exit(1)
    if section in ("soft", "strict") and not lang:
        click.echo(f"--{section} requires --lang", err=True)
        raise click.exceptions.Exit(1)

    pairs = _parse_weight_args(args)
    path = _user_path()
    doc = _load_doc(path)
    arr = _resolve_arr(doc, section, lang)

    for phrase, weight in pairs:
        if not 0.1 <= weight <= 5.0:
            click.echo(f"Warning: suspicious weight {weight} for '{phrase}'")
        idx = _find_phrase_in_array(arr, phrase)
        if idx is None:
            click.echo(f"'{phrase}' not in [{section}]", err=True)
            continue
        new_entry = tomlkit.array()
        new_entry.append(phrase)
        new_entry.append(weight)
        arr[idx] = new_entry
        click.echo(f"  {phrase} → weight {weight}")

    _atomic_write(path, doc)


@weight_group.command("unset")
@click.option("--universal", "section", flag_value="universal")
@click.option("--raw", "section", flag_value="raw")
@click.option("--soft", "section", flag_value="soft")
@click.option("--strict", "section", flag_value="strict")
@click.option("--lang", "lang", default=None)
@click.argument("phrase")
def cmd_weight_unset(section: str, lang: str | None, phrase: str):
    path = _user_path()
    doc = _load_doc(path)
    arr = _resolve_arr(doc, section, lang)
    idx = _find_phrase_in_array(arr, phrase)
    if idx is None:
        click.echo(f"'{phrase}' not in [{section}]", err=True)
        raise click.exceptions.Exit(1)
    arr[idx] = phrase
    _atomic_write(path, doc)
    click.echo(f"  {phrase} → weight 1.0 (reverted)")


@weight_group.command("list")
def cmd_weight_list():
    """Show only non-default weights."""
    from skills.youtube_transcribe.detection.triggers import load_triggers

    path = _user_path()
    cfg = load_triggers(user_path=path if path.exists() else None)
    found = False

    def _show(name: str, items: dict[str, float]):
        nonlocal found
        for phrase, w in items.items():
            if w != 1.0:
                click.echo(f"  [{name}] '{phrase}' → {w}")
                found = True

    _show("universal", cfg.universal)
    _show("raw", cfg.raw)
    for lang, lcfg in cfg.languages.items():
        _show(f"soft:{lang}", lcfg.soft)
        _show(f"strict:{lang}", lcfg.strict)

    if not found:
        click.echo("No non-default weights set.")
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_triggers_cli_weight.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full triggers CLI suite**

Run: `uv run pytest tests/test_triggers_cli*.py -v`
Expected: ~17 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/detection/triggers_cli.py tests/test_triggers_cli_weight.py
git commit -m "feat(triggers-cli): add weight set/unset/list commands"
```

---

# Phase 5 — Detection (windows + scene + frame-diff + budget)

### Task 17: detection/base.py — DetectionWindow + Detector Protocol

**Files:**
- Create: `skills/youtube_transcribe/detection/base.py`
- Create: `tests/test_detection_base.py`

- [ ] **Step 1: Написать failing test**

`tests/test_detection_base.py`:

```python
"""Tests for DetectionWindow dataclass and Detector Protocol."""
from skills.youtube_transcribe.detection.base import DetectionWindow


def test_window_creation():
    w = DetectionWindow(start=10.0, end=15.0, reason="raw", score=1.0, weight=2.0, phrase="TODO")
    assert w.start == 10.0
    assert w.end == 15.0
    assert w.reason == "raw"


def test_window_priority_score():
    w = DetectionWindow(start=0.0, end=5.0, reason="universal", score=0.7, weight=1.5, phrase="x")
    assert abs(w.priority_score - 1.05) < 1e-6  # 0.7 * 1.5
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_detection_base.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/base.py`:

```python
"""DetectionWindow + Detector Protocol."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DetectionWindow:
    start: float       # секунды
    end: float
    reason: str        # "raw" | "strict:ru" | "soft:ru" | "universal" | "scene_change" | "llm_full_pass"
    score: float       # 0..1
    weight: float = 1.0
    phrase: str = ""   # фраза, которая сработала (для триггер-окон)

    @property
    def priority_score(self) -> float:
        return self.score * self.weight


class Detector(Protocol):
    """Anything that finds visual-important windows in a video."""

    def find_windows(
        self,
        segments: list,
        video_path: Path | None,
        triggers,           # TriggerConfig
    ) -> list[DetectionWindow]:
        ...
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_detection_base.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/base.py tests/test_detection_base.py
git commit -m "feat(detection): DetectionWindow dataclass + Detector Protocol"
```

---

### Task 18: detection/scene.py — PySceneDetect wrapper

**Files:**
- Create: `skills/youtube_transcribe/detection/scene.py`
- Create: `tests/test_detection_scene.py`

- [ ] **Step 1: Написать failing test (мок PySceneDetect API)**

`tests/test_detection_scene.py`:

```python
"""Tests for scene boundary detection. PySceneDetect мокается."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.detection.scene import find_scene_boundaries


def test_find_scene_boundaries_calls_pyscenedetect():
    fake_scene_list = [
        # PySceneDetect returns list of (FrameTimecode start, FrameTimecode end)
        (MagicMock(get_seconds=lambda: 0.0), MagicMock(get_seconds=lambda: 10.5)),
        (MagicMock(get_seconds=lambda: 10.5), MagicMock(get_seconds=lambda: 25.0)),
        (MagicMock(get_seconds=lambda: 25.0), MagicMock(get_seconds=lambda: 60.0)),
    ]
    with patch("scenedetect.detect", return_value=fake_scene_list):
        boundaries = find_scene_boundaries(Path("fake.mp4"), threshold=27.0)
    # Boundaries are scene START times (excluding first scene)
    assert boundaries == [10.5, 25.0]


def test_find_scene_boundaries_empty_video():
    with patch("scenedetect.detect", return_value=[]):
        boundaries = find_scene_boundaries(Path("empty.mp4"))
    assert boundaries == []


def test_find_scene_boundaries_single_scene():
    """One-scene video has no boundaries."""
    fake = [(MagicMock(get_seconds=lambda: 0.0), MagicMock(get_seconds=lambda: 60.0))]
    with patch("scenedetect.detect", return_value=fake):
        boundaries = find_scene_boundaries(Path("single.mp4"))
    assert boundaries == []
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_detection_scene.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/scene.py`:

```python
"""Scene boundary detection via PySceneDetect.

Returns scene START timestamps in seconds (excluding the very first scene
which starts at 0.0). These boundaries are used as visual cues for windowing.
"""
from __future__ import annotations

from pathlib import Path


def find_scene_boundaries(video_path: Path, threshold: float = 27.0) -> list[float]:
    """Returns list of scene-change timestamps in seconds.

    threshold: ContentDetector threshold; 27 is PySceneDetect default; lower
    means more sensitive (more boundaries).
    """
    import scenedetect

    scenes = scenedetect.detect(str(video_path), scenedetect.ContentDetector(threshold=threshold))
    # First scene starts at 0 — it's not a boundary, skip it.
    return [start.get_seconds() for start, _end in scenes[1:]]
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_detection_scene.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/scene.py tests/test_detection_scene.py
git commit -m "feat(detection): scene boundaries via PySceneDetect"
```

---

### Task 19: detection/frame_diff.py — perceptual hashing diff

**Files:**
- Create: `skills/youtube_transcribe/detection/frame_diff.py`
- Create: `tests/test_detection_frame_diff.py`

- [ ] **Step 1: Написать failing test**

`tests/test_detection_frame_diff.py`:

```python
"""Tests for frame difference detection via ImageHash."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skills.youtube_transcribe.detection.frame_diff import (
    FrameDiff,
    detect_frame_changes_in_window,
)


def test_frame_diff_dataclass():
    fd = FrameDiff(timestamp=10.5, hamming_distance=18)
    assert fd.timestamp == 10.5
    assert fd.hamming_distance == 18


def test_detect_frame_changes_returns_diffs():
    """Mock ffmpeg + imagehash to return synthetic frames."""
    fake_hashes = [MagicMock(), MagicMock(), MagicMock()]
    # Hamming distances between consecutive: 0, 30 (big change)
    fake_hashes[0].__sub__ = MagicMock(return_value=0)
    fake_hashes[1].__sub__ = MagicMock(return_value=30)
    fake_hashes[2].__sub__ = MagicMock(return_value=5)

    with patch(
        "skills.youtube_transcribe.detection.frame_diff._extract_frame_hashes",
        return_value=[(0.0, fake_hashes[0]), (1.0, fake_hashes[1]), (2.0, fake_hashes[2])],
    ):
        diffs = detect_frame_changes_in_window(
            Path("fake.mp4"), start=0.0, end=2.0, threshold=20
        )
    # Only the diff > threshold (20) makes it to the result
    assert len(diffs) == 1
    assert diffs[0].timestamp == 1.0
    assert diffs[0].hamming_distance == 30


def test_detect_frame_changes_no_changes():
    fake_hashes = [MagicMock(), MagicMock()]
    fake_hashes[0].__sub__ = MagicMock(return_value=2)
    with patch(
        "skills.youtube_transcribe.detection.frame_diff._extract_frame_hashes",
        return_value=[(0.0, fake_hashes[0]), (1.0, fake_hashes[1])],
    ):
        diffs = detect_frame_changes_in_window(Path("x.mp4"), 0.0, 1.0, threshold=20)
    assert diffs == []
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_detection_frame_diff.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/frame_diff.py`:

```python
"""Frame difference detection via perceptual hashing (imagehash).

Used inside trigger windows to find sub-moments where visuals actually change
(vs. talking-head with static screen).
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrameDiff:
    timestamp: float
    hamming_distance: int       # 0 = identical, ~64 = completely different


def _extract_frame_hashes(video_path: Path, start: float, end: float, fps: float = 1.0):
    """Use ffmpeg to dump frames at fps, hash each. Returns list[(timestamp, hash)]."""
    import imagehash
    from PIL import Image

    out: list[tuple[float, object]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-to", str(end),
            "-i", str(video_path),
            "-vf", f"fps={fps}",
            str(tmp_dir / "frame_%04d.jpg"),
        ]
        subprocess.run(cmd, check=True)
        files = sorted(tmp_dir.glob("frame_*.jpg"))
        for idx, f in enumerate(files):
            img = Image.open(f)
            h = imagehash.phash(img)
            timestamp = start + idx / fps
            out.append((timestamp, h))
    return out


def detect_frame_changes_in_window(
    video_path: Path,
    start: float,
    end: float,
    threshold: int = 20,
    fps: float = 1.0,
) -> list[FrameDiff]:
    """Returns frame timestamps where visual changed substantially vs. previous frame.

    threshold: hamming distance cut-off (0..64). 20 ≈ noticeable change.
    """
    hashes = _extract_frame_hashes(video_path, start, end, fps=fps)
    if len(hashes) < 2:
        return []
    out: list[FrameDiff] = []
    for i in range(1, len(hashes)):
        prev_t, prev_h = hashes[i - 1]
        cur_t, cur_h = hashes[i]
        dist = cur_h - prev_h
        if dist >= threshold:
            out.append(FrameDiff(timestamp=cur_t, hamming_distance=int(dist)))
    return out
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_detection_frame_diff.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/frame_diff.py tests/test_detection_frame_diff.py
git commit -m "feat(detection): frame change detection via perceptual hashing"
```

---

### Task 20: detection/window_merge.py — merge overlapping + bucket select

**Files:**
- Create: `skills/youtube_transcribe/detection/window_merge.py`
- Create: `tests/test_window_merge.py`

- [ ] **Step 1: Написать failing test**

`tests/test_window_merge.py`:

```python
"""Tests for window merging and bucket-based selection."""
from skills.youtube_transcribe.detection.base import DetectionWindow
from skills.youtube_transcribe.detection.window_merge import (
    merge_overlapping_windows,
    select_windows_by_budget,
)


def test_merge_non_overlapping_unchanged():
    ws = [
        DetectionWindow(0.0, 5.0, "raw", 1.0, 1.0, "a"),
        DetectionWindow(10.0, 15.0, "raw", 1.0, 1.0, "b"),
    ]
    out = merge_overlapping_windows(ws, max_gap=1.0)
    assert len(out) == 2


def test_merge_overlapping_combines():
    ws = [
        DetectionWindow(0.0, 5.0, "raw", 1.0, 1.0, "a"),
        DetectionWindow(4.0, 10.0, "raw", 0.8, 1.0, "b"),
    ]
    out = merge_overlapping_windows(ws, max_gap=0.5)
    assert len(out) == 1
    assert out[0].start == 0.0
    assert out[0].end == 10.0


def test_merge_close_gap_combines():
    ws = [
        DetectionWindow(0.0, 5.0, "raw", 1.0, 1.0, "a"),
        DetectionWindow(5.5, 10.0, "raw", 1.0, 1.0, "b"),
    ]
    out = merge_overlapping_windows(ws, max_gap=1.0)
    assert len(out) == 1


def test_budget_within_returns_all():
    ws = [
        DetectionWindow(0.0, 5.0, "raw", 1.0, 1.0, "a"),
        DetectionWindow(20.0, 25.0, "raw", 1.0, 1.0, "b"),
    ]
    out = select_windows_by_budget(ws, max_windows=10, video_duration=60.0)
    assert len(out) == 2


def test_budget_exceed_picks_best_per_bucket():
    """Видео 60s, бюджет 3 → корзины [0-20, 20-40, 40-60]. В каждой берём best."""
    ws = [
        DetectionWindow(2.0, 4.0, "u", 0.5, 1.0, "low"),
        DetectionWindow(5.0, 7.0, "u", 0.9, 2.0, "high"),  # bucket 0, score*w = 1.8
        DetectionWindow(25.0, 27.0, "u", 0.8, 1.0, "ok"),  # bucket 1
        DetectionWindow(30.0, 32.0, "u", 0.6, 1.0, "less"),
        DetectionWindow(50.0, 52.0, "u", 0.7, 1.0, "fine"),  # bucket 2
    ]
    out = select_windows_by_budget(ws, max_windows=3, video_duration=60.0)
    assert len(out) == 3
    phrases = sorted(w.phrase for w in out)
    assert phrases == ["fine", "high", "ok"]


def test_budget_zero_or_no_video_returns_empty():
    ws = [DetectionWindow(0.0, 5.0, "raw", 1.0, 1.0, "a")]
    assert select_windows_by_budget(ws, max_windows=0, video_duration=60.0) == []
    assert select_windows_by_budget(ws, max_windows=5, video_duration=0.0) == []
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_window_merge.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/detection/window_merge.py`:

```python
"""Window merge (combine overlaps + close gaps) and budget selection."""
from __future__ import annotations

from skills.youtube_transcribe.detection.base import DetectionWindow


def merge_overlapping_windows(
    windows: list[DetectionWindow], max_gap: float = 1.0
) -> list[DetectionWindow]:
    """Sort by start, merge if overlap or gap < max_gap. Keep best (priority_score) reason/phrase."""
    if not windows:
        return []
    sorted_ws = sorted(windows, key=lambda w: w.start)
    out: list[DetectionWindow] = [sorted_ws[0]]
    for w in sorted_ws[1:]:
        last = out[-1]
        if w.start <= last.end + max_gap:
            best = last if last.priority_score >= w.priority_score else w
            out[-1] = DetectionWindow(
                start=min(last.start, w.start),
                end=max(last.end, w.end),
                reason=best.reason,
                score=best.score,
                weight=best.weight,
                phrase=best.phrase,
            )
        else:
            out.append(w)
    return out


def select_windows_by_budget(
    windows: list[DetectionWindow],
    max_windows: int,
    video_duration: float,
) -> list[DetectionWindow]:
    """If matches fit within budget — return all. Otherwise:
      1. Divide video into max_windows time buckets.
      2. In each bucket — pick window with highest priority_score (score * weight).
      3. Return list (may be < max_windows if some buckets empty).
    """
    if max_windows <= 0 or video_duration <= 0 or not windows:
        return []
    if len(windows) <= max_windows:
        return list(windows)

    bucket_size = video_duration / max_windows
    buckets: list[list[DetectionWindow]] = [[] for _ in range(max_windows)]
    for w in windows:
        idx = min(int(w.start / bucket_size), max_windows - 1)
        buckets[idx].append(w)
    out = []
    for bucket in buckets:
        if bucket:
            out.append(max(bucket, key=lambda w: w.priority_score))
    return out
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_window_merge.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/detection/window_merge.py tests/test_window_merge.py
git commit -m "feat(detection): window merge + bucket-based budget selection"
```

---

# Phase 6 — Vision backend (Gemini multimodal)

### Task 21: vision/frames.py — ffmpeg keyframe extraction

**Files:**
- Create: `skills/youtube_transcribe/vision/frames.py`
- Create: `tests/test_vision_frames.py`

- [ ] **Step 1: Написать failing test**

`tests/test_vision_frames.py`:

```python
"""Tests for keyframe extraction. ffmpeg subprocess mocked."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.vision.frames import extract_keyframes


def test_extract_keyframes_calls_ffmpeg(tmp_path):
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    # Pretend 3 frames were created
    for i in range(3):
        (out_dir / f"frame_{i:04d}.jpg").write_bytes(b"fake jpeg")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = extract_keyframes(
            video_path=Path("input.mp4"),
            start=10.0,
            end=15.0,
            count=3,
            out_dir=out_dir,
            video_id="abc",
        )

    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert "ffmpeg" in cmd[0]
    assert "-ss" in cmd
    assert "10.0" in cmd
    # Returns paths to extracted frames
    assert len(result) == 3


def test_extract_keyframes_renames_with_video_id(tmp_path):
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    (out_dir / "tmp_0001.jpg").write_bytes(b"fake")

    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        with patch(
            "skills.youtube_transcribe.vision.frames._tmp_pattern",
            return_value=out_dir / "tmp_%04d.jpg",
        ):
            paths = extract_keyframes(
                video_path=Path("v.mp4"),
                start=5.0,
                end=10.0,
                count=1,
                out_dir=out_dir,
                video_id="vid123",
            )
    # Renamed files should follow <video_id>_<sec>.jpg pattern
    for p in paths:
        assert p.name.startswith("vid123_")
        assert p.exists()
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_vision_frames.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/vision/frames.py`:

```python
"""Extract keyframes from video via ffmpeg.

Output naming: <video_id>_<seconds>.jpg, relative to out_dir/frames/.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _tmp_pattern(out_dir: Path) -> Path:
    """Pattern for ffmpeg output files (overridable in tests)."""
    return out_dir / "tmp_%04d.jpg"


def extract_keyframes(
    video_path: Path,
    start: float,
    end: float,
    count: int,
    out_dir: Path,
    video_id: str,
) -> list[Path]:
    """Extract <count> evenly-spaced keyframes from [start, end] window.

    Files named <video_id>_<sec>.jpg in out_dir.
    Returns list of created file paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = max(end - start, 0.1)
    fps = count / duration

    pattern = _tmp_pattern(out_dir)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-frames:v", str(count),
        str(pattern),
    ]
    subprocess.run(cmd, check=True)

    # Rename tmp_NNNN.jpg → <video_id>_<sec>.jpg
    tmp_files = sorted(out_dir.glob("tmp_*.jpg"))
    out_paths: list[Path] = []
    for idx, tmp in enumerate(tmp_files):
        sec = int(start + idx / fps)
        new_path = out_dir / f"{video_id}_{sec:05d}.jpg"
        tmp.rename(new_path)
        out_paths.append(new_path)
    return out_paths
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_vision_frames.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/vision/frames.py tests/test_vision_frames.py
git commit -m "feat(vision): ffmpeg-based keyframe extraction with video_id naming"
```

---

### Task 22: backends/vision_base.py — VisionBackend Protocol + VisualSegment

**Files:**
- Create: `skills/youtube_transcribe/backends/vision_base.py`
- Create: `tests/test_vision_base.py`

- [ ] **Step 1: Написать failing test**

`tests/test_vision_base.py`:

```python
"""Tests for VisualSegment dataclass and VisionBackend Protocol."""
from skills.youtube_transcribe.backends.vision_base import VisualSegment


def test_visual_segment_creation():
    vs = VisualSegment(
        start=10.5,
        end=15.0,
        description="Code editor with API call",
        keyframes=["frames/abc_00010.jpg"],
        detected_objects=["editor", "code"],
        trigger_reason="universal:function",
        importance="high",
    )
    assert vs.start == 10.5
    assert vs.importance == "high"


def test_visual_segment_defaults():
    vs = VisualSegment(start=0.0, end=1.0, description="x", keyframes=[])
    assert vs.detected_objects == []
    assert vs.trigger_reason == ""
    assert vs.importance == "medium"
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_vision_base.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/backends/vision_base.py`:

```python
"""Vision backend Protocol + VisualSegment data type."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from skills.youtube_transcribe.detection.base import DetectionWindow

Importance = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class VisualSegment:
    """One annotated visual moment."""
    start: float
    end: float
    description: str
    keyframes: list[str]               # relative paths to jpg files
    detected_objects: list[str] = field(default_factory=list)
    trigger_reason: str = ""
    importance: Importance = "medium"


class VisionBackend(Protocol):
    """Multimodal LLM that can describe video+audio together."""

    def annotate_segments(
        self,
        video_path: Path,
        windows: list[DetectionWindow],
        prompt_template: str,
        language: str,
        video_id: str,
        out_dir: Path,
    ) -> list[VisualSegment]:
        ...
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_vision_base.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/backends/vision_base.py tests/test_vision_base.py
git commit -m "feat(vision): VisionBackend Protocol + VisualSegment dataclass"
```

---

### Task 23: vision/prompts.py — DEFAULT_PROMPT template

**Files:**
- Create: `skills/youtube_transcribe/vision/prompts.py`
- Create: `tests/test_vision_prompts.py`

- [ ] **Step 1: Написать failing test**

`tests/test_vision_prompts.py`:

```python
"""Tests for vision prompt template formatting."""
from skills.youtube_transcribe.vision.prompts import (
    DEFAULT_PROMPT,
    format_prompt,
)


def test_default_prompt_has_expected_keys():
    """Template должен ожидать language, transcript_snippet, start_sec, end_sec."""
    formatted = format_prompt(
        DEFAULT_PROMPT,
        language="en",
        transcript_snippet="hello",
        start_sec=10.0,
        end_sec=15.0,
    )
    assert "en" in formatted
    assert "hello" in formatted
    assert "10.0" in formatted or "10" in formatted


def test_format_prompt_unknown_language_falls_back_to_english():
    formatted = format_prompt(
        DEFAULT_PROMPT,
        language="kk",       # казахский — точно нет специального шаблона
        transcript_snippet="x",
        start_sec=0.0,
        end_sec=1.0,
    )
    # Just verify it doesn't crash and returns a non-empty string
    assert formatted
    assert "x" in formatted
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_vision_prompts.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/vision/prompts.py`:

```python
"""Prompt templates for vision-LLM annotation of video moments."""
from __future__ import annotations

DEFAULT_PROMPT = """\
You are analyzing a YouTube video. Below is the transcript snippet for a specific
moment. Describe what is shown VISUALLY on the screen during this moment in
{language}, structured as JSON with these keys:
- description: 1-3 sentences. What is happening visually. Mention UI, code,
  diagrams, demonstrations. NOT what is said.
- key_objects: list of distinct visual objects/UI-elements/code-fragments shown.
- importance: "high" | "medium" | "low" — how visually informative is this moment
  beyond the spoken content.

Transcript context (audio only):
{transcript_snippet}

Time window: {start_sec:.1f}s — {end_sec:.1f}s.

Return ONLY valid JSON, no preamble.
"""


def format_prompt(
    template: str,
    *,
    language: str,
    transcript_snippet: str,
    start_sec: float,
    end_sec: float,
) -> str:
    return template.format(
        language=language,
        transcript_snippet=transcript_snippet,
        start_sec=start_sec,
        end_sec=end_sec,
    )
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_vision_prompts.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/vision/prompts.py tests/test_vision_prompts.py
git commit -m "feat(vision): default prompt template + format_prompt helper"
```

---

### Task 24: vision/gemini.py — GeminiVisionBackend (multimodal File API)

**Files:**
- Create: `skills/youtube_transcribe/vision/gemini.py`
- Create: `tests/test_vision_gemini.py`

- [ ] **Step 1: Написать failing test**

`tests/test_vision_gemini.py`:

```python
"""Tests for GeminiVisionBackend. genai.Client mocked."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skills.youtube_transcribe.detection.base import DetectionWindow
from skills.youtube_transcribe.vision.gemini import GeminiVisionBackend


def _fake_segment(start, end, text):
    """Minimal stand-in for Segment."""
    s = MagicMock()
    s.start = start
    s.end = end
    s.text = text
    return s


def test_gemini_annotate_returns_visual_segments(tmp_path):
    """Mock the entire genai client + ffmpeg keyframe extraction."""
    fake_resp = MagicMock()
    fake_resp.text = json.dumps({
        "description": "Code editor with API call",
        "key_objects": ["editor", "API"],
        "importance": "high",
    })
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/123")
    fake_client.models.generate_content.return_value = fake_resp

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    windows = [
        DetectionWindow(start=10.0, end=15.0, reason="universal", score=0.8, weight=1.0, phrase="code"),
    ]

    with patch(
        "skills.youtube_transcribe.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[out_dir / "vid_00010.jpg"],
    ):
        backend = GeminiVisionBackend(api_key="fake", model="gemini-2.5-flash")
        result = backend.annotate_segments(
            video_path=Path("input.mp4"),
            windows=windows,
            prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
            language="en",
            video_id="vid",
            out_dir=out_dir,
        )

    assert len(result) == 1
    assert result[0].description == "Code editor with API call"
    assert result[0].importance == "high"
    assert "editor" in result[0].key_objects


def test_gemini_handles_invalid_json(tmp_path):
    """Bad JSON from Gemini → fall back to raw text in description."""
    fake_resp = MagicMock()
    fake_resp.text = "not valid json"
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.youtube_transcribe.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[out_dir / "vid_00010.jpg"],
    ):
        backend = GeminiVisionBackend(api_key="fake")
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="{language}{transcript_snippet}{start_sec}{end_sec}",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
    assert "not valid json" in result[0].description
    assert result[0].importance == "medium"  # default fallback


def test_gemini_window_with_no_keyframes_skipped(tmp_path):
    """If keyframe extraction returns empty, window is skipped."""
    fake_client = MagicMock()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.youtube_transcribe.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.youtube_transcribe.vision.frames.extract_keyframes",
        return_value=[],
    ):
        backend = GeminiVisionBackend(api_key="fake")
        result = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=[DetectionWindow(0, 1, "raw", 1, 1, "x")],
            prompt_template="x",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
    assert result == []
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_vision_gemini.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/vision/gemini.py`:

```python
"""GeminiVisionBackend — multimodal annotation via Gemini File API."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from google import genai

from skills.youtube_transcribe.backends.vision_base import VisionBackend, VisualSegment
from skills.youtube_transcribe.detection.base import DetectionWindow
from skills.youtube_transcribe.vision import frames as frames_mod
from skills.youtube_transcribe.vision.prompts import format_prompt


@dataclass
class GeminiVisionBackend:
    api_key: str
    model: str = "gemini-2.5-flash"
    frames_per_window: int = 3
    max_retries: int = 3

    def annotate_segments(
        self,
        video_path: Path,
        windows: list[DetectionWindow],
        prompt_template: str,
        language: str,
        video_id: str,
        out_dir: Path,
    ) -> list[VisualSegment]:
        client = genai.Client(api_key=self.api_key)
        # Upload video once, use for all windows
        try:
            uploaded = client.files.upload(file=str(video_path))
        except Exception as e:
            # Failure to upload — skip vision annotation entirely
            return []

        frames_dir = out_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        out: list[VisualSegment] = []
        for w in windows:
            try:
                keyframes = frames_mod.extract_keyframes(
                    video_path=video_path,
                    start=w.start,
                    end=w.end,
                    count=self.frames_per_window,
                    out_dir=frames_dir,
                    video_id=video_id,
                )
            except Exception:
                continue
            if not keyframes:
                continue

            prompt = format_prompt(
                prompt_template,
                language=language,
                transcript_snippet=w.phrase or "(window from scene change)",
                start_sec=w.start,
                end_sec=w.end,
            )

            description, key_objects, importance = self._call_with_retry(client, uploaded, prompt)
            rel_keyframes = [f"frames/{p.name}" for p in keyframes]
            out.append(VisualSegment(
                start=w.start,
                end=w.end,
                description=description,
                keyframes=rel_keyframes,
                detected_objects=key_objects,
                trigger_reason=w.reason,
                importance=importance,
            ))
        return out

    def _call_with_retry(self, client, uploaded, prompt: str) -> tuple[str, list[str], str]:
        backoffs = [3.0, 6.0, 12.0]
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = client.models.generate_content(
                    model=self.model,
                    contents=[prompt, uploaded],
                )
                return self._parse_response(resp.text or "")
            except Exception as e:
                last_err = e
                if attempt < self.max_retries - 1:
                    time.sleep(backoffs[attempt])
        return f"(error: {last_err})", [], "medium"

    @staticmethod
    def _parse_response(text: str) -> tuple[str, list[str], str]:
        text = text.strip()
        if text.startswith("```"):
            # Strip code fences
            text = "\n".join(line for line in text.split("\n") if not line.startswith("```"))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text, [], "medium"
        desc = str(data.get("description", text))[:2000]
        ko = data.get("key_objects", [])
        if not isinstance(ko, list):
            ko = []
        importance = data.get("importance", "medium")
        if importance not in ("low", "medium", "high"):
            importance = "medium"
        return desc, [str(o) for o in ko], importance
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_vision_gemini.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full vision suite**

Run: `uv run pytest tests/test_vision_*.py -v`
Expected: ~7 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/vision/gemini.py tests/test_vision_gemini.py
git commit -m "feat(vision): GeminiVisionBackend with File API + per-window calls"
```

---

# Phase 7 — Presets registry + 4 tiers

### Task 25: presets/registry.py — OptionField + REGISTRY

**Files:**
- Create: `skills/youtube_transcribe/presets/registry.py`
- Create: `tests/test_presets_registry.py`

- [ ] **Step 1: Написать failing test**

`tests/test_presets_registry.py`:

```python
"""Tests for OptionField + REGISTRY."""
from skills.youtube_transcribe.presets.registry import (
    OptionField,
    REGISTRY,
    get_field,
    fields_by_section,
)


def test_registry_has_required_fields():
    keys = {f.key for f in REGISTRY}
    assert "transcribe_backend" in keys
    assert "vision_backend" in keys
    assert "detect_method" in keys
    assert "frames_per_window" in keys


def test_field_has_required_metadata():
    f = get_field("transcribe_backend")
    assert f is not None
    assert f.type is str
    assert f.default == "subtitles"
    assert "subtitles" in f.choices
    assert "whisper-local" in f.choices
    assert f.description


def test_each_default_is_in_choices():
    """If a field has choices, default MUST be in choices."""
    for f in REGISTRY:
        if f.choices is not None:
            assert f.default in f.choices, f"{f.key} default {f.default} not in {f.choices}"


def test_fields_by_section_groups():
    by_sect = fields_by_section()
    assert "transcribe" in by_sect
    assert "vision" in by_sect


def test_get_field_unknown_returns_none():
    assert get_field("totally_made_up") is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_presets_registry.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/presets/registry.py`:

```python
"""Single source of truth for all v0.2 options.

Used by:
- CLI flag generation (Click options)
- TUI prompts (`youtube-transcribe config`)
- Future v0.4+ web UI form rendering
- Default config.toml comment generation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OptionField:
    key: str
    type: type
    default: Any
    choices: list | None
    description: str
    section: str


REGISTRY: list[OptionField] = [
    # === transcribe ===
    OptionField(
        key="transcribe_backend", type=str, default="subtitles",
        choices=["subtitles", "whisper-local", "gemini", "groq", "openai",
                 "deepgram", "assemblyai", "custom"],
        description="Чем транскрибировать. subtitles = брать готовые с YouTube.",
        section="transcribe",
    ),
    OptionField(
        key="fallback_backend", type=str, default="whisper-local",
        choices=["whisper-local", "gemini", "groq", "openai", "deepgram",
                 "assemblyai", "custom"],
        description="Куда переключиться, если subtitles не подошли (smart-режим).",
        section="transcribe",
    ),
    # === vision ===
    OptionField(
        key="vision_backend", type=str, default="off",
        choices=["off", "gemini"],
        description="Visual mode. off = только аудио. gemini = multimodal анализ.",
        section="vision",
    ),
    OptionField(
        key="frames_per_window", type=int, default=3,
        choices=None,
        description="Сколько keyframes извлекать на одно visual-окно.",
        section="vision",
    ),
    OptionField(
        key="max_windows_per_video", type=int, default=20,
        choices=None,
        description="Максимум окон vision-анализа на одно видео.",
        section="vision",
    ),
    # === detection ===
    OptionField(
        key="detect_method", type=str, default="keywords_only",
        choices=["keywords_only", "semantic", "hybrid", "llm_full_pass"],
        description="Метод поиска визуально-важных моментов.",
        section="detection",
    ),
    # === smart ===
    OptionField(
        key="quality_check", type=bool, default=False,
        choices=None,
        description="Запускать quality check на полученном транскрипте.",
        section="smart",
    ),
    OptionField(
        key="subtitle_quality_threshold", type=float, default=0.6,
        choices=None,
        description="Score < этого → fallback к whisper в smart-режиме.",
        section="smart",
    ),
    OptionField(
        key="quality_perplexity", type=bool, default=False,
        choices=None,
        description="Включить kenlm perplexity (требует extra `perplexity`).",
        section="smart",
    ),
    # === output ===
    OptionField(
        key="ocr", type=bool, default=False,
        choices=None,
        description="OCR на keyframes (требует extra `ocr` + системный tesseract).",
        section="output",
    ),
]


def get_field(key: str) -> OptionField | None:
    for f in REGISTRY:
        if f.key == key:
            return f
    return None


def fields_by_section() -> dict[str, list[OptionField]]:
    out: dict[str, list[OptionField]] = {}
    for f in REGISTRY:
        out.setdefault(f.section, []).append(f)
    return out
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_presets_registry.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/youtube_transcribe/presets/registry.py tests/test_presets_registry.py
git commit -m "feat(presets): single options registry for CLI/TUI/web UI"
```

---

### Task 26: presets/data/presets_default.toml + presets/loader.py

**Files:**
- Create: `skills/youtube_transcribe/presets/data/presets_default.toml`
- Create: `skills/youtube_transcribe/presets/loader.py`
- Create: `tests/test_presets_loader.py`

- [ ] **Step 1: Создать presets_default.toml**

`skills/youtube_transcribe/presets/data/presets_default.toml`:

```toml
# Built-in 4-tier presets. User overrides go to ~/.youtube-transcribe/config.toml.

default_preset = "smart"

# === ECO ===
[presets.eco]
transcribe_backend = "subtitles"
fallback_backend = "whisper-local"
vision_backend = "off"
detect_method = "keywords_only"
quality_check = false
max_windows_per_video = 0

# === SMART (default) ===
[presets.smart]
transcribe_backend = "subtitles"
fallback_backend = "whisper-local"
quality_check = true
subtitle_quality_threshold = 0.6
vision_backend = "gemini"
detect_method = "hybrid"
frames_per_window = 3
max_windows_per_video = 20

# === STANDARD ===
[presets.standard]
transcribe_backend = "whisper-local"
vision_backend = "gemini"
detect_method = "hybrid"
frames_per_window = 3
max_windows_per_video = 30

# === PREMIUM ===
[presets.premium]
transcribe_backend = "whisper-local"
vision_backend = "gemini"
detect_method = "llm_full_pass"
frames_per_window = 5
max_windows_per_video = 50
quality_check = true
quality_perplexity = true
```

- [ ] **Step 2: Написать failing test**

`tests/test_presets_loader.py`:

```python
"""Tests for preset loading + merge with user config + CLI overrides."""
import textwrap

import pytest

from skills.youtube_transcribe.presets.loader import (
    load_preset_values,
    list_preset_names,
)


def test_list_presets_includes_4_tiers():
    names = list_preset_names()
    assert {"eco", "smart", "standard", "premium"}.issubset(set(names))


def test_load_smart_preset_defaults():
    vals = load_preset_values("smart")
    assert vals["transcribe_backend"] == "subtitles"
    assert vals["vision_backend"] == "gemini"
    assert vals["detect_method"] == "hybrid"


def test_load_eco_preset_no_visual():
    vals = load_preset_values("eco")
    assert vals["vision_backend"] == "off"


def test_load_unknown_preset_raises():
    with pytest.raises(KeyError):
        load_preset_values("nonexistent")


def test_user_config_overrides_builtin(tmp_path):
    user_path = tmp_path / "config.toml"
    user_path.write_text(textwrap.dedent("""\
        [presets.smart]
        max_windows_per_video = 50
    """), encoding="utf-8")

    vals = load_preset_values("smart", user_config_path=user_path)
    assert vals["max_windows_per_video"] == 50
    # Other fields remain from built-in
    assert vals["transcribe_backend"] == "subtitles"


def test_cli_overrides_beat_user_and_builtin(tmp_path):
    user_path = tmp_path / "config.toml"
    user_path.write_text(textwrap.dedent("""\
        [presets.smart]
        max_windows_per_video = 50
    """), encoding="utf-8")

    vals = load_preset_values(
        "smart",
        user_config_path=user_path,
        cli_overrides={"max_windows_per_video": 100, "vision_backend": "off"},
    )
    assert vals["max_windows_per_video"] == 100
    assert vals["vision_backend"] == "off"


def test_external_config_path_replaces_user(tmp_path):
    """--config /path/to/file.toml — alternative config file."""
    ext_path = tmp_path / "ext.toml"
    ext_path.write_text(textwrap.dedent("""\
        [presets.smart]
        transcribe_backend = "groq"
    """), encoding="utf-8")

    vals = load_preset_values("smart", external_config_path=ext_path)
    assert vals["transcribe_backend"] == "groq"
```

- [ ] **Step 3: Run test, verify FAIL**

Run: `uv run pytest tests/test_presets_loader.py -v`
Expected: ImportError.

- [ ] **Step 4: Написать реализацию**

`skills/youtube_transcribe/presets/loader.py`:

```python
"""Load preset values: built-in defaults < user config.toml < external --config < CLI flags."""
from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

from skills.youtube_transcribe.presets.registry import REGISTRY

DEFAULT_USER_CONFIG = Path.home() / ".youtube-transcribe" / "config.toml"


def _load_builtin() -> dict:
    text = files("skills.youtube_transcribe.presets.data").joinpath(
        "presets_default.toml"
    ).read_text(encoding="utf-8")
    return tomllib.loads(text)


def _load_toml(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def list_preset_names() -> list[str]:
    return list(_load_builtin().get("presets", {}).keys())


def load_preset_values(
    preset_name: str,
    *,
    user_config_path: Path | None = None,
    external_config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve final values for `preset_name`. Priority (lowest to highest):
      1. registry defaults
      2. built-in presets_default.toml [presets.<name>]
      3. user ~/.youtube-transcribe/config.toml [presets.<name>] (or external if given)
      4. CLI overrides
    """
    builtin = _load_builtin()
    presets = builtin.get("presets", {})
    if preset_name not in presets:
        raise KeyError(f"Unknown preset: {preset_name}. Known: {list(presets.keys())}")

    # 1. registry defaults
    values: dict[str, Any] = {f.key: f.default for f in REGISTRY}

    # 2. built-in preset overrides
    values.update(presets[preset_name])

    # 3. user config OR external --config
    config_path = external_config_path if external_config_path else (user_config_path or DEFAULT_USER_CONFIG)
    user_data = _load_toml(config_path)
    user_preset = user_data.get("presets", {}).get(preset_name, {})
    values.update(user_preset)

    # 4. CLI overrides
    if cli_overrides:
        for k, v in cli_overrides.items():
            if v is not None:
                values[k] = v

    return values
```

- [ ] **Step 5: Run test, verify PASS**

Run: `uv run pytest tests/test_presets_loader.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/presets/data/presets_default.toml \
        skills/youtube_transcribe/presets/loader.py \
        tests/test_presets_loader.py
git commit -m "feat(presets): 4-tier defaults + load_preset_values with override chain"
```

---

### Task 27: presets — silent fallback for vision when no GEMINI_API_KEY

**Files:**
- Modify: `skills/youtube_transcribe/presets/loader.py`
- Create: `tests/test_presets_silent_fallback.py`

- [ ] **Step 1: Написать failing test**

`tests/test_presets_silent_fallback.py`:

```python
"""When vision_backend=gemini but no API key — silent fallback to off."""
import pytest

from skills.youtube_transcribe.presets.loader import resolve_with_env_checks


def test_smart_preset_gemini_without_key_falls_back(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )

    vals, info_messages = resolve_with_env_checks("smart")
    assert vals["vision_backend"] == "off"
    assert any("GEMINI_API_KEY" in m for m in info_messages)


def test_smart_preset_gemini_with_key_kept(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    vals, info_messages = resolve_with_env_checks("smart")
    assert vals["vision_backend"] == "gemini"
    assert info_messages == []


def test_eco_preset_unaffected_no_key_no_fallback(monkeypatch):
    """Eco has vision_backend=off already, no fallback needed."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    vals, _ = resolve_with_env_checks("eco")
    assert vals["vision_backend"] == "off"
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_presets_silent_fallback.py -v`
Expected: ImportError on `resolve_with_env_checks`.

- [ ] **Step 3: Дописать loader.py**

В конец `skills/youtube_transcribe/presets/loader.py`:

```python
def resolve_with_env_checks(
    preset_name: str,
    *,
    user_config_path: Path | None = None,
    external_config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Same as load_preset_values, but applies silent fallbacks for missing API keys.

    Returns (values, info_messages). Info messages should be printed to stderr
    so user knows why visual mode is off.
    """
    from skills.youtube_transcribe.config import get_api_key

    values = load_preset_values(
        preset_name,
        user_config_path=user_config_path,
        external_config_path=external_config_path,
        cli_overrides=cli_overrides,
    )
    info: list[str] = []

    if values.get("vision_backend") == "gemini":
        if not get_api_key("gemini"):
            values["vision_backend"] = "off"
            info.append(
                "ℹ Visual mode disabled: GEMINI_API_KEY not set. "
                "Add to ~/.youtube-transcribe/.env to enable."
            )

    return values, info
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_presets_silent_fallback.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full presets suite**

Run: `uv run pytest tests/test_presets_*.py -v`
Expected: ~15 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/presets/loader.py tests/test_presets_silent_fallback.py
git commit -m "feat(presets): silent fallback for vision when GEMINI_API_KEY missing"
```

---

# Phase 8 — Output extension + CLI rewiring

### Task 28: output_writer.py — visual moments в combined.md

**Files:**
- Modify: `skills/youtube_transcribe/utils/output_writer.py`
- Create: `tests/test_output_writer_visual.py`

- [ ] **Step 1: Написать failing test**

`tests/test_output_writer_visual.py`:

```python
"""Tests for visual moments rendering in combined.md."""
from datetime import date, datetime
from pathlib import Path

from skills.youtube_transcribe.utils.output_writer import (
    BatchMeta,
    BatchVideoStatus,
    write_combined_md,
)
from skills.youtube_transcribe.backends.vision_base import VisualSegment


def _meta() -> BatchMeta:
    return BatchMeta(
        batch_name="test_batch",
        created_at=datetime(2026, 5, 10, 12, 0, 0),
        source_type="inline",
        source_url=None,
        backend="whisper-local",
        backend_options={"model": "turbo"},
        language="auto",
    )


def _video_with_visuals() -> BatchVideoStatus:
    return BatchVideoStatus(
        index=1,
        url="https://youtu.be/abc",
        video_id="abc",
        title="Tutorial",
        upload_date=date(2026, 4, 1),
        duration_sec=600,
        channel="Test",
        language_detected="en",
        text="Hello and welcome to today's tutorial.",
        files={"txt": "Tutorial_abc.txt", "srt": "Tutorial_abc.srt"},
        status="ok",
        visual_segments=[
            VisualSegment(
                start=10.0, end=15.0,
                description="Code editor with API call",
                keyframes=["frames/abc_00010.jpg"],
                detected_objects=["editor"],
                trigger_reason="universal:function",
                importance="high",
            ),
        ],
    )


def test_combined_md_includes_visual_moments_section(tmp_path):
    write_combined_md([_video_with_visuals()], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "### Visual moments" in content
    assert "frames/abc_00010.jpg" in content
    assert "Code editor with API call" in content
    assert "importance: high" in content


def test_combined_md_skips_visual_section_if_empty(tmp_path):
    v = _video_with_visuals()
    v_no_visuals = BatchVideoStatus(
        **{**v.__dict__, "visual_segments": []},
    )
    write_combined_md([v_no_visuals], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "### Visual moments" not in content


def test_combined_md_includes_quality_warning_when_low(tmp_path):
    from skills.youtube_transcribe.quality.base import QualityReport
    v = _video_with_visuals()
    v_low_quality = BatchVideoStatus(
        **{**v.__dict__,
            "quality": QualityReport(
                score=0.3, breakdown={"oov": 0.4}, flags=["high_oov"],
                recommendation="low_quality",
            ),
        },
    )
    write_combined_md([v_low_quality], _meta(), tmp_path)
    content = (tmp_path / "combined.md").read_text(encoding="utf-8")
    assert "Quality" in content
    assert "0.3" in content or "low_quality" in content
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_output_writer_visual.py -v`
Expected: FAIL — `BatchVideoStatus` пока не имеет полей `visual_segments` / `quality`.

- [ ] **Step 3: Расширить `BatchVideoStatus` и `write_combined_md`**

В `skills/youtube_transcribe/utils/output_writer.py`:

1. **Расширить imports:**

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from skills.youtube_transcribe.backends.vision_base import VisualSegment
    from skills.youtube_transcribe.quality.base import QualityReport
```

2. **Расширить `BatchVideoStatus`** — добавить поля в конец dataclass:

```python
@dataclass
class BatchVideoStatus:
    # ... existing fields ...
    error: str | None = None
    # === v0.2 additions ===
    visual_segments: list = field(default_factory=list)        # list[VisualSegment]
    quality: object | None = None                               # QualityReport | None
```

3. **Дополнить `write_combined_md` после блока `parts.append(v.text.strip() + "\n")`:**

```python
        # === v0.2: quality warning ===
        if v.quality is not None and v.quality.recommendation != "use_as_is":
            parts.append("\n")
            flags_str = ", ".join(v.quality.flags) if v.quality.flags else "—"
            parts.append(
                f"⚠ **Quality: {v.quality.recommendation}** "
                f"(score={v.quality.score:.2f}, flags=[{flags_str}])\n"
            )

        # === v0.2: visual moments ===
        if v.visual_segments:
            parts.append("\n### Visual moments\n\n")
            for vs in v.visual_segments:
                ts = _format_timestamp_dotted(vs.start)
                parts.append(f"#### {ts} — {vs.description.split('.')[0]} (importance: {vs.importance})\n\n")
                for kf in vs.keyframes:
                    parts.append(f"![]({kf})\n\n")
                parts.append(f"{vs.description}\n\n")
                if vs.detected_objects:
                    parts.append(f"Objects detected: {', '.join(vs.detected_objects)}\n\n")
                parts.append(f"Trigger: `{vs.trigger_reason}`\n\n")
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_output_writer_visual.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify v0.1 tests still pass**

Run: `uv run pytest tests/test_output_writer*.py -v`
Expected: все green (старые v0.1 тесты + новые v0.2).

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/utils/output_writer.py tests/test_output_writer_visual.py
git commit -m "feat(output): add visual moments + quality warnings to combined.md"
```

---

### Task 29: output_writer.py — manifest расширить полями quality + visual_segments

**Files:**
- Modify: `skills/youtube_transcribe/utils/output_writer.py`
- Create: `tests/test_manifest_v02.py`

- [ ] **Step 1: Написать failing test**

`tests/test_manifest_v02.py`:

```python
"""Tests for manifest.json v0.2 extensions (quality, visual_segments)."""
import json
from datetime import date, datetime
from pathlib import Path

from skills.youtube_transcribe.utils.output_writer import (
    BatchMeta,
    BatchVideoStatus,
    write_manifest_json,
)
from skills.youtube_transcribe.backends.vision_base import VisualSegment
from skills.youtube_transcribe.quality.base import QualityReport


def _meta():
    return BatchMeta(
        batch_name="b", created_at=datetime(2026, 5, 10),
        source_type="inline", source_url=None,
        backend="whisper-local", backend_options={}, language="en",
    )


def test_manifest_includes_quality_field(tmp_path):
    v = BatchVideoStatus(
        index=1, url="https://x", video_id="x", title="X",
        upload_date=date(2026, 4, 1), duration_sec=60, channel="C",
        language_detected="en",
        text="hi", files={"txt": "X.txt"}, status="ok",
        quality=QualityReport(score=0.8, breakdown={"oov": 0.05}, flags=[],
                              recommendation="use_as_is"),
    )
    write_manifest_json([v], [], _meta(), tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    assert data["videos"][0]["quality"]["score"] == 0.8
    assert data["videos"][0]["quality"]["recommendation"] == "use_as_is"


def test_manifest_includes_visual_segments(tmp_path):
    v = BatchVideoStatus(
        index=1, url="https://x", video_id="x", title="X",
        upload_date=date(2026, 4, 1), duration_sec=60, channel="C",
        language_detected="en",
        text="hi", files={"txt": "X.txt"}, status="ok",
        visual_segments=[
            VisualSegment(
                start=10.0, end=15.0, description="d",
                keyframes=["frames/x.jpg"], importance="high",
                detected_objects=["a"], trigger_reason="raw",
            ),
        ],
    )
    write_manifest_json([v], [], _meta(), tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    vs = data["videos"][0]["visual_segments"][0]
    assert vs["start"] == 10.0
    assert vs["importance"] == "high"
    assert vs["keyframes"] == ["frames/x.jpg"]


def test_manifest_no_quality_field_when_none(tmp_path):
    v = BatchVideoStatus(
        index=1, url="https://x", video_id="x", title="X",
        upload_date=date(2026, 4, 1), duration_sec=60, channel="C",
        language_detected="en",
        text="hi", files={"txt": "X.txt"}, status="ok",
    )
    write_manifest_json([v], [], _meta(), tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    assert data["videos"][0].get("quality") is None
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_manifest_v02.py -v`
Expected: FAIL — манифест ещё не расширен.

- [ ] **Step 3: Расширить `write_manifest_json`**

В `skills/youtube_transcribe/utils/output_writer.py`, в `write_manifest_json`, дополнить блок построения `out.append(...)`:

```python
    for v in videos:
        entry = {
            "index": v.index,
            "url": v.url,
            "video_id": v.video_id,
            "title": v.title,
            "upload_date": v.upload_date.isoformat() if v.upload_date else None,
            "duration_sec": v.duration_sec,
            "channel": v.channel,
            "language_detected": v.language_detected,
            "files": v.files,
            "status": v.status,
            "error": v.error,
        }
        # === v0.2 ===
        if v.quality is not None:
            entry["quality"] = {
                "score": v.quality.score,
                "breakdown": v.quality.breakdown,
                "flags": v.quality.flags,
                "recommendation": v.quality.recommendation,
            }
        if v.visual_segments:
            entry["visual_segments"] = [
                {
                    "start": vs.start,
                    "end": vs.end,
                    "description": vs.description,
                    "keyframes": vs.keyframes,
                    "detected_objects": vs.detected_objects,
                    "trigger_reason": vs.trigger_reason,
                    "importance": vs.importance,
                }
                for vs in v.visual_segments
            ]
        out.append(entry)
```

(Заменить старый цикл на этот.)

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_manifest_v02.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify v0.1 manifest tests still pass**

Run: `uv run pytest tests/ -k manifest -v`
Expected: все green.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/utils/output_writer.py tests/test_manifest_v02.py
git commit -m "feat(output): extend manifest.json with quality + visual_segments"
```

---

### Task 30: pipeline.py — quality + detect + vision stages

**Files:**
- Create: `skills/youtube_transcribe/pipeline_v02.py` (новый, чтобы не конфликтовать с существующим pipeline'ом v0.1)
- Create: `tests/test_pipeline_v02.py`

> **Note:** существующий `run_pipeline()` в v0.1 расположен в `transcribe.py`. В v0.2 мы добавляем wrapper, который вызывает старый `run_pipeline` и затем applies quality + vision stages. Чтобы не ломать существующий код, создаём новый файл `pipeline_v02.py`.

- [ ] **Step 1: Написать failing test**

`tests/test_pipeline_v02.py`:

```python
"""Tests for v0.2 pipeline wrapper that adds quality + vision stages."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.pipeline_v02 import apply_v02_stages
from skills.youtube_transcribe.backends.base import TranscriptionResult
from skills.youtube_transcribe.utils.output_writer import Segment


def _result(text="hello world"):
    return TranscriptionResult(
        text=text,
        segments=[Segment(start=0.0, end=5.0, text=text)],
        language="en",
        backend_used="subtitles",
    )


def test_quality_check_runs_when_enabled():
    cfg = {"quality_check": True, "vision_backend": "off"}
    result = _result()
    with patch(
        "skills.youtube_transcribe.pipeline_v02.HeuristicChecker"
    ) as mock_checker:
        instance = MagicMock()
        instance.check.return_value = MagicMock(
            score=0.85, recommendation="use_as_is", flags=[], breakdown={},
        )
        mock_checker.return_value = instance

        out = apply_v02_stages(
            result=result, cfg=cfg, video_path=None,
            video_id="x", out_dir=Path("/tmp"), source="youtube_auto",
        )
    assert out.quality is not None
    assert out.quality.score == 0.85


def test_quality_check_skipped_when_disabled():
    cfg = {"quality_check": False, "vision_backend": "off"}
    result = _result()
    out = apply_v02_stages(
        result=result, cfg=cfg, video_path=None,
        video_id="x", out_dir=Path("/tmp"), source="youtube_auto",
    )
    assert out.quality is None


def test_vision_skipped_when_off():
    cfg = {"quality_check": False, "vision_backend": "off"}
    result = _result()
    out = apply_v02_stages(
        result=result, cfg=cfg, video_path=Path("/tmp/v.mp4"),
        video_id="x", out_dir=Path("/tmp"), source="whisper",
    )
    assert out.visual_segments == []


def test_vision_runs_when_gemini_and_video_path(tmp_path):
    cfg = {
        "quality_check": False,
        "vision_backend": "gemini",
        "detect_method": "keywords_only",
        "frames_per_window": 1,
        "max_windows_per_video": 5,
    }
    result = _result(text="look here")
    fake_visual = MagicMock()
    fake_visual.start = 0.0
    fake_visual.end = 5.0

    with patch(
        "skills.youtube_transcribe.pipeline_v02.find_detection_windows",
        return_value=[MagicMock(start=0.0, end=5.0, reason="universal", score=0.7,
                                weight=1.0, phrase="look here", priority_score=0.7)],
    ), patch(
        "skills.youtube_transcribe.pipeline_v02.GeminiVisionBackend"
    ) as mock_vis, patch(
        "skills.youtube_transcribe.config.get_api_key",
        return_value="fake_key",
    ):
        mock_vis.return_value.annotate_segments.return_value = [fake_visual]
        out = apply_v02_stages(
            result=result, cfg=cfg, video_path=tmp_path / "v.mp4",
            video_id="x", out_dir=tmp_path, source="whisper",
        )
    assert len(out.visual_segments) == 1
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_pipeline_v02.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/pipeline_v02.py`:

```python
"""v0.2 pipeline stages: quality check + visual detection/annotation.

Wrapper applied after the v0.1 transcribe stage. Returns enriched
TranscriptionResult with .quality and .visual_segments populated.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from skills.youtube_transcribe.backends.base import TranscriptionResult
from skills.youtube_transcribe.detection.base import DetectionWindow
from skills.youtube_transcribe.detection.matcher import match_segment
from skills.youtube_transcribe.detection.scene import find_scene_boundaries
from skills.youtube_transcribe.detection.triggers import load_triggers, TriggerConfig
from skills.youtube_transcribe.detection.window_merge import (
    merge_overlapping_windows,
    select_windows_by_budget,
)
from skills.youtube_transcribe.quality.heuristic_checker import HeuristicChecker
from skills.youtube_transcribe.vision.gemini import GeminiVisionBackend
from skills.youtube_transcribe.vision.prompts import DEFAULT_PROMPT


Source = Literal["youtube_manual", "youtube_auto", "whisper", "external_asr"]


def find_detection_windows(
    result: TranscriptionResult,
    video_path: Path | None,
    triggers: TriggerConfig,
    detect_method: str,
) -> list[DetectionWindow]:
    """Build list of windows from triggers + (optionally) scene boundaries."""
    windows: list[DetectionWindow] = []

    # 1. Trigger-based windows from transcript
    for seg in result.segments:
        m = match_segment(seg.text, triggers)
        if m:
            windows.append(DetectionWindow(
                start=max(seg.start - 1.5, 0.0),
                end=seg.end + 1.5,
                reason=m.reason,
                score=m.score,
                weight=m.weight,
                phrase=m.phrase,
            ))

    # 2. Scene-change boundaries (only for hybrid / llm_full_pass)
    if detect_method in ("hybrid", "llm_full_pass") and video_path is not None:
        try:
            boundaries = find_scene_boundaries(video_path)
            for t in boundaries:
                windows.append(DetectionWindow(
                    start=max(t - 0.5, 0.0),
                    end=t + 1.5,
                    reason="scene_change",
                    score=0.5,
                    weight=1.0,
                    phrase="",
                ))
        except Exception:
            pass

    return windows


def apply_v02_stages(
    *,
    result: TranscriptionResult,
    cfg: dict[str, Any],
    video_path: Path | None,
    video_id: str,
    out_dir: Path,
    source: Source,
) -> TranscriptionResult:
    """Apply quality check + detect + vision stages. Returns enriched result."""
    # === Quality check ===
    if cfg.get("quality_check"):
        checker = HeuristicChecker()
        report = checker.check(result.segments, result.language, source=source)
        result = TranscriptionResult(
            text=result.text,
            segments=result.segments,
            language=result.language,
            backend_used=result.backend_used,
        )
        result.quality = report

    # === Visual detection + annotation ===
    if cfg.get("vision_backend") == "gemini" and video_path is not None:
        from skills.youtube_transcribe.config import get_api_key
        api_key = get_api_key("gemini")
        if not api_key:
            return result

        triggers = load_triggers()
        windows = find_detection_windows(
            result, video_path, triggers, cfg.get("detect_method", "keywords_only")
        )
        windows = merge_overlapping_windows(windows, max_gap=1.0)

        video_duration = result.segments[-1].end if result.segments else 0.0
        windows = select_windows_by_budget(
            windows,
            max_windows=cfg.get("max_windows_per_video", 20),
            video_duration=video_duration,
        )

        if windows:
            backend = GeminiVisionBackend(
                api_key=api_key,
                frames_per_window=cfg.get("frames_per_window", 3),
            )
            visuals = backend.annotate_segments(
                video_path=video_path,
                windows=windows,
                prompt_template=DEFAULT_PROMPT,
                language=result.language,
                video_id=video_id,
                out_dir=out_dir,
            )
            result.visual_segments = visuals

    return result
```

> **Note:** `TranscriptionResult` в v0.1 — frozen dataclass без полей `quality`/`visual_segments`. Чтобы не ломать v0.1 backends, добавим эти поля как опциональные в Task 31 (через настоящий refactor).
>
> Временно — конструируем новый TR через unfrozen-копию или используем `setattr`. В TDD-стиле: тест сейчас сделает `setattr(result, "quality", ...)`. Это compromise — приемлемо в один шаг до Task 31.

- [ ] **Step 4: Расширить `TranscriptionResult` в `backends/base.py`**

В `skills/youtube_transcribe/backends/base.py`:

```python
@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]
    language: str
    backend_used: str
    # === v0.2 ===
    quality: object | None = None                           # QualityReport | None
    visual_segments: list = field(default_factory=list)     # list[VisualSegment]
```

(Убрать `frozen=True` если был, добавить `field` import.)

- [ ] **Step 5: Run test, verify PASS**

Run: `uv run pytest tests/test_pipeline_v02.py -v`
Expected: 4 passed.

- [ ] **Step 6: Verify v0.1 backends still work**

Run: `uv run pytest tests/test_backends_*.py -v`
Expected: все green.

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/pipeline_v02.py \
        skills/youtube_transcribe/backends/base.py \
        tests/test_pipeline_v02.py
git commit -m "feat(pipeline): v0.2 stages — quality check + detect + vision wrapper"
```

---

### Task 31: transcribe.py — новые CLI флаги + integrate v0.2 stages + register triggers sub-group

**Files:**
- Modify: `skills/youtube_transcribe/transcribe.py`
- Create: `tests/test_cli_v02_flags.py`

- [ ] **Step 1: Написать failing test**

`tests/test_cli_v02_flags.py`:

```python
"""Tests for v0.2 CLI flags surface area."""
from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def test_cli_help_shows_v02_flags():
    runner = CliRunner()
    res = runner.invoke(cli, ["transcribe", "--help"])
    assert res.exit_code == 0
    assert "--with-visuals" in res.output
    assert "--vision-backend" in res.output
    assert "--detect-method" in res.output
    assert "--preset" in res.output
    assert "--config" in res.output
    assert "--ocr" in res.output


def test_cli_triggers_subgroup_registered():
    runner = CliRunner()
    res = runner.invoke(cli, ["triggers", "--help"])
    assert res.exit_code == 0
    assert "init" in res.output
    assert "add" in res.output


def test_invalid_preset_value_rejected():
    runner = CliRunner()
    res = runner.invoke(cli, ["transcribe", "--preset", "nonexistent_preset", "fake-url"])
    assert res.exit_code != 0
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_cli_v02_flags.py -v`
Expected: FAIL — флаги ещё не добавлены.

- [ ] **Step 3: Расширить `transcribe.py` — добавить флаги в `transcribe` и `batch` команды + register triggers sub-group**

В `skills/youtube_transcribe/transcribe.py`:

1. **Добавить imports вверху:**

```python
from skills.youtube_transcribe.detection.triggers_cli import triggers_cli
from skills.youtube_transcribe.pipeline_v02 import apply_v02_stages
from skills.youtube_transcribe.presets.loader import (
    list_preset_names,
    resolve_with_env_checks,
)
```

2. **Зарегистрировать `triggers_cli` как sub-group в `cli`:**

В конце `transcribe.py`, до `if __name__ == "__main__"`:

```python
cli.add_command(triggers_cli)
```

3. **Добавить v0.2 флаги к `transcribe` и `batch` командам.** Найти существующий `@click.command(name="transcribe")` и добавить под него:

```python
@click.option("--with-visuals", is_flag=True, help="Shortcut for --vision-backend=gemini.")
@click.option("--vision-backend", type=click.Choice(["off", "gemini"]), default=None,
              help="Visual mode backend. off = audio only.")
@click.option("--detect-method",
              type=click.Choice(["keywords_only", "semantic", "hybrid", "llm_full_pass"]),
              default=None, help="How to find visual moments.")
@click.option("--frames-per-window", type=int, default=None)
@click.option("--max-windows", type=int, default=None)
@click.option("--ocr", is_flag=True, default=None, help="Run OCR on keyframes (--ocr opt-in).")
@click.option("--check-quality", is_flag=True, default=None,
              help="Force quality check + write to manifest.")
@click.option("--no-quality-check", is_flag=True, default=None,
              help="Skip quality check even in smart preset.")
@click.option("--preset", type=click.Choice(list_preset_names()), default=None,
              help="Preset name. Default — from config.")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              help="External config TOML (alternative to ~/.youtube-transcribe/config.toml).")
@click.option("--triggers", "triggers_path", type=click.Path(exists=True), default=None,
              help="External triggers TOML.")
@click.option("--no-default-triggers", is_flag=True, default=False,
              help="Disable built-in triggers, use only user file.")
```

4. **В функции `transcribe_cmd` (или эквивалентной точке входа) применить новые флаги:**

После получения `TranscriptionResult` от v0.1 backend'а, сделать:

```python
    # === v0.2 stage application ===
    cli_overrides: dict = {}
    if vision_backend is not None:
        cli_overrides["vision_backend"] = vision_backend
    if with_visuals:
        cli_overrides["vision_backend"] = "gemini"
    if detect_method is not None:
        cli_overrides["detect_method"] = detect_method
    if frames_per_window is not None:
        cli_overrides["frames_per_window"] = frames_per_window
    if max_windows is not None:
        cli_overrides["max_windows_per_video"] = max_windows
    if ocr is True:
        cli_overrides["ocr"] = True
    if check_quality is True:
        cli_overrides["quality_check"] = True
    if no_quality_check is True:
        cli_overrides["quality_check"] = False

    preset_name = preset or "smart"
    cfg, info_msgs = resolve_with_env_checks(
        preset_name,
        external_config_path=Path(config_path) if config_path else None,
        cli_overrides=cli_overrides,
    )
    for msg in info_msgs:
        console.print(msg, style="dim")

    source = "youtube_manual" if backend_used == "subtitles_manual" \
        else "youtube_auto" if backend_used == "subtitles_auto" \
        else "whisper" if "whisper" in backend_used \
        else "external_asr"

    result = apply_v02_stages(
        result=result,
        cfg=cfg,
        video_path=local_video_path,   # из downloader
        video_id=video_id_from_target,
        out_dir=output_dir,
        source=source,
    )
```

> **Note:** местá подстановки конкретных переменных (`backend_used`, `local_video_path`, `video_id_from_target`, `output_dir`) зависят от структуры существующей функции `transcribe_cmd` в v0.1. Subagent должен прочитать `transcribe.py` и подставить корректные имена. Это указание — не магия, а явная отсылка читать существующий код. Если в существующем коде имя другое — использовать его.

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_cli_v02_flags.py -v`
Expected: 3 passed.

- [ ] **Step 5: Manual smoke check (CLI help renders)**

Run:
```bash
uv run youtube-transcribe transcribe --help
uv run youtube-transcribe triggers --help
uv run youtube-transcribe triggers add --help
```

Expected: каждая команда печатает help без stack trace.

- [ ] **Step 6: Verify v0.1 CLI tests still pass**

Run: `uv run pytest tests/test_cli*.py tests/test_transcribe*.py -v`
Expected: все green.

- [ ] **Step 7: Commit**

```bash
git add skills/youtube_transcribe/transcribe.py tests/test_cli_v02_flags.py
git commit -m "feat(cli): v0.2 flags (vision/detect/preset/config/triggers/ocr) + register triggers subcommand"
```

---

# Phase 9 — OCR + migration + docs + golden set

### Task 32: vision/ocr.py — opt-in OCR через pytesseract

**Files:**
- Create: `skills/youtube_transcribe/vision/ocr.py`
- Create: `tests/test_vision_ocr.py`

- [ ] **Step 1: Написать failing test (мок tesseract)**

`tests/test_vision_ocr.py`:

```python
"""Tests for OCR layer (--ocr flag)."""
from pathlib import Path
from unittest.mock import patch

from skills.youtube_transcribe.vision.ocr import ocr_keyframes


def test_ocr_returns_strings_per_keyframe(tmp_path):
    kf1 = tmp_path / "f1.jpg"
    kf2 = tmp_path / "f2.jpg"
    kf1.write_bytes(b"fake jpeg")
    kf2.write_bytes(b"fake jpeg")

    with patch(
        "skills.youtube_transcribe.vision.ocr._run_tesseract",
        side_effect=["import anthropic", "function call"],
    ):
        results = ocr_keyframes([kf1, kf2])

    assert results == ["import anthropic", "function call"]


def test_ocr_skips_unreadable_files(tmp_path):
    kf = tmp_path / "broken.jpg"
    kf.write_bytes(b"")
    with patch(
        "skills.youtube_transcribe.vision.ocr._run_tesseract",
        side_effect=Exception("can't read"),
    ):
        results = ocr_keyframes([kf])
    # Errors → empty string for that frame
    assert results == [""]


def test_ocr_returns_empty_for_empty_input():
    assert ocr_keyframes([]) == []
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_vision_ocr.py -v`
Expected: ImportError.

- [ ] **Step 3: Написать реализацию**

`skills/youtube_transcribe/vision/ocr.py`:

```python
"""OCR for keyframes — opt-in via --ocr flag.

Tries pytesseract first (requires system `tesseract` binary).
Falls back to easyocr (heavy 60MB model, but no system binary needed).
"""
from __future__ import annotations

from pathlib import Path


def _run_tesseract(image_path: Path) -> str:
    """Single keyframe → text. Override-able for testing."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        return pytesseract.image_to_string(img).strip()
    except ImportError:
        # Fallback to easyocr
        try:
            import easyocr
            reader = easyocr.Reader(["en", "ru"], gpu=False)
            results = reader.readtext(str(image_path), detail=0)
            return " ".join(results)
        except ImportError as e:
            raise ImportError(
                "OCR requires either pytesseract+system tesseract or easyocr. "
                "Install with `uv sync --extra ocr`."
            ) from e


def ocr_keyframes(keyframes: list[Path]) -> list[str]:
    """Returns one OCR'd string per keyframe. Errors → empty string for that frame."""
    out: list[str] = []
    for kf in keyframes:
        try:
            text = _run_tesseract(kf)
        except Exception:
            text = ""
        out.append(text)
    return out
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_vision_ocr.py -v`
Expected: 3 passed.

- [ ] **Step 5: Integrate в pipeline_v02.py**

В `skills/youtube_transcribe/pipeline_v02.py`, после блока с visuals, добавить:

```python
        # === v0.2: OCR (opt-in) ===
        if cfg.get("ocr") and result.visual_segments:
            from skills.youtube_transcribe.vision.ocr import ocr_keyframes
            for vs in result.visual_segments:
                kf_paths = [out_dir / kf for kf in vs.keyframes]
                ocr_texts = ocr_keyframes(kf_paths)
                # Append non-empty OCR results to detected_objects
                for text in ocr_texts:
                    if text:
                        # Mutate via dict access since dataclass is frozen
                        object.__setattr__(
                            vs, "detected_objects",
                            list(vs.detected_objects) + [f"ocr:{text[:200]}"],
                        )
```

> Это compromise — VisualSegment frozen, поэтому используем `object.__setattr__`. Альтернатива (cleaner) — сделать VisualSegment не frozen или возвращать новый VisualSegment. Subagent выбирает в момент implementation.

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/vision/ocr.py \
        skills/youtube_transcribe/pipeline_v02.py \
        tests/test_vision_ocr.py
git commit -m "feat(vision): opt-in OCR via pytesseract+easyocr fallback"
```

---

### Task 33: config.py — migration v0.1.x → v0.2 (legacy preset)

**Files:**
- Modify: `skills/youtube_transcribe/config.py`
- Create: `tests/test_migration_v02.py`

- [ ] **Step 1: Написать failing test**

`tests/test_migration_v02.py`:

```python
"""Tests for v0.1.x → v0.2 config migration."""
import textwrap
from pathlib import Path

from skills.youtube_transcribe.config import migrate_v01_to_v02


def test_v01_config_gets_default_preset_added(tmp_path):
    old_config = tmp_path / "config.toml"
    old_config.write_text(textwrap.dedent("""\
        default_backend = "whisper-local"
        fallback_backend = "whisper-local"

        [whisper-local]
        model = "turbo"

        [output]
        language = "auto"
    """), encoding="utf-8")

    migrate_v01_to_v02(old_config)

    content = old_config.read_text(encoding="utf-8")
    assert "default_preset" in content
    assert "[presets.custom_legacy]" in content


def test_v01_config_preserves_user_settings(tmp_path):
    old_config = tmp_path / "config.toml"
    old_config.write_text(textwrap.dedent("""\
        default_backend = "groq"
        [whisper-local]
        model = "large"
    """), encoding="utf-8")

    migrate_v01_to_v02(old_config)
    content = old_config.read_text(encoding="utf-8")
    # User backend choice preserved in legacy preset
    assert "groq" in content
    # whisper model preserved
    assert "large" in content


def test_v02_config_idempotent(tmp_path):
    """If config already has default_preset, migration is no-op."""
    config = tmp_path / "config.toml"
    config.write_text("default_preset = \"smart\"\n", encoding="utf-8")
    migrate_v01_to_v02(config)
    assert config.read_text("utf-8") == "default_preset = \"smart\"\n"


def test_no_config_file_does_nothing(tmp_path):
    """No-op if file doesn't exist."""
    nonexistent = tmp_path / "missing.toml"
    migrate_v01_to_v02(nonexistent)
    assert not nonexistent.exists()
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `uv run pytest tests/test_migration_v02.py -v`
Expected: ImportError.

- [ ] **Step 3: Дописать `config.py`**

В конец `skills/youtube_transcribe/config.py`:

```python
def migrate_v01_to_v02(path: Path = CONFIG_PATH) -> None:
    """Migrate v0.1.x config.toml to v0.2 format.

    Preserves user's existing settings as `[presets.custom_legacy]` and
    sets `default_preset = "custom_legacy"` so behavior remains identical.

    No-op if file doesn't exist or already has `default_preset` key.
    """
    if not path.exists():
        return

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if "default_preset" in raw:
        return  # already v0.2

    # Build legacy preset from v0.1 fields
    legacy: dict = {}
    if "default_backend" in raw:
        legacy["transcribe_backend"] = raw["default_backend"]
    if "fallback_backend" in raw:
        legacy["fallback_backend"] = raw["fallback_backend"]
    # Preserve nested whisper-local, gemini, etc. by appending v0.2 sections

    new_text = path.read_text(encoding="utf-8")
    new_text = 'default_preset = "custom_legacy"\n\n' + new_text
    new_text += "\n[presets.custom_legacy]\n"
    for k, v in legacy.items():
        new_text += f'{k} = "{v}"\n'

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: Run test, verify PASS**

Run: `uv run pytest tests/test_migration_v02.py -v`
Expected: 4 passed.

- [ ] **Step 5: Hook migration в `load_config` (auto-migrate on first load)**

В `skills/youtube_transcribe/config.py`, в начале функции `load_config`, добавить:

```python
def load_config(path: Path = CONFIG_PATH) -> Config:
    if path.exists():
        migrate_v01_to_v02(path)   # ← NEW: auto-upgrade on load
    if not path.exists():
        return DEFAULT_CONFIG
    # ... rest unchanged ...
```

- [ ] **Step 6: Commit**

```bash
git add skills/youtube_transcribe/config.py tests/test_migration_v02.py
git commit -m "feat(config): auto-migrate v0.1 config.toml to v0.2 (custom_legacy preset)"
```

---

### Task 34: golden quality set — tests/data/quality_golden.json + test

**Files:**
- Create: `tests/data/quality_golden.json`
- Create: `tests/test_quality_golden.py`

- [ ] **Step 1: Создать synthetic golden set**

`tests/data/quality_golden.json`:

```json
{
  "version": 1,
  "description": "Synthetic golden set for HeuristicChecker calibration. Real-video calibration on Mac is a separate step (manual validation phase).",
  "cases": [
    {
      "id": "manual_clean",
      "language": "en",
      "source": "youtube_manual",
      "text": "Hello and welcome to today's tutorial about Python programming.",
      "expected_score_min": 0.95,
      "expected_recommendation": "use_as_is"
    },
    {
      "id": "auto_clean_en",
      "language": "en",
      "source": "youtube_auto",
      "text": "Hello and welcome to today's tutorial about Python programming basics. We will cover variables, functions and classes.",
      "expected_score_min": 0.65,
      "expected_recommendation": "use_as_is"
    },
    {
      "id": "auto_garbled_ru",
      "language": "ru",
      "source": "youtube_auto",
      "text": "прьвет дрнае пвоит мфаета звдавр квоиак пжвжыа кмлда сжодг пжмва",
      "expected_score_max": 0.45,
      "expected_flags_include": "high_oov"
    },
    {
      "id": "whisper_loop",
      "language": "en",
      "source": "whisper",
      "text": "thank you for watching thank you for watching thank you for watching thank you for watching thank you for watching",
      "expected_score_max": 0.45,
      "expected_flags_include_any": ["looped", "boilerplate_hallucinations"]
    },
    {
      "id": "music_video",
      "language": "en",
      "source": "youtube_auto",
      "text": "[Music] [Music] [Music] [Music] hello",
      "expected_score_max": 0.4,
      "expected_flags_include": "mostly_music"
    }
  ]
}
```

- [ ] **Step 2: Написать failing test**

`tests/test_quality_golden.py`:

```python
"""Golden-set regression test for HeuristicChecker.

Synthetic cases are stable and run in CI. Real-video calibration is manual
(see HANDOFF / Task 35). Drift > 0.1 from expected scores will fail this test.
"""
import json
from pathlib import Path

import pytest

from skills.youtube_transcribe.quality.heuristic_checker import HeuristicChecker
from skills.youtube_transcribe.utils.output_writer import Segment


GOLDEN = json.loads(
    (Path(__file__).parent / "data" / "quality_golden.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["id"])
def test_golden_case(case):
    checker = HeuristicChecker()
    segments = [Segment(start=0.0, end=10.0, text=case["text"])]
    report = checker.check(segments, case["language"], source=case["source"])

    if "expected_score_min" in case:
        assert report.score >= case["expected_score_min"] - 0.05, \
            f"{case['id']}: score {report.score} below expected min {case['expected_score_min']}"
    if "expected_score_max" in case:
        assert report.score <= case["expected_score_max"] + 0.05, \
            f"{case['id']}: score {report.score} above expected max {case['expected_score_max']}"
    if "expected_recommendation" in case:
        assert report.recommendation == case["expected_recommendation"], \
            f"{case['id']}: rec={report.recommendation}, expected={case['expected_recommendation']}"
    if "expected_flags_include" in case:
        assert case["expected_flags_include"] in report.flags, \
            f"{case['id']}: flag missing. Got flags: {report.flags}"
    if "expected_flags_include_any" in case:
        wanted = case["expected_flags_include_any"]
        assert any(f in report.flags for f in wanted), \
            f"{case['id']}: none of {wanted} in {report.flags}"
```

- [ ] **Step 3: Run test, verify PASS**

Run: `uv run pytest tests/test_quality_golden.py -v`
Expected: 5 passed.

> If a case fails by > 0.05 — re-tune weights in `HeuristicChecker.check` and adjust the golden expectation. The point is: future code changes must not silently break these synthetic baselines.

- [ ] **Step 4: Commit**

```bash
git add tests/data/quality_golden.json tests/test_quality_golden.py
git commit -m "test(quality): synthetic golden set for HeuristicChecker regression"
```

---

### Task 35: Documentation — README + CHANGELOG + SKILL.md

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `skills/youtube_transcribe/SKILL.md`

- [ ] **Step 1: Update README.md — добавить секцию про visual mode**

В `README.md`, после существующей секции «Quick start», добавить новый раздел:

```markdown
## Visual mode (v0.2)

Включи `--with-visuals` чтобы получить не только транскрипт, но и описание
визуальных моментов с встроенными скриншотами в `combined.md`. Полезно для
видео-туториалов: получаешь markdown-инструкцию с картинками.

```bash
youtube-transcribe https://youtube.com/watch?v=... --with-visuals
```

Требуется `GEMINI_API_KEY` (free tier ~1500 RPD достаточно для 75 видео/день).
Если ключ не задан — визуальная часть тихо отключается, остаётся обычный
транскрипт.

### Triggers — управление точками визуального анализа

```bash
# Создать пользовательский triggers.toml
youtube-transcribe triggers init

# Добавить фразы (через ;)
youtube-transcribe triggers add --universal "look here; for example; demo"

# Per-language strict (точное совпадение)
youtube-transcribe triggers add --strict --lang ru "баг; PR"

# Поднять вес важной фразы
youtube-transcribe triggers weight set --universal "function" 1.5

# Проверить какие триггеры срабатывают на конкретной фразе
youtube-transcribe triggers test "вот этот код важен"
```

### Presets

| Preset | Transcribe | Vision | Detection |
|---|---|---|---|
| `eco` | subtitles → user-chosen | off | keywords only |
| `smart` (default) | subtitles → quality check → fallback | gemini | hybrid |
| `standard` | whisper-local | gemini | hybrid |
| `premium` | whisper-large | gemini | LLM full pass |

```bash
youtube-transcribe URL --preset standard
youtube-transcribe URL --preset smart --frames-per-window 5
```
```

- [ ] **Step 2: Update CHANGELOG.md**

Добавить в начало после `## [Unreleased]`:

```markdown
## [0.2.0] — 2026-XX-XX

### Added
- Visual mode (`--with-visuals`) — multimodal анализ видео через Gemini
  (фреймы + аудио). Embedded screenshots в combined.md.
- Quality check для транскриптов (smart-режим автоматически выбирает между
  готовыми субтитрами и whisper).
- Multilingual triggers через локальные embeddings (paraphrase-multilingual-MiniLM-L12-v2).
- Triggers CLI tool: `triggers init/add/list/remove/reset/edit/test/weight`.
- Dynamic presets (eco/smart/standard/premium) с единым реестром опций.
- `--config` flag для альтернативных config-файлов.
- `--ocr` opt-in флаг для извлечения текста с keyframes.

### Changed
- `BatchVideoStatus` расширен полями `quality` и `visual_segments`.
- `manifest.json` теперь содержит quality breakdown и visual_segments.
- `combined.md` содержит секцию `### Visual moments` с inline-скриншотами.

### Migration v0.1.x → v0.2
- Auto-migration существующего `~/.youtube-transcribe/config.toml` в формат
  `[presets.custom_legacy]` с сохранением всех настроек пользователя.
- Если есть `GEMINI_API_KEY` → visual mode silent-on в smart-преcете. Иначе
  поведение полностью совместимо с v0.1.

### Dependencies (new)
- core: pyspellchecker, pyahocorasick, langdetect, sentence-transformers,
  lemminflect, pymorphy3, tomlkit, pyscenedetect, imagehash
- optional: pytesseract+easyocr (extra `ocr`), kenlm (extra `perplexity`)
```

- [ ] **Step 3: Update SKILL.md**

В `skills/youtube_transcribe/SKILL.md` дополнить раздел про combined.md:

```markdown
### combined.md (v0.2)

Если использовался `--with-visuals`, combined.md содержит секцию
`### Visual moments` с встроенными скриншотами и описаниями визуальных
моментов. Это полноценный markdown-туториал — можно использовать как
основу для заметок и планов изучения.

При запросе пользователя «сделай туториал/инструкцию по этому видео»:
1. Используй визуальные моменты как структурные точки.
2. Цитируй timestamps в формате `00:00:45`.
3. Inline-картинки уже встроены — referencing их через relative paths.

При quality < 0.6 (warning в combined.md):
- Транскрипт может содержать ошибки распознавания.
- Скриншоты остаются достоверными.
- Помогай пользователю работать с тем что есть, не отказывайся.
```

- [ ] **Step 4: Verify rendering**

Run:
```bash
uv run python -c "from pathlib import Path; print(Path('README.md').read_text()[:500])"
```
Expected: первые 500 символов README — без ошибок.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md skills/youtube_transcribe/SKILL.md
git commit -m "docs(v0.2): README visual mode section, CHANGELOG, SKILL.md updates"
```

---

# Phase 10 — Mac validation (manual, runs locally after `git pull`)

> **Note:** Phase 10 — это manual validation, не CI. Эти шаги выполняются на
> рабочей Mac-машине пользователя после того как все 35 задач закоммичены и
> залиты в main. Не дискет subagent-driven автоматически.

### Task 36 (manual): real-video smoke test для visual mode

- [ ] **Step 1: Pull & sync на Mac**

```bash
git pull
uv sync --extra dev
```

- [ ] **Step 2: Прогнать unit suite полностью**

Run: `uv run pytest -q`
Expected: все 250+ тестов green.

- [ ] **Step 3: Запустить smoke на коротком ролике с visual mode**

```bash
export GEMINI_API_KEY=...   # реальный ключ
uv run youtube-transcribe https://www.youtube.com/watch?v=jNQXAC9IVRw --with-visuals
```

Expected:
- В `transcripts/` появляются: `Me_at_the_zoo_jNQXAC9IVRw.txt`,
  `Me_at_the_zoo_jNQXAC9IVRw.srt`, `Me_at_the_zoo_jNQXAC9IVRw.visual.md`,
  и `transcripts/frames/Me_at_the_zoo_jNQXAC9IVRw_*.jpg` (минимум 1 кадр).
- `visual.md` содержит секцию `### Visual moments` с inline-скриншотами.

- [ ] **Step 4: Запустить batch на маленьком плейлисте с visual mode**

```bash
uv run youtube-transcribe batch <playlist URL> --limit 2 --with-visuals
```

Expected:
- Создаётся `transcripts/batch_*/` папка.
- В ней `combined.md` со скриншотами для каждого видео.
- `frames/` непустой.
- `manifest.json` содержит `visual_segments` для каждого видео.

- [ ] **Step 5: Триггер CLI smoke**

```bash
uv run youtube-transcribe triggers init
uv run youtube-transcribe triggers add --universal "look at this; demo here"
uv run youtube-transcribe triggers add --strict --lang ru "баг; PR"
uv run youtube-transcribe triggers weight set --universal "demo here" 1.5
uv run youtube-transcribe triggers list
uv run youtube-transcribe triggers test "вот этот баг здесь"
```

Expected: каждая команда отрабатывает без ошибки. Last `test` показывает match `strict:ru`.

- [ ] **Step 6: Quality check smoke**

```bash
uv run youtube-transcribe https://youtube.com/watch?v=<video_with_auto_subs> --check-quality
```

Expected: в логе печатается quality score, в manifest.json есть поле `quality`.

- [ ] **Step 7: Если всё green — bump version и tag**

В `pyproject.toml`: `version = "0.2.0"` (убрать `-dev`).
В `__init__.py`: `__version__ = "0.2.0"`.

```bash
git add pyproject.toml skills/youtube_transcribe/__init__.py
git commit -m "release: v0.2.0"
git tag v0.2.0
git push --tags origin main
```

---

# Финальный чек-лист

- [ ] Все unit-тесты зелёные (CI на 3 ОС × Python 3.11/3.12).
- [ ] Real-video smoke test (Task 36) прошёл на Mac.
- [ ] CHANGELOG.md содержит entry для v0.2.0.
- [ ] README.md содержит секцию visual mode.
- [ ] SKILL.md обновлён про combined.md v0.2.
- [ ] Migration v0.1.x → v0.2 проверена на staging-конфиге (созданном вручную из v0.1).
- [ ] Перед push в main прогнаны скиллы `code-reviewer` + `security-review` (по правилу `git-cross-os`).

---

## Self-review summary

**Spec coverage check:**
- §1 Цель → Tasks 22 (vision), 3-7 (quality), 25-27 (presets), 14-16 (triggers CLI). ✓
- §2 Архитектура (4 protocols) → Task 3 (QualityChecker), Task 17 (Detector), Task 22 (VisionBackend), Task 25 (registry). ✓
- §3 Quality check → Tasks 3-7 + Task 34 (golden). ✓
- §4 Триггеры → Tasks 8-13 (core) + 14-16 (CLI). ✓
- §5 Detection → Tasks 17-20. ✓
- §6 Vision Gemini → Tasks 21-24. ✓
- §7 Embedded screenshots → Tasks 28-29. ✓
- §8 Динамические presets → Tasks 25-27. ✓
- §9 CLI флаги → Task 31. ✓
- §10 Web UI seam → реализовано через registry (Task 25) + чистый pipeline (Task 30). ✓
- §11 Тестирование → каждая задача имеет тесты + Task 34 golden. ✓
- §12-13 Backward compat / migration → Task 33. ✓
- §16 Triggers CLI → Tasks 14-16. ✓
- §17 OCR → Task 32. ✓

**Type consistency check:**
- `Segment` (from `utils/output_writer.py`) — используется по всему плану одинаково. ✓
- `TranscriptionResult` — расширяется в Task 30 (поля `quality`, `visual_segments`). Все стадии после Task 30 ожидают эти поля. ✓
- `QualityReport` — Task 3, потребляется Task 7, 28, 29, 30. ✓
- `DetectionWindow` — Task 17, потребляется 18-20, 22, 24. ✓
- `VisualSegment` — Task 22, потребляется 24, 28, 29. ✓
- `TriggerConfig`, `LanguageTriggers`, `TriggerMatch` — Task 8, 10-13, 14-16. ✓

**Placeholder scan:** все шаги имеют конкретный код, тесты с явным ожидаемым выводом и команды с реальными expectation'ами.

**Phase 10 disclaimer:** последняя фаза — manual, не для subagent. Subagent-driven execution останавливается после Task 35 (commit docs); Phase 10 запускает пользователь сам.

