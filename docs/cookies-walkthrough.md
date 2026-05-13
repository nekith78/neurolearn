# Cookies UX walkthrough (manual QA)

Ручной прогон, чтобы почувствовать flow глазами нового пользователя:
от первого `subscribes add` без настроенных cookies → wizard → реальный
update с Instagram'ом / TikTok'ом.

**Этот файл — инструкция для тебя.** Я не могу его прогнать сам, потому
что:
- Нужны твои **реальные** cookies из браузера (Instagram session).
- Wizard ждёт **интерактивного ввода в живом TTY** — я в Claude Code
  обхожусь mock'ами.

## Подготовка (один раз)

### 1. Бэкап твоего текущего состояния

```bash
mkdir -p ~/yt-tr-walkthrough-bak
[[ -f ~/.youtube-transcribe/subscribes.toml ]] && \
  cp ~/.youtube-transcribe/subscribes.toml ~/yt-tr-walkthrough-bak/
[[ -f ~/.youtube-transcribe/config.toml ]] && \
  cp ~/.youtube-transcribe/config.toml ~/yt-tr-walkthrough-bak/
[[ -f ~/.youtube-transcribe/instagram-cookies.txt ]] && \
  cp ~/.youtube-transcribe/instagram-cookies.txt ~/yt-tr-walkthrough-bak/
[[ -f ~/.youtube-transcribe/tiktok-cookies.txt ]] && \
  cp ~/.youtube-transcribe/tiktok-cookies.txt ~/yt-tr-walkthrough-bak/
echo "✓ backup saved to ~/yt-tr-walkthrough-bak/"
```

### 2. Поставь расширение для экспорта cookies

Любой Chromium-браузер (Chrome / Brave / Edge / Vivaldi) — расширение
**«Get cookies.txt LOCALLY»** в Chrome Web Store.
Firefox — расширение **«cookies.txt»** by lennon на addons.mozilla.org.

Открой `instagram.com` (залогиненный) в браузере. Нажми иконку
расширения → выбери **Current site only** → **Export** → сохрани файл
как `~/Downloads/instagram_cookies.txt`.

---

## Сценарий A: первый add Instagram без cookies → wizard offer

### A.1. Симулируем чистого юзера

Очисти только настройки cookies (subscribes-каналы оставь, если есть):

```bash
yt-tr subscribes cookies clear instagram 2>/dev/null || true
yt-tr subscribes cookies clear tiktok    2>/dev/null || true
```

### A.2. Добавь Instagram-канал

```bash
yt-tr subscribes add https://www.instagram.com/natgeo/ --group walk-ig
```

**Что ты должен увидеть:**

```
✓ Добавлен @natgeo (instagram, id=natgeo, group=walk-ig)
Cookies для instagram ещё не настроены. Настроить сейчас? [y/N]:
```

### A.3. Введи `y` → должен запуститься wizard

После `y` появится:

```
Настройка instagram cookies
Шаги:
  1. Поставь расширение 'Get cookies.txt LOCALLY' (open-source) в любом
     браузере (Chrome / Firefox / Edge / Brave).
  2. Открой instagram.com (залогиненный) → расширение → Export.
  3. Введи путь к скачанному файлу ниже.

Путь к cookies.txt:
```

### A.4. Введи путь к экспортированному файлу

```
~/Downloads/instagram_cookies.txt
```

Ожидаемый вывод:

```
✓ instagram cookies сохранены: /Users/nekith78/.youtube-transcribe/instagram-cookies.txt (mode 0600)
Сменить позже: yt-tr subscribes cookies set instagram <new-path>.
```

### A.5. Проверь что cookies прописались

```bash
yt-tr subscribes cookies show
```

Должна быть таблица:
- `instagram` | `/Users/.../instagram-cookies.txt` | `ok`
- `tiktok` | `—` | `not set`

---

## Сценарий B: повторный add — wizard НЕ должен запускаться

```bash
yt-tr subscribes add https://www.instagram.com/nasa/ --group walk-ig
```

