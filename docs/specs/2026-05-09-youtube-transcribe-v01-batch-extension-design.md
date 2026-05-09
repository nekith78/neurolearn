# Дизайн-документ: youtube-transcribe v0.1 — расширение batch-режима

**Дата:** 2026-05-09
**Статус:** Черновик к согласованию
**Автор:** brainstorm с пользователем (Claude Code)
**Базовая спека:** [docs/specs/2026-05-08-youtube-transcribe-design.md](2026-05-08-youtube-transcribe-design.md) (v0.1)

---

## 1. Контекст и цель расширения

Базовая спека v0.1 проектирует **single-режим**: 1 URL/файл → 1 транскрипт. По итогам брейнсторма к ней добавляется **batch-режим**:

> «Кинь URL канала YouTube или пачку ссылок — получи N транскриптов и единый combined.md для последующей обработки в Claude-чате (заметка, сводка, план изучения).»

Расширение **встраивается прямо в v0.1**, до начала кодинга. Не вырастает в v0.2 поверх готового артефакта — single и batch с самого начала спроектированы как один pipeline (single = batch из 1 элемента).

### Главный пользовательский сценарий

Пользователь хочет изучить тему через видео-контент. Сейчас:
1. Указывает URL канала или передаёт пачку URL: `youtube-transcribe batch https://youtube.com/@anthropicai --limit 10 --backend subtitles`.
2. Skill разворачивает канал в 10 свежих видео (без скачивания, только метадата), последовательно транскрибирует каждое, складывает результат в изолированную batch-папку.
3. Получает один `combined.md` со всеми текстами + метой (заголовки, даты, длительность, бэкенд).
4. В Claude-чате говорит «прочти `combined.md` и сделай заметку по теме X» — Claude работает с уже оплаченной подпиской, без дополнительных API-ключей в skill.

### Что входит в это расширение

- Sub-команда `youtube-transcribe batch <inputs...>`.
- Источники входа: URL inline, URL канала/плейлиста (yt-dlp expand), файл со списком URL.
- Резолвер `Resolver` — превращает любой вход в плоский список `ResolvedTarget` **без скачивания медиа**.
- Структурированный выход: изолированная batch-папка + `combined.md` + `manifest.json` + `errors.log`.
- `continue-on-error` по умолчанию, `--fail-fast` по флагу.
- Архитектурный задел под фильтры (`--since`, `--until`, `--min-duration`, `--max-duration`, `--no-shorts`) — поля в `ResolverFilters` присутствуют, реализация в v0.3.

### Что отложено

- Поиск по тегам/теме (`batch --search "..."`) → v0.3.
- Instagram (`batch --instagram @user` + период) → v0.4.
- Параллелизм (`--workers N`), кэш (`--skip-existing`), фильтры по дате/длительности/shorts → v0.3.
- LLM-сводка внутри skill (`--summarize`) → open / v1.x. В v0.1–v0.x сводку делает Claude в чате, читая `combined.md`.

См. §9 «Roadmap».

---

## 2. Scope v0.1 (расширенный)

**Что теперь включено в первый релиз:**
- Single-режим (как в базовой спеке §1–§18).
- **NEW:** batch-режим с тремя источниками входа.
- **NEW:** `combined.md` + `manifest.json` + `errors.log`.
- **NEW:** `--limit N` для канала/плейлиста (default 10).
- **NEW:** архитектурный задел под фильтры v0.3.

**Что остаётся out-of-scope для v0.1:**

| Фича | Куда отложено | Причина |
|---|---|---|
| `batch --search "..."` (поиск по тегам) | v0.3 | Нужен YouTube Data API ключ или yt-dlp `ytsearchN:` + ранжирование «релевантности и качества» — отдельная подсистема |
| `batch --instagram @user` | v0.4 | Анти-бот защита Instagram, cookies, отдельная стратегия |
| `--summarize` (LLM-сводка через CLI) | open | Сводку делает Claude-чат через `combined.md` — без новых зависимостей и ключей |
| `--workers N` | v0.3 | whisper-local не выигрывает от параллелизма; cloud упирается в rate-limits |
| `--skip-existing` (кэш по video_id) | v0.3 | Усложнение поведения, добавляется по фидбеку |
| Фильтры: `--since/--until/--min-duration/--max-duration/--no-shorts` | v0.3 | Поля в `ResolverFilters` уже зарезервированы — добавить только проброс в yt-dlp opts |

