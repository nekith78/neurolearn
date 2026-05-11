# youtube-transcribe v0.7 — Design: `research` + `subscribes`

**Status:** draft for review
**Date:** 2026-05-12
**Base version:** 0.6.0
**Target version:** 0.7.0

## 1. Цели и принципы

v0.7 добавляет две команды, объединённые общим core:

- **`research "query"`** — широкий поиск по теме: yt-dlp search → date filter → опц. фильтры → транскрибация → опц. анализ. Аналог `batch --search`, но с multi-lang, LLM pre-screening, interactive checkpoint и интеграцией с analyze.
- **`subscribes`** — отслеживание любимых каналов: персистентный список + stateful incremental update. RSS-first для скорости, yt-dlp fallback когда нужны данные которых нет в RSS.

**Принципы:**
1. Доверяем ранжированию YouTube. Своей формулы качества НЕТ — фильтр только по дате и опциональным flag'ам пользователя.
2. Один core pipeline (`_run_batch_pipeline` extracted из v0.6 `batch_cmd`) — две команды поверх.
3. Полная функциональность доступна и Claude в чате (через CLI + чтение TOML), и пользователю в терминале.
4. Опции v0.7 не ломают существующие команды v0.1–v0.6.

## 2. CLI surface

### 2.1 `research`

```
yt-tr research [QUERY] [OPTIONS]
```

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| `QUERY` (positional) | str | — | Поисковый запрос. Опускается если используется `--query-<lang>`. |
| `--query-ru TEXT` / `--query-en TEXT` / `--query-<lang> TEXT` | str | — | Альтернатива: пользователь сам передаёт формулировки на конкретных языках. Если используется хоть один `--query-<lang>` — `QUERY` и `--languages` translation выключаются. |
| `--languages CSV` | str | `ru,en` | Список языков для поиска. Если `QUERY` на одном из них — используется как есть для этого языка; для остальных — LLM переводит. Mutex с `--query-<lang>`. |
| `--translate-backend` | choice | = `--analyze-backend` | LLM для перевода query. Игнорируется если `--query-<lang>` используется. |
| `--days N` | int | 30 | Окно дат (последние N дней). Mutex с `--since/--until`. |
| `--since YYYY-MM-DD --until YYYY-MM-DD` | date | — | Конкретное окно дат. |
| `--limit N` | int | 20 | Сколько видео взять из топа YouTube **на каждый язык**. После dedup может быть меньше. |
| `--match TEXT` | str | — | Substring-фильтр на title (case-insensitive). Оффлайн, быстрый. |
| `--filter TEXT` | str | — | LLM pre-screening на title+channel+(description если уже скачана). Возвращает subset релевантных. Можно использовать после `--match`. |
| `--filter-backend` | choice | gemini | LLM для pre-screening. |
| `--in-subscribes` | flag | False | source = каналы из subscribes.toml вместо global search. Cross-pollination. |
| `--group NAME` | str | — | С `--in-subscribes` — только конкретная группа каналов. |
| `--yes` | flag | False | Пропустить TTY-checkpoint (для cron / Claude в non-TTY автоматически). |
| `--no-analyze` | flag | False | Транскрибировать без финального analyze шага. Если НЕ указан — required `--prompt`/`--prompt-file`. |
| `--prompt TEXT` / `--prompt-file PATH` | str / path | — | Analyze prompt. Required если analyze включён (default). |
| `--analyze-backend` | choice | gemini | LLM для финального analyze. |
| `--ollama-model TEXT` | str | `llama3.2:3b` | Для backend=ollama. Применяется к translation/filter/analyze (общий). |
| `--ollama-host TEXT` | str | `http://localhost:11434` | Для backend=ollama. |
| `--no-stdout` | flag | False | Не печатать ответ analyze в консоль. |
| `--output-dir PATH` | path | из config | Где складывать результат. |
| `--batch-name TEXT` | str | auto | Имя итоговой папки (default: `research_<ts>_<slug>`). |
| **Все существующие batch-флаги** (`--backend`, `--whisper-model`, `--correct-asr`, `--diarize`, `--translate-to`, ...) | | | Пробрасываются в transcription шаг. |

### 2.2 `subscribes` (group)

