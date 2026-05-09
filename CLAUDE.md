# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Состояние репо

Реализация **ещё не начиналась**. В репо только дизайн + план, кода нет:

- Спека (источник истины): [docs/specs/2026-05-08-youtube-transcribe-design.md](docs/specs/2026-05-08-youtube-transcribe-design.md) — 19 пронумерованных секций.
- План реализации (30 тасок, 7 фаз): [docs/plans/2026-05-08-youtube-transcribe.md](docs/plans/2026-05-08-youtube-transcribe.md). Каждая таска самодостаточна (файлы, код, тесты, commit-команда).
- Cross-machine handoff: [HANDOFF.md](HANDOFF.md).

Если спека и план расходятся — верить спеке, чинить план.

## Как продолжать работу

Дефолтный режим выполнения — **subagent-driven**: один свежий subagent на одну Task плана, ревью между тасками. Перед стартом новой таски: `git log --oneline` → понять, на какой Task остановились.

```
Skill superpowers:subagent-driven-development → диспатчишь Task N → ревью → Task N+1
```

Pre-flight перед Task 1: проверить `uv --version` (нужно 0.4+). На Mac доп. требования (ffmpeg, arm64-Python, macOS ≥13.5) — см. HANDOFF.md.

## Команды (после Task 1)

```bash
uv sync --extra dev                    # установить deps (pyproject.toml появляется в Task 1)
uv run pytest -v                       # все unit-тесты
uv run pytest tests/test_xxx.py::test_yyy   # один тест
RUN_E2E_SMOKE=1 uv run pytest -v       # включить опциональные e2e (бьют по реальному YouTube)
uv run youtube-transcribe --help       # CLI после Task 20+
```

Запускать `uv sync` **до** Task 1 нельзя — `pyproject.toml` ещё не создан.

## Архитектурные инварианты

**Имя пакета vs имя CLI.** Skill называется `youtube-transcribe` (kebab-case) — это имя плагина, slash-команды и CLI-бинарника. Python-пакет лежит в `skills/youtube_transcribe/` (snake_case) — иначе импорты не работают. Использовать оба варианта по контексту, не путать.

**Абстракция бэкендов.** `backends/base.py` определяет `Transcriber` (Protocol) и `TranscriptionResult` (dataclass). Все 8 бэкендов (subtitles, whisper-local, gemini, groq, openai, deepgram, assemblyai, custom) — взаимозаменяемые реализации одного интерфейса. Тесты пишутся **против интерфейса**, внешние SDK мокаются. Добавить новый бэкенд = реализовать `Transcriber` + зарегистрировать в реестре, остальной код не трогается.

**Smart-режим — не бэкенд, а композиция.** При `default_backend = "smart"` сначала пробуется `subtitles` (если URL — YouTube), затем `fallback_backend` (по умолчанию `whisper-local`). Логика собирается на верхнем уровне, не в бэкендах.

**Whisper-local — две физические реализации, один интерфейс.** На macOS arm64 — `mlx-whisper`, везде ещё — `faster-whisper`. Выбор делает `utils/platform_detect.py` автоматически по результату детекта (label/backend_impl/device/vram). `MODEL_MAP` (спека §5.2) задаёт пары `mlx`/`faster` для каждой модели; `distil` существует только на `faster` — на Mac должна быть понятная ошибка с exit code 4, не stack trace.

**Конфиг и секреты.**
- `~/.youtube-transcribe/config.toml` — настройки (TOML, читается `tomli`/пишется `tomli-w`).
- `~/.youtube-transcribe/.env` — API-ключи, права `0600` на Unix.
- Приоритет загрузки: env vars процесса > `.env` > ошибка с инструкцией.
- Ключи **никогда** не печатать целиком в логи (даже при `--verbose`) — маскировать как `sk-***...XYZ`. На запрос «покажи мой ключ» — отказ, отсылка в `.env`.

## Cross-OS специфика

Разработка идёт на **Windows**, валидация на **Mac** — последняя фаза плана (Tasks 28–30). `mlx-whisper` на этапе кодинга **не тестируется на хост-машине разработчика** — реализация по официальной доке, отладка на Mac через git pull → запуск → фикс.

`.gitattributes` уже фиксирует EOL: `*.py *.md *.toml` → `LF`, `*.ps1 *.bat *.cmd` → `CRLF`. Не переопределять. `uv.lock` намеренно не коммитим (cross-platform skill, lock дал бы Mac/Windows-расходимость на mlx-whisper). `.python-version` тоже игнорируется.

`mlx-whisper` подцепляется PEP 508 marker'ом `sys_platform == 'darwin' and platform_machine == 'arm64'` — не импортировать напрямую без проверки платформы, иначе на Windows будет ImportError.

**Симметричный marker на `faster-whisper`:** `sys_platform != 'darwin' or platform_machine != 'arm64'` (де Морган от `not (... and ...)` — стандарт PEP 508 не поддерживает `not (...)` через hatchling). Причина — `faster-whisper 1.2+` тянет `onnxruntime 1.26+`, у которого нет wheel под macOS arm64. На Mac arm64 используется только mlx-whisper, на Windows/Linux/x86_64-Mac — только faster-whisper. `backends/whisper_local.py` (Tasks 9-10) импортирует обе библиотеки внутри функций после `platform_detect`, не на module-level.

## Тестирование

- **Уровень 1:** unit с моками — `subprocess`/`platform` для `platform_detect`, SDK-клиенты для каждого бэкенда. Должны зеленеть на любой ОС без ключей и без интернета.
- **Уровень 2:** e2e smoke под env-флагом `RUN_E2E_SMOKE=1` — реальный 19-сек ролик с YouTube. По умолчанию выключены, включаются вручную и в CI с секретами.
- **Уровень 3:** ручной прогон на Mac (Tasks 28–29) — wizard, реальная транскрипция через mlx-whisper, проверка всех 5 моделей.

TDD-стиль обязателен (см. план: failing test → impl → pass → commit).

## Контракт перед push в main

Скилл `git-cross-os` (глобальный) требует прогон `code-reviewer` + `security-review` перед финальным push. Соблюдать.

## Out of scope для v1

Диаризация, чанкинг видео >2ч, постобработка через локальную LLM, авто-саммари внутри skill, web UI, стриминг, не-OpenAI-compat провайдеры в `custom`. Если возникает запрос на это — фиксировать в roadmap (README), а не докручивать в текущую итерацию.