---

## 3. Архитектура

### Принцип

Single и batch разделяют **один pipeline**. Двух разных кодопутей в `transcribe.py` не делаем — это рассинхрон при правках. Single = batch из 1 target.

### Новые компоненты

#### `utils/resolver.py`

```python
@dataclass
class ResolvedTarget:
    url: str
    title: str | None
    upload_date: date | None
    duration_sec: int | None
    source: Literal["inline", "file", "channel", "playlist", "single"]
    video_id: str | None       # для дедупликации; None для не-YouTube источников

@dataclass
class ResolverFilters:
    limit: int = 10
    # задел под v0.3 (в v0.1 значения не используются, поля присутствуют):
    since: date | None = None
    until: date | None = None
    min_duration_sec: int | None = None
    max_duration_sec: int | None = None
    include_shorts: bool = True

def resolve(
    inputs: list[str],
    from_file: Path | None,
    filters: ResolverFilters,
) -> list[ResolvedTarget]: ...
```

Внутри Resolver вызывает `downloader.expand_channel_or_playlist(url, limit)` (см. ниже) для разворота каналов/плейлистов. Все обращения к yt-dlp инкапсулированы в `downloader.py` — Resolver не знает про yt-dlp напрямую. Это согласуется с базовой спекой §11 (downloader — единственная обёртка над yt-dlp).

Используется `extract_flat=True` — получаем **только метадату**, не медиа. Дёшево даже на больших каналах.

#### `utils/output_writer.py` — новые функции

```python
@dataclass
class BatchMeta:
    """Метадата batch-прогона. Передаётся в writers, попадает в YAML/JSON."""
    batch_name: str
    created_at: datetime
    source_type: Literal["channel", "playlist", "file", "inline", "mixed"]
    source_url: str | None       # None для file/inline/mixed
    backend: str
    backend_options: dict        # whisper_model / gemini_model / etc.
    language: str

@dataclass
class BatchFailure:
    """Один отказ внутри batch."""
    target: ResolvedTarget
    stage: Literal["resolve", "download", "backend", "write"]
    error: Exception
    hint: str | None             # подсказка пользователю

def write_combined_md(
    results: list[TranscriptionResult],
    batch_meta: BatchMeta,
    output_dir: Path,
) -> Path: ...

def write_manifest_json(
    results: list[TranscriptionResult],
    failures: list[BatchFailure],
    batch_meta: BatchMeta,
    output_dir: Path,
) -> Path: ...

def write_errors_log(
    failures: list[BatchFailure],
    output_dir: Path,
) -> Path | None: ...   # None если ошибок не было
```

### Изменения в существующих компонентах

#### `transcribe.py` — два sub-command'а поверх общего core

```python
def run_pipeline(target: ResolvedTarget, config: Config) -> TranscriptionResult:
    """Core: один target → один результат. Используется обеими sub-командами."""

@cli.command("transcribe")
def cmd_transcribe(input: str, **opts):
    """Single-режим. Также вызывается без sub-команды: youtube-transcribe <URL>."""
    targets = resolve([input], from_file=None, filters=ResolverFilters())  # один и тот же Resolver
    assert len(targets) == 1                  # single = batch из 1
    result = run_pipeline(targets[0], config)
    write_outputs_single(result, output_dir)

@cli.command("batch")
def cmd_batch(inputs: list[str], from_file: Path | None, limit: int, fail_fast: bool, **opts):
    targets = resolve(inputs, from_file, ResolverFilters(limit=limit))
    batch_dir = create_batch_dir(output_dir, batch_name)
    results, failures = [], []
    for target in targets:
        try:
            result = run_pipeline(target, config)
            write_outputs_per_video(result, batch_dir / "videos", index)
            results.append(result)
        except Exception as e:
            failures.append(BatchFailure(target, e))
            if fail_fast: raise
    write_combined_md(results, batch_meta, batch_dir)
    write_manifest_json(results, failures, batch_meta, batch_dir)
    if failures: write_errors_log(failures, batch_dir)
    print_summary(results, failures, batch_dir)
```

Single-форма без sub-команды (`youtube-transcribe <URL>`) сохраняется через Click default-routing — чтобы базовая спека §8 не ломалась.

#### `utils/downloader.py`