```
yt-tr subscribes add <channel-url> [--group NAME]
yt-tr subscribes remove <channel-url-or-handle>
yt-tr subscribes list [--group NAME]
yt-tr subscribes edit                     # открыть TOML в $EDITOR
yt-tr subscribes update [OPTIONS]         # запуск flow
yt-tr subscribes schedule install [OPTIONS]    # генерация cron/launchd/systemd snippet
yt-tr subscribes schedule uninstall
```

`subscribes update` опции:
| Флаг | Default | Описание |
|---|---|---|
| `--group NAME` | — | Только каналы этой группы. |
| `--days N` | stateful | Override: тянуть за последние N дней. State **НЕ обновляется**. |
| `--since/--until` | stateful | Override конкретным окном. State **НЕ обновляется**. |
| `--match TEXT` | — | Substring filter (как в research). |
| `--filter TEXT` | — | LLM pre-screening (как в research). |
| `--no-rss` | False | Принудительно использовать yt-dlp вместо RSS. |
| `--yes`, `--no-analyze`, `--prompt`, `--analyze-backend`, etc. | как в research |
| Все batch-флаги | | Пробрасываются. |

`subscribes schedule install` опции:
| Флаг | Default | Описание |
|---|---|---|
| `--every TEXT` | `1h` | Интервал: `15m`, `1h`, `6h`, `1d`. |
| `--platform AUTO\|cron\|launchd\|systemd` | auto | Платформа. Auto детектит ОС. |
| Все опции `subscribes update` | | Сохраняются в scheduled command. |

Не запускает планировщик автоматически — **печатает готовый файл/строку** и инструкции «положи это в `crontab -e` / `~/Library/LaunchAgents/com.user.yt-tr-subscribes.plist` / `~/.config/systemd/user/`».

### 2.3 `history`

```
yt-tr history list [--last N] [--type research|subscribes]
yt-tr history show <run-id>
```

Persistent лог запусков research/subscribes runs (timestamp, query/group, найдено N видео, путь к output folder).

### 2.4 `webui` (расширение)

Существующая команда `yt-tr webui` получает новые Gradio tabs:
- **Research** — форма с query, languages, days/since-until, filters, analyze prompt.
- **Subscribes** — список каналов, кнопки add/remove, форма update.

### 2.5 Exit codes (research + subscribes update)

| Code | Значение |
|---|---|
| 0 | OK |
| 2 | Ошибка аргументов (mutex, missing required prompt и т.п.) |
| 3 | Source не найден (нет результатов поиска / нет subscribes / нет каналов в группе) |
| 4 | LLM error (translation / filter / analyze вернул пусто или нет ключа) |
| 5 | Пользователь отменил TTY-checkpoint |

## 3. Storage layouts

### 3.1 `~/.youtube-transcribe/subscribes.toml`

```toml
# Anthropic & OpenAI researchers
[[channels]]
url = "https://www.youtube.com/@AnthropicAI"
handle = "@AnthropicAI"
channel_id = "UCrDwWp7EBBv4NwvScIpBDOA"   # cached, resolved on `add`
group = "ai-research"
added = "2026-05-12"
last_seen_video_id = "abc123def"
last_seen_published = "2026-05-11T14:00:00Z"

[[channels]]
url = "https://www.youtube.com/@OpenAI"
handle = "@OpenAI"
channel_id = "UCXZCJLdBC09xxGZ6gcdrc6A"
group = "ai-research"
added = "2026-05-12"
# last_seen_* отсутствует — initial run требует --days или --since

# Philosophy
[[channels]]
url = "https://www.youtube.com/@lexfridman"
handle = "@lexfridman"
channel_id = "UCSHZKyawb77ixDdsGog4iWA"
group = "philosophy"
added = "2026-05-12"
```

- Скилл редактирует через `tomlkit` — сохраняет комментарии пользователя.
- Поля `last_seen_video_id` и `last_seen_published` — для stateful incremental update.
- `channel_id` cached на `add` (один yt-dlp вызов), потом используется для RSS feed без повторного scraping.

### 3.2 `~/.youtube-transcribe/history.toml`