**Ожидание:** канал добавлен без всяких вопросов про cookies (уже
настроены). Просто:

```
✓ Добавлен @nasa (instagram, id=nasa, group=walk-ig)
```

---

## Сценарий C: реальный `subscribes update` с твоими cookies

```bash
rm -rf /tmp/yt-walk-ig
yt-tr subscribes update --platform instagram --group walk-ig --days 7 \
  --backend subtitles --no-analyze --yes \
  --output-dir /tmp/yt-walk-ig
```

**Три валидных исхода:**

1. **Лучший:** `✓ N IG reel(s) скачано + транскрибировано` — full success.
2. **Норм:** `Нет новых видео с момента последнего запуска.` — cookies
   приняты, но видео в окне не нашлось.
3. **Плохо:** `Unable to extract data` / `Instagram sent an empty media
   response` — твои cookies не дошли / протухли / yt-dlp upstream
   сломан.

Если (3), попробуй:

```bash
# Очистка → переэкспорт → re-set
yt-tr subscribes cookies clear instagram
yt-tr subscribes cookies set instagram ~/Downloads/instagram_cookies.txt
```

И заново сценарий C.

---

## Сценарий D: `update --platform instagram` без cookies → safety-net offer

Чистим cookies снова чтобы пройти ветку «cookies нет, предложить настроить»:

```bash
yt-tr subscribes cookies clear instagram
yt-tr subscribes update --platform instagram --group walk-ig --days 7 \
  --backend subtitles --no-analyze --yes \
  --output-dir /tmp/yt-walk-ig-d
```

**Ожидание:**

```
Cookies для instagram не настроены — yt-dlp скорее всего вернёт ошибку. Настроить сейчас? [y/N]:
```

Введи `n` (или Enter) → пайплайн пойдёт без cookies, поймает yt-dlp
ошибку, gracefully завершится. Или `y` → откроется wizard, тот же что в
сценарии A.

---

## Сценарий E: TikTok с похожим flow

```bash
yt-tr subscribes cookies clear tiktok 2>/dev/null || true
yt-tr subscribes add https://www.tiktok.com/@duolingo --group walk-tt
```

Ожидание: `Cookies для tiktok ещё не настроены. Настроить сейчас?` —
у TikTok похожий flow. Если хочешь — пройди wizard с
`~/Downloads/tiktok_cookies.txt`. Если не хочешь (TikTok часто работает
анонимно для публичных аккаунтов) — `n`, и обычный `subscribes update`
для @duolingo сработает без cookies.

---

## Что должен заметить

- **Wizard запускается только в TTY** (твой терминал). Через Claude Code
  / pipe / CI он молча пропускается — это правильно.
- **Спрашивает только при первом разе**, потом подхватывает из config.
- **Можно сменить позже** — `yt-tr subscribes cookies set instagram
  <new-path>`.
- **Можно убрать** — `yt-tr subscribes cookies clear instagram`.

---

## Восстановление твоего состояния

После прогона:

```bash
# Удали тестовые каналы
yt-tr subscribes remove "@natgeo" 2>/dev/null || true
yt-tr subscribes remove "@nasa" 2>/dev/null || true
yt-tr subscribes remove "@duolingo" 2>/dev/null || true

# Восстанови из бэкапа (если были свои данные)
[[ -f ~/yt-tr-walkthrough-bak/subscribes.toml ]] && \
  cp ~/yt-tr-walkthrough-bak/subscribes.toml ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/config.toml ]] && \
  cp ~/yt-tr-walkthrough-bak/config.toml ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/instagram-cookies.txt ]] && \
  cp ~/yt-tr-walkthrough-bak/instagram-cookies.txt ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/tiktok-cookies.txt ]] && \
  cp ~/yt-tr-walkthrough-bak/tiktok-cookies.txt ~/.youtube-transcribe/

# Удали тестовые батчи и бэкап-папку
rm -rf /tmp/yt-walk-ig /tmp/yt-walk-ig-d ~/yt-tr-walkthrough-bak
echo "✓ restored"
```