Добавляются две функции (обе используют yt-dlp `extract_flat=True`, без скачивания медиа):
```python
def probe_input(url_or_path: str) -> tuple[Literal["video", "playlist", "local"], dict]:
    """Определить тип входа: одиночное видео / канал-или-плейлист / локальный файл.
    Возвращает (kind, raw_metadata_dict)."""

def expand_channel_or_playlist(url: str, limit: int) -> list[ChannelEntry]:
    """Развернуть канал/плейлист в первые N entries. Только метадата."""
```

`probe_input` и `expand_channel_or_playlist` — единственные новые точки входа в yt-dlp в обход существующего downloader-API. Все остальные обращения к yt-dlp (скачивание аудио, обработка ошибок 403/401) — без изменений по базовой спеке §11.

### Поток данных

```
batch <inputs>
  → Resolver.resolve()                          → list[ResolvedTarget]
  → for target in targets:
        run_pipeline(target, config)            → TranscriptionResult | Exception
            ↳ скачивание аудио в системный temp (tempfile.TemporaryDirectory)
            ↳ транскрибация выбранным бэкендом
            ↳ авто-удаление temp в finally
  → output_writer:
        per-video .txt + .srt в <batch>/videos/
        combined.md в корне batch-папки
        manifest.json в корне
        errors.log если были ошибки
  → Rich summary table в stdout
```

### Хранение временных аудио-файлов

**Системный temp** через `tempfile.TemporaryDirectory()`. После транскрибации одного видео папка авто-чистится в `finally`-блоке. На диске в любой момент времени лежит **один mp3** (~25–30 MB на час видео), а не 50 разом.

При флаге `--keep-audio` копия каждого mp3 уезжает в `<batch>/audio/NN_<video_id>.mp3`.

---

## 4. CLI контракт

### Главная команда (single, обратная совместимость)

```
youtube-transcribe <URL_или_путь> [опции]            # эквивалент `transcribe`
youtube-transcribe transcribe <URL_или_путь> [опции] # явная форма
```

Все флаги из базовой спеки §8 работают без изменений.

### Sub-команда `batch`

```
youtube-transcribe batch <input> [<input> ...] [опции]

Источники входа (можно комбинировать):
  <input>                        URL видео, URL канала, URL плейлиста
  --from-file PATH               Файл со списком URL (1 на строку, # — комментарий)

Фильтры (для канала/плейлиста):
  --limit N                      Сколько видео взять (default: 10)

  # ↓ задел на v0.3 — поля присутствуют в ResolverFilters,
  #   флаги не реализованы, документируются в roadmap:
  # --since YYYY-MM-DD
  # --until YYYY-MM-DD
  # --min-duration SEC
  # --max-duration SEC
  # --no-shorts / --include-shorts

Выход:
  --output-dir DIR               Корень для batch-папок (default: ./transcripts)
  --batch-name NAME              Имя batch-папки (default: batch_<timestamp>_<auto-slug>)
  --no-combined                  Не создавать combined.md (default: создавать)

Поведение:
  --fail-fast                    Остановиться на первой ошибке (default: continue-on-error)

Все опции single-команды наследуются:
  --backend, --whisper-model, --gemini-model, --groq-model, --deepgram-model,
  --assemblyai-model, --language, --srt/--no-srt, --timestamps/--no-timestamps,
  --device, --compute-type, --beam-size, --vad,
  --keep-audio, --cookies-from-browser, --no-fast-path, --verbose
```

### Auto-slug для имени папки

- Все входы — один канал/плейлист: slug = имя канала (`@anthropicai`).
- Несколько отдельных URL: slug = `mixed_<N>`.
- Только из `--from-file`: slug = stem имени файла (`urls.txt` → `urls`).

### Примеры

```bash
# Несколько отдельных URL
youtube-transcribe batch https://youtu.be/AAA https://youtu.be/BBB

# Канал, топ-10 свежих, через subtitles (быстро)
youtube-transcribe batch https://youtube.com/@anthropicai --limit 10 --backend subtitles

# Плейлист из файла
youtube-transcribe batch --from-file ~/learn/claude-videos.txt --backend gemini

# Канал на Mac через mlx, без .srt
youtube-transcribe batch https://youtube.com/@channel --limit 5 \
    --backend whisper-local --whisper-model turbo --no-srt
```

### Slash-команда `/transcribe`

Расширяется зеркально — все флаги пробрасываются 1-в-1:

```
/transcribe batch <inputs...> --limit 10 --backend subtitles
```

### SKILL.md — новые триггеры

Skill срабатывает на:
- «прогони пачку видео», «расшифруй все эти ссылки», «вот несколько ссылок»;
- «весь канал», «последние N видео с канала», «все видео с @channel»;
- «возьми этот плейлист», «всё из этого плейлиста»;
- multi-URL message: пользователь прислал 2+ YouTube-ссылки в одном сообщении.

После завершения batch Claude автоматически читает `combined.md` и предлагает: «сделать заметку / сводку / план изучения по теме».

Анти-триггер сохраняется (см. базовая спека §10): не срабатывать на концептуальные вопросы про сам skill.

---

## 5. Resolver — вход → плоский список целей

### Алгоритм `resolve(inputs, from_file, filters)`

```
1. Собрать сырые строки:
     raw = list(inputs)
     if from_file:
         raw += parse_file(from_file)   # 1 URL на строку, # — комментарий, пустые игнор
     if not raw:
         raise CLIError("no inputs given")

2. Для каждой raw-строки определить тип через `downloader.probe_input(url)`:
     # тонкая обёртка над yt-dlp extract_info(url, download=False, extract_flat=True)
     # возвращает кортеж (kind, payload):
     #   kind='video'    → одиночное видео + metadata
     #   kind='playlist' → канал ИЛИ плейлист + entries[]
     #                     (yt-dlp не различает строго; нам не критично — поведение одинаковое)
     #   kind='local'    → локальный путь к файлу

3. Развернуть:
     - 'video'   → один ResolvedTarget(source='single' | 'inline')
     - 'playlist' → entries[:filters.limit], каждый → ResolvedTarget(source='channel' | 'playlist')
     - 'local'   → один ResolvedTarget(source='single', url=str(path))

4. Дедупликация по video_id:
     если URL встречается дважды (inline + file, file + канал) — оставляем первое вхождение,
     warning в stderr.

5. Применить фильтры:
     - limit применяется ПЕРЕД дедупликацией для каждого источника-плейлиста отдельно
       (чтобы --limit 10 на канал не "съело" одно из inline-видео).
     - в v0.1: only limit. Остальные поля ResolverFilters — placeholder.

6. Вернуть list[ResolvedTarget].
```

### Формат `--from-file`

```
# Любой текст после # — комментарий
https://youtu.be/AAA
https://youtu.be/BBB

# Пустые строки игнорируются
https://www.youtube.com/@channel-name        # канал — тоже валидно, развернётся
```

### Поведение при ошибках Resolver

- yt-dlp вернул 403/private/removed на одном из inline URL → этот target помечается как `unresolvable`, попадает в `errors.log` сразу, **до pipeline**. Остальные продолжают.
- Файл `--from-file` не найден / пустой / нет валидных URL → `CLIError`, exit code 2 (input error).
- Канал/плейлист пустой (после применения фильтров — 0 entries) → warning, batch завершается без работы, exit code 0.

### Что Resolver НЕ делает в v0.1

- Не скачивает медиа (это задача `run_pipeline`/downloader).
- Не различает канал vs плейлист (yt-dlp выдаёт оба как `_type='playlist'` — поведение одинаковое).
- Не учитывает дату/duration/shorts при отборе — поля `ResolverFilters` пустые, интерфейс forward-compatible.

### Архитектурное обязательство

`extract_flat=True` — обязательно. Иначе yt-dlp начнёт пробивать каждое видео отдельно, и на канале с 100+ видео это съест минуты до начала транскрибации.

---

## 6. Структура выходов и форматы

### Дерево batch-папки

```
./transcripts/batch_2026-05-09_15-30-12_<slug>/
├── combined.md                    # единый файл для Claude/чтения
├── manifest.json                  # машиночитаемая мета (для скриптов)
├── errors.log                     # только если были ошибки
├── videos/
│   ├── 01_<title-slug>_<video_id>.txt    # с таймкодами (как в single-режиме, §12 базовой спеки)
│   ├── 01_<title-slug>_<video_id>.srt
│   ├── 02_<title-slug>_<video_id>.txt
│   ├── 02_<title-slug>_<video_id>.srt
│   └── ...
└── audio/                         # только если --keep-audio
    ├── 01_<video_id>.mp3
    └── ...
```