```toml
[[runs]]
id = "research_2026-05-12-1430_claude-new-features"
type = "research"
query = "Claude new features"
languages = ["ru", "en"]
days = 30
videos_found = 18
filter = null
output = "~/.youtube-transcribe/transcripts/research_2026-05-12-1430_claude-new-features"
timestamp = "2026-05-12T14:30:00Z"
analyze_backend = "gemini"
analyze_prompt_preview = "Сделай конспект ключевых идей..."
status = "ok"

[[runs]]
id = "subscribes_2026-05-12-1500"
type = "subscribes"
group = null
videos_found = 5
output = "~/.youtube-transcribe/transcripts/subscribes_2026-05-12-1500"
timestamp = "2026-05-12T15:00:00Z"
status = "ok"
```

Лог в TOML (а не SQLite) — простой, читаемый, портативный.

## 4. Pipeline architecture

### 4.1 Общий core

```
source-fetch (search | per-channel)
      │
      ▼
date-filter (--days / --since-until / stateful)
      │
      ▼
opt: substring-match (--match)
      │
      ▼
opt: LLM pre-screen (--filter via filter-backend)
      │
      ▼
TTY checkpoint (questionary picker, skip if --yes or non-TTY)
      │
      ▼
_run_batch_pipeline (extracted from v0.6 batch_cmd)
      │
      ▼
opt: analyze (existing analyze.runner) — skipped if --no-analyze
      │
      ▼
output: <outputs>/research_<ts>_<slug>/ или subscribes_<ts>/
      │
      ▼
history.toml entry (lazy append)
```

### 4.2 research-specific source

1. **Detect language of QUERY** через langdetect.
2. **Build queries per --languages**:
   - Для языка совпадающего с detected — query как есть.
   - Для остальных — LLM translation через analyze.runner с prompt `"Translate this YouTube search query to {lang}, keep technical terms intact: {query}"`. Один LLM call, ~50 токенов.
3. **Альтернатива: `--query-<lang>`** — пользователь даёт готовые формулировки, translation выключается.
4. **Sequential yt-dlp searches** (или параллельно через ThreadPool) — `ytsearch{limit}:{query_per_lang}` для каждого языка.
5. **Dedup по video_id**, объединение в один список.
6. **Cross-pollination (`--in-subscribes`)**: вместо yt-dlp search → fetch latest N от каждого канала subscribes (RSS) → объединить → передать дальше.

### 4.3 subscribes-specific source

1. **Load subscribes.toml**, фильтр по `--group` если указан.
2. **Per-channel discovery (RSS-first):**
   - Build RSS URL: `https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}`
   - HTTP GET (urllib stdlib, ~100ms на канал, параллельно через ThreadPool).
   - Parse XML: extract `entry > yt:videoId`, `entry > title`, `entry > published`.
3. **Date filter:**
   - **Stateful (default)**: оставляем видео с `published > last_seen_published` per-channel.
   - **Override**: фильтр по `--days N` или `--since/--until`.
4. **RSS budget check:** RSS отдаёт ~15 последних видео. Если для какого-то канала самое старое в RSS уже свежее чем cutoff → потенциально RSS не покрывает все видео за период. Делаем yt-dlp fallback **только для этого канала**.
5. **Fallback to yt-dlp** (когда нужны data not in RSS):
   - `--min-duration N` / `--max-duration N` → нужен duration → full extract per video.
   - RSS budget hit (см. выше).
   - `--no-rss` (явно).
6. **State update** (только если default stateful, не override):
   - После успешного запуска update — set `last_seen_video_id` и `last_seen_published` на newest video per channel.

### 4.4 Multi-language search detection

```
langdetect.detect(query) → "ru"
--languages = ["ru", "en"]
─────────────────────────
ru: query as-is → ytsearch20:"Claude новинки"
en: LLM translate → ytsearch20:"Claude new features"
```