**Принципы:**
- Префикс `NN_` обеспечивает порядок (как в Resolver).
- Имя slug-а — то же что в single-режиме (санитизация в базовой спеке §12).
- `videos/` — это N single-режим выходов без изменений формата. Совместимо с любым существующим инструментом.

### `combined.md` — формат

```markdown
---
batch_name: anthropicai-claude-explained
created_at: 2026-05-09T15:30:12+03:00
source: channel
source_url: https://youtube.com/@anthropicai
total: 10
ok: 9
failed: 1
backend: whisper-local
whisper_model: turbo
language: auto
---

# Batch transcript — @anthropicai — 2026-05-09

10 видео, бэкенд: whisper-local (turbo). 9 успешно, 1 с ошибкой (см. errors.log).

---

## 1. What is Claude — explained in 2 minutes

| Поле | Значение |
|---|---|
| URL | https://youtu.be/AAA |
| Video ID | AAA |
| Date | 2026-04-20 |
| Duration | 2:14 |
| Channel | @anthropicai |
| Language detected | en |

Claude is an AI assistant made by Anthropic. The way it works is...
<flat-text транскрипта без таймкодов, разбитый на абзацы по эвристике §12 базовой спеки>

---

## 2. ...
```

**Решения по формату:**

- YAML front-matter в верхушке файла — читаем человеком, парсится скриптами, Claude в чате легко выдёргивает «10 видео, такой-то канал».
- Per-video секции — без YAML, с таблицей метаданных. Компактно, легко скроллить.
- Текст внутри секций — **flat (без таймкодов)**. `combined.md` создан для целей «прочитал → сделал заметку». Кому нужны таймкоды → берёт `videos/NN_*.txt` или `.srt`.
- Разделитель `---` между секциями — визуальный + парсится как Markdown thematic break.
- Если у видео нет `upload_date`/`duration` (yt-dlp иногда не возвращает) — в табличке показываем `—`.

### `manifest.json`

Параллельный машиночитаемый дубль:

```json
{
  "batch_name": "anthropicai-claude-explained",
  "created_at": "2026-05-09T15:30:12+03:00",
  "source": {"type": "channel", "url": "https://youtube.com/@anthropicai"},
  "config": {"backend": "whisper-local", "whisper_model": "turbo", "language": "auto"},
  "stats": {"total": 10, "ok": 9, "failed": 1, "duration_sec": 512},
  "videos": [
    {
      "index": 1,
      "url": "https://youtu.be/AAA",
      "video_id": "AAA",
      "title": "What is Claude...",
      "upload_date": "2026-04-20",
      "duration_sec": 134,
      "channel": "@anthropicai",
      "language_detected": "en",
      "files": {
        "txt": "videos/01_what-is-claude_AAA.txt",
        "srt": "videos/01_what-is-claude_AAA.srt"
      },
      "status": "ok"
    },
    {
      "index": 7,
      "url": "https://youtu.be/CCC",
      "status": "failed",
      "error": "HTTP 403 — yt-dlp blocked, try --cookies-from-browser chrome"
    }
  ]
}
```

Полезно для будущих интеграций (`batch --search` будет писать тот же `manifest.json` — единый формат).

### `errors.log` (только если были ошибки)

```
[2026-05-09T15:31:42] FAILED #7 https://youtu.be/CCC
  Stage: download
  Reason: yt-dlp HTTP 403 — "Sign in to confirm you're not a bot"
  Hint: try --cookies-from-browser chrome

[2026-05-09T15:35:17] FAILED #9 https://youtu.be/DDD
  Stage: backend
  Reason: BackendNotConfigured — GEMINI_API_KEY missing
  Hint: youtube-transcribe config set-key gemini
```

### Summary в stdout (Rich)

После завершения:
```
✓ 9 ok   ✗ 1 failed   Total: 10   Elapsed: 8m 32s

  ./transcripts/batch_2026-05-09_15-30-12_anthropicai/
  ├── combined.md       (~85 KB, ~21k tokens)
  ├── manifest.json
  ├── videos/           (9 transcripts, 9 .srt)
  └── errors.log        (1 failure)

  Next: ask Claude → "прочти combined.md и сделай заметку по теме"
```

Подсказка про Claude — последняя строка — встроена сознательно. Главная цель batch — это вход для Claude-чата, а не финальный артефакт сам по себе.

---

## 7. Defaults и обработка ошибок