Кэш переводов в памяти на одну команду (если запросить `research --languages ru,en,zh` — три LLM call'а, кэшируются если повторное использование).

### 4.5 RSS XML parsing

Используем `xml.etree.ElementTree` (stdlib). YouTube RSS schema стабилен 10+ лет.

```python
import xml.etree.ElementTree as ET
NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

def parse_rss(xml_text: str) -> list[RssEntry]:
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall("atom:entry", NS):
        entries.append(RssEntry(
            video_id=entry.find("yt:videoId", NS).text,
            title=entry.find("atom:title", NS).text,
            published=entry.find("atom:published", NS).text,
            channel_id=entry.find("yt:channelId", NS).text,
            url=f"https://www.youtube.com/watch?v={...}",
        ))
    return entries
```

### 4.6 Refactor: `_run_batch_pipeline` extract

В v0.6 `batch_cmd` — монолитная Click-функция ~400 строк. v0.7 extract:

**Внешний слой остаётся в `batch_cmd`:**
- Click декораторы и парсинг CLI флагов
- Резолв SOURCE (URLs / from-file / channel / playlist / search)
- Загрузка config

**Новый внутренний слой `_run_batch_pipeline(targets, cfg, options) -> Path`:**
- Принимает уже resolved-targets (`list[ResolvedTarget]`) и options dict
- Делает: skip-existing проверку, download → transcribe → write outputs (combined.md, manifest, videos, errors.log)
- Возвращает путь к итоговой папке

Тогда `research_cmd` делает:
```python
targets = research_source.fetch(query, languages, days, ...)
targets = apply_filters(targets, match, filter_spec)
chosen = tty_checkpoint(targets, yes_flag)
batch_dir = _run_batch_pipeline(chosen, cfg, options)
if not no_analyze:
    _run_then_analyze(batch_folder=batch_dir, ...)   # уже существует с v0.6
history.append_run(...)
```

Аналогично `subscribes_update_cmd`.

Этот рефакторинг был отложен в v0.6 plan; теперь делаем его правильно. Все 614 v0.6 тестов должны остаться зелёными (включая `batch --then-analyze`).

## 5. Filter logic

### 5.1 `--match` (substring)

Case-insensitive substring matching на `title`. Простой, оффлайн, быстрый. Не требует LLM.

```python
chosen = [t for t in candidates if match_substr.lower() in t.title.lower()]
```

### 5.2 `--filter` (LLM pre-screening)

Передаём LLM (через `analyze.runner.run_analysis`) prompt:

```
You select videos relevant to: {filter_text}

Candidates:
[1] {title} — {channel} — {date} — {duration}
[2] {title} — ...
...

Return ONLY a JSON array of selected indices, e.g. [1, 3, 5].
```

LLM возвращает массив, мы фильтруем. Если возвращает невалидный JSON — fallback: оставляем всех, log warning.

`--match` и `--filter` можно комбинировать: сначала substring (быстрый отсев), потом LLM на оставшихся (меньше токенов).

## 6. Date logic

### 6.1 `--days N` parsing

Просто целое число дней. `now - timedelta(days=N)` → cutoff.

### 6.2 `--since/--until`

Формат `YYYY-MM-DD`. Парсим через `datetime.date.fromisoformat()`. Mutex с `--days`.

### 6.3 Stateful subscribes

- **Default (no flags)**: per-channel, `published > last_seen_published`.
- **Override (`--days N` или `--since/--until`)**:
  - Игнорирует last_seen.
  - Применяет окно дат глобально к новым кандидатам.
  - **НЕ обновляет** `last_seen_*` в TOML после успеха — чтобы случайный override не сбил incremental stream.
- **First-run (state пуст для канала)**: требует `--days N` или `--since/--until` явно. Иначе exit 2 «не указано initial окно для каналов без state: @X, @Y».

## 7. Cross-pollination (`research --in-subscribes`)

```bash
yt-tr research "Claude features" --in-subscribes --group ai-research --days 14
```

Source = подмножество subscribes (с группой если указана), а не global YouTube search. Затем тот же pipeline: date filter → match/filter → checkpoint → transcribe → analyze.

Полезно для «свежие фишки из моего узкого круга авторов».

## 8. Setup helpers (`subscribes schedule install`)

Не запускаем daemon — генерируем готовый файл/строку для пользователя.

### 8.1 Auto-detect platform

```python
if sys.platform == "darwin":  → launchd
elif sys.platform.startswith("linux"):  → systemd user unit (если есть) или cron
else:  → cron / windows task (cron-fallback)
```

### 8.2 Outputs

**Cron line** (Linux/Mac без launchd):
```
0 */1 * * * /usr/local/bin/youtube-transcribe subscribes update --prompt-file ~/.../prompt.md >> ~/.youtube-transcribe/logs/scheduler.log 2>&1
```

**LaunchAgent plist** (`~/Library/LaunchAgents/com.user.yt-tr-subscribes.plist`):
```xml
<?xml version="1.0"?>
<plist><dict>
  <key>Label</key><string>com.user.yt-tr-subscribes</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/youtube-transcribe</string>
    <string>subscribes</string>
    <string>update</string>
    <string>--prompt-file</string>
    <string>/Users/.../prompt.md</string>
  </array>
  <key>StartInterval</key><integer>3600</integer>
  ...
</dict></plist>
```

**Systemd user unit** (`~/.config/systemd/user/yt-tr-subscribes.timer`):
```
[Unit]
Description=youtube-transcribe subscribes update

[Timer]
OnUnitActiveSec=1h
Unit=yt-tr-subscribes.service

[Install]
WantedBy=timers.target
```

Команда печатает файл + следующие шаги («сохрани в X, активируй командой Y»). Не создаёт файлы без `--write`.

`subscribes schedule uninstall` — печатает инструкцию как убрать (потому что сами не создавали).

## 9. Web UI (Gradio tabs)

Расширение существующего `yt-tr webui`. Два новых таба:

**Research tab:**
- Textarea для query
- Multi-select для languages
- Days slider / since-until date pickers
- Optional textareas для --match и --filter
- Backend dropdown
- Analyze prompt textarea
- Submit → backend job (через analyze.runner pipeline) → results pane

**Subscribes tab:**
- Список каналов (table) с group filter dropdown
- Buttons: add (input URL), remove (per row), update all / per group
- Schedule install snippet preview

Реализация: Gradio Blocks, переиспользует существующий `webui/app.py`.

## 10. Code structure (новые модули)

```
skills/youtube_transcribe/
├── research/                              ← NEW
│   ├── __init__.py
│   ├── source.py                          # yt-dlp search multi-lang
│   ├── translator.py                      # LLM query translation
│   ├── pipeline.py                        # research_cmd orchestration
│   └── (date_filter / match / llm_screen — shared с subscribes)
├── subscribes/                            ← NEW
│   ├── __init__.py
│   ├── store.py                           # tomlkit subscribes.toml
│   ├── state.py                           # last_seen tracking
│   ├── rss.py                             # RSS feed fetch + parse
│   ├── channel_resolver.py                # url → channel_id one-time
│   ├── group.py                           # group filtering
│   ├── cli.py                             # subscribes group sub-commands
│   ├── pipeline.py                        # subscribes update orchestration
│   └── schedule.py                        # cron/launchd/systemd snippet gen
├── shared/                                ← NEW (общий filter logic)
│   ├── __init__.py
│   ├── date_filter.py                     # --days / --since-until parsing
│   ├── match.py                           # substring filter
│   └── llm_screen.py                      # LLM pre-screen
├── history/                               ← NEW
│   ├── __init__.py
│   ├── store.py                           # history.toml read/write
│   └── cli.py                             # yt-tr history list/show
├── transcribe.py                          # +research_cmd, +subscribes group,
│                                          #  +history group, refactor batch_cmd
└── (existing v0.6 modules — unchanged для extension points)
```

`_run_batch_pipeline` живёт в `transcribe.py` рядом с `batch_cmd` (или extracted в `pipeline.py` в корне пакета — final decision на этапе плана).

## 11. Dependencies

Новых **не добавляем**:
- RSS: `xml.etree.ElementTree` (stdlib) + `urllib.request` (stdlib).
- HTTP: stdlib. `requests` НЕ добавляем (хочется минимум deps).
- `langdetect` — уже в v0.2 deps.
- `tomlkit` — уже в v0.2 deps.
- `questionary` — уже в v0.6 deps.

## 12. Integration с v0.6

Переиспользуем:
- `analyze.runner.run_analysis` — для translation, filter, finальный analyze.
- `analyze.prompt_builder` — для финального analyze.
- `analyze.picker.pick_videos` — для TTY-checkpoint (с `--yes` skip).
- `analyze.output_writer` — для `analysis-*.md` в результирующей папке.
- `_run_then_analyze` (если уже extracted) или новая extraction.
- `utils/resolver` — для URL parsing.

## 13. Out of scope (v0.7)

Подтверждено с пользователем:
- **Channel discovery** (предложи похожие каналы) — нужен YouTube Data API или scraping similar-channels page.
- **Composite quality score** (multi-criteria ranking) — пользователь явно отверг: «верим YouTube ranking».
- **Content-based deduplication** (embeddings/LLM на транскриптах) — пока хватает video_id dedup.
- **Saved prompts library** — пользователь не запросил.
- **Notifications** (desktop / Telegram / email) — пользователь не запросил.
- **Token cost estimation** перед analyze — не приоритет.

## 14. Тестирование

### 14.1 Unit (target ~50-70 новых тестов)

| Файл | Покрытие |
|---|---|
| `tests/test_research_source.py` | yt-dlp search per language, mock yt-dlp |
| `tests/test_research_translator.py` | LLM translation (mock analyze.runner), single-lang skip |
| `tests/test_shared_date_filter.py` | --days / --since-until parsing, edge cases |
| `tests/test_shared_match.py` | substring case-insensitive |
| `tests/test_shared_llm_screen.py` | LLM filter (mock), invalid JSON fallback |
| `tests/test_subscribes_store.py` | tomlkit read/write, comments preservation, group filter |
| `tests/test_subscribes_state.py` | last_seen update, override doesn't update |
| `tests/test_subscribes_rss.py` | RSS XML parse, real-format fixture, http mock |
| `tests/test_subscribes_channel_resolver.py` | url → channel_id, cache hit |
| `tests/test_subscribes_pipeline.py` | RSS path, fallback to yt-dlp, hybrid logic |
| `tests/test_subscribes_schedule.py` | cron / launchd / systemd snippet gen |
| `tests/test_history_store.py` | append, list, show, TOML format |
| `tests/test_cli_research.py` | E2E CLI с mocks: happy path, mutex, exit codes |
| `tests/test_cli_subscribes.py` | add/remove/list/edit/update CLI |
| `tests/test_cli_history.py` | history list/show |
| `tests/test_batch_refactor.py` | `_run_batch_pipeline` extraction; existing batch_cmd behavior preserved |

### 14.2 E2E smoke (опционально, `RUN_E2E_SMOKE=1`)

- `research "Claude features" --days 7 --languages en --backend subtitles --no-analyze` — реальный yt-dlp search + транскрибация.
- `subscribes add @AnthropicAI && subscribes update --days 14 --backend subtitles --no-analyze` — реальный RSS + per-channel flow.

### 14.3 Backward compat

- Все 614 v0.6 тестов остаются зелёными.
- `youtube-transcribe batch ...` ведёт себя байт-в-байт как раньше (после рефакторинга через `_run_batch_pipeline`).
- `youtube-transcribe analyze` / `summarize` без изменений.

## 15. Acceptance criteria (ручной shake-down)

- [ ] `yt-tr research --help` показывает все 18+ опций.
- [ ] `yt-tr research "Claude новинки" --days 7 --languages ru,en --no-analyze` — два yt-dlp search'а (ru как есть, en через LLM translation), объединение, transcribe.
- [ ] `yt-tr research "X" --in-subscribes --group ai-research --days 14 --prompt "..."` — source = subscribes, не global search.
- [ ] `yt-tr research "X" --match "Claude" --filter "новинки за неделю" --prompt "..."` — substring filter затем LLM pre-screen.
- [ ] `yt-tr subscribes add https://youtube.com/@AnthropicAI` — добавляет в TOML, кэширует channel_id.
- [ ] `yt-tr subscribes list` — выводит список с группами.
- [ ] `yt-tr subscribes list --group ai-research` — фильтр.
- [ ] `yt-tr subscribes edit` — открывает TOML в $EDITOR.
- [ ] `yt-tr subscribes update --days 7 --prompt "..."` — первый запуск с initial окном.
- [ ] `yt-tr subscribes update --prompt "..."` — incremental после первого запуска.
- [ ] `yt-tr subscribes update --no-rss --days 7 --prompt "..."` — forces yt-dlp вместо RSS.
- [ ] `yt-tr subscribes schedule install --every 1h` — печатает готовый launchd plist / cron line / systemd unit.
- [ ] `yt-tr history list` — показывает последние runs.
- [ ] `yt-tr webui` — открывает Gradio с новыми табами Research + Subscribes.
- [ ] Все 614 v0.6 тестов зелёные после рефакторинга `_run_batch_pipeline`.
- [ ] Все новые ~50-70 тестов зелёные.

## 16. Версия

`pyproject.toml`: `version = "0.7.0-dev"` на старте, `"0.7.0"` в финальном task.
`skills/youtube_transcribe/__init__.py`: `__version__ = "0.7.0"`.