| Параметр | Значение | Почему |
|---|---|---|
| Параллелизм | последовательно, 1 video за раз | whisper-local уже жрёт VRAM/CPU; cloud упрётся в rate-limits. `--workers N` — в v0.3 если будет фидбек |
| Поведение при ошибке | `continue-on-error` | На канале из 50 видео отказ от 1 не должен убивать остальные 49 |
| Кэш / re-run | НЕТ кэша в v0.1 | Перезапуск = всё перетранскрибируется. Явное поведение. `--skip-existing` — в v0.3 |
| Порядок видео в канале | свежие сначала | Совпадает с UX «топ-10 свежих» |
| auto-update yt-dlp | наследуется из базовой спеки §11 | раз в день, по флагу `yt_dlp_auto_update` |
| Лимит на канал | 10 | Безопасный default — `100+ видео × whisper-local = вечер` нежелателен молча |
| Temp-папка для аудио | системный temp через `tempfile.TemporaryDirectory()` | авто-чистка при ошибке/Ctrl+C |

### Классификация ошибок batch

- `Stage: resolve` — yt-dlp не смог разобрать URL (private/removed/region-locked). Target не доходит до pipeline.
- `Stage: download` — yt-dlp упал на скачивании аудио (403, 401, network).
- `Stage: backend` — бэкенд вернул ошибку (BackendNotConfigured, API timeout, провайдер упал).
- `Stage: write` — не удалось записать выходной файл (диск, права).

Все классификации фиксируются в `manifest.json` и `errors.log` с `Hint:` — подсказкой пользователю что делать.

---

## 8. Тестирование

### Уровень 1 — unit с моками

- **`test_resolver.py`** — mock `yt-dlp.extract_info(extract_flat=True)`:
  - playlist с 50 entries + `--limit 10` → 10 целей
  - mix `_type='video'` и `'playlist'` → корректный flat-разворот
  - `--from-file`: парсинг комментариев, пустых строк, дубликатов
  - дедупликация inline + file + канал по `video_id`
  - empty playlist → warning, exit 0
- **`test_output_writer_combined.py`**:
  - 10 фейковых `TranscriptionResult` → проверка YAML-frontmatter, таблиц, разделителей
  - `manifest.json` — schema-валидация
  - `errors.log` — формат
- **`test_pipeline_batch.py`**:
  - mock `run_pipeline()` → continue-on-error: 1 fail в середине, остальные 9 продолжают, manifest корректный
  - mock + `--fail-fast` → прерывание на первой ошибке

### Уровень 2 — e2e smoke под `RUN_E2E_SMOKE=1`

- Реальный маленький публичный плейлист (2–3 коротких видео) + `--backend subtitles` → проверка `combined.md`, `manifest.json`, нумерации файлов.

### Уровень 3 — ручной на Mac (Phase 7)

- `batch <channel-url> --limit 3 --backend whisper-local` → проверка mlx-whisper в loop (модель не должна перезагружаться при каждом видео впустую).

---

## 9. Roadmap (отложенные фичи)

| Фича | Версия | Готовая точка внедрения |
|---|---|---|
| Фильтры: `--since`, `--until`, `--min-duration`, `--max-duration`, `--no-shorts` | v0.3 | Поля в `ResolverFilters` уже зарезервированы — добавить только проброс в yt-dlp opts |
| `--workers N` параллелизм | v0.3 | for-loop → `concurrent.futures.ThreadPoolExecutor`, lock на whisper-local |
| `--skip-existing` (кэш по video_id) | v0.3 | Сканирование `<batch>/manifest.json` при старте |
| Поиск по тегам/теме (`batch --search "..."`) | v0.3 | Новый `_type='search'` в Resolver, `ytsearchN:` через yt-dlp или YouTube Data API ключ + ранжирование |
| Instagram (`batch --instagram @user`, период) | v0.4 | yt-dlp уже умеет Instagram, требуются cookies + анти-бот стратегия |
| LLM-сводка `--summarize` | open / v1.x | Отдельный модуль, новый API-ключ; пока сводку делает Claude в чате |

---

## 10. Влияние на существующий план Tasks 1–30

Расширение **встраивается в текущий план** (writing-plans скилл его перепишет).

| Task | Что меняется |
|---|---|
| Task 5 (output_writer.py) | + `write_combined_md(results, batch_meta, output_dir)`, + `write_manifest_json(...)`, + `write_errors_log(...)`. Тесты расширяются. |
| Task 7 (downloader.py) | + `probe_input(url_or_path)` (kind detection) + `expand_channel_or_playlist(url, limit)`. Обе функции через `extract_flat=True`, только метаданные, без скачивания. |
| **Новая Task 7.5 (utils/resolver.py)** | `Resolver`, `ResolvedTarget`, `ResolverFilters`, парсер `--from-file`, дедупликация. ~150 LOC + тесты. |
| Task 20 (CLI entry point) | Изначально 2 sub-команды: `transcribe` (single, default-routing) + `batch`. Общий `run_pipeline()` core. |
| Task 22 (SKILL.md) | + триггеры batch. + правило «после batch предложи `combined.md` для заметки». |
| Task 23 (slash-команда) | проброс `batch` 1-в-1 |
| Task 24 (README) | + секция «Batch / каналы» с примерами + рекомендация `--backend subtitles` для больших каналов |
| Task 26 (smoke-тест) | + e2e batch-сценарий на маленьком плейлисте |
| Tasks 28–29 (Mac validation) | + один ручной batch-прогон через mlx-whisper |

**Итог:** +1 новая Task (7.5 Resolver) + расширения 8 существующих. Один большой пересмотр UX (двойная sub-команда в Task 20).

---

## 11. Открытые вопросы / риски

1. **yt-dlp `extract_flat=True` иногда возвращает entries без `upload_date`/`duration`** — особенно на Shorts и live-стримах. Fallback в `combined.md`/`manifest.json`: показывать `—` / `null`. Не блокирует прогон.
2. **Очень большие каналы (>1000 видео)** — yt-dlp может тянуть метадату долго даже с `extract_flat`. В v0.1 не оптимизируем; документируем `--limit` как обязательный для больших каналов. yt-dlp параметр `--playlist-end N` пробрасывается под капотом.
3. **Дубликаты `video_id` между источниками** (inline + канал, в котором лежит то же видео) — дедупликация безопасна, но видео появляется в `combined.md` один раз. Намеренно. Warning в stderr.
4. **Click default-routing для single-формы без sub-команды** — `youtube-transcribe <URL>` должно роутиться в `transcribe`. Реализуется через `cli.add_command(...)` + кастомный `cli.invoke()` или через Click 8.1+ `default_command`. Если в Click это окажется костыльно — допустимо отказаться и потребовать явное `youtube-transcribe transcribe <URL>` (но тогда базовая спека §8 чуть меняется в UX).
5. **batch-папка с очень длинным slug** — некоторые ФС (Windows, ecryptfs) ограничивают длину имени. Slug ограничивается 60 символами на уровень + усечение `<title>` в имени файла до 60 символов.

---

## 12. Финальный чек-лист (повторение для удобства)

- ✅ Sub-команда `youtube-transcribe batch <inputs...>`.
- ✅ Источники входа: URL inline + URL канала/плейлиста + `--from-file`.
- ✅ Resolver разворачивает любой вход в плоский список без скачивания медиа.
- ✅ `--limit N` (default 10) + архитектурный задел под фильтры v0.3.
- ✅ Изолированная batch-папка: `videos/`, `combined.md`, `manifest.json`, опционально `errors.log` и `audio/`.
- ✅ `combined.md` с YAML front-matter — оптимизирован для чтения Claude в чате.
- ✅ continue-on-error по умолчанию, `--fail-fast` по флагу.
- ✅ Системный temp для аудио (`tempfile.TemporaryDirectory()`), чистка авто.
- ✅ SKILL.md и slash-команда расширяются зеркально.
- ✅ Тесты: unit (моки yt-dlp) + e2e под `RUN_E2E_SMOKE=1` + ручной Mac-прогон.
- ✅ LLM-сводка остаётся вне skill — обязанность Claude-чата.

---

## 13. Что дальше

После одобрения этого документа:

1. Через skill `superpowers:writing-plans` обновляется существующий план [docs/plans/2026-05-08-youtube-transcribe.md](../plans/2026-05-08-youtube-transcribe.md): добавляется Task 7.5 (Resolver), расширяются Tasks 5, 7, 20, 22, 23, 24, 26, 28–29.
2. Реализация продолжается subagent-driven по обновлённому плану.
3. Финальный прогон по чек-листу §12.
