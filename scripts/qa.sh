#!/usr/bin/env bash
# QA helper for manual testing of v0.7 features.
#
# Usage:
#   scripts/qa.sh                  # show menu
#   scripts/qa.sh phase4           # real batch via subtitles (no API keys)
#   scripts/qa.sh phase5.1         # research single-language (needs GEMINI_API_KEY)
#   scripts/qa.sh phase5.2         # research multi-language with translation
#   scripts/qa.sh phase5.3a        # subscribes add + list
#   scripts/qa.sh phase5.3b        # subscribes update (incremental)
#   scripts/qa.sh phase5.3c        # subscribes --no-rss (yt-dlp path)
#   scripts/qa.sh phase5.4         # history list/show
#   scripts/qa.sh cleanup          # remove all QA artefacts
#
# Run from the repo root: /Users/nekith78/youtube-transcribe.

set -u

# ── colours ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
  BOLD=$'\033[1m';     DIM=$'\033[2m';   NC=$'\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; BOLD=''; DIM=''; NC=''
fi

QA_DIR="/tmp/yt-qa"
mkdir -p "$QA_DIR"

YT="uv run youtube-transcribe"

step() {
  echo
  echo "${BOLD}══ $1 ══${NC}"
}

ok() {
  echo "${GREEN}✓${NC} $1"
}

fail() {
  echo "${RED}✗${NC} $1"
}

note() {
  echo "${DIM}  $1${NC}"
}

require_key() {
  local key_name="$1"
  if ! grep -q "^${key_name}=" ~/.youtube-transcribe/.env 2>/dev/null; then
    echo "${YELLOW}!${NC} ${key_name} не найден в ~/.youtube-transcribe/.env"
    echo "${DIM}  Эта фаза требует ключ. Пропусти или установи через:${NC}"
    echo "${DIM}  $YT config set-key ${key_name,,}${NC}"
    return 1
  fi
  return 0
}

# ── Phase 4: real batch via subtitles ─────────────────────────────────
phase4() {
  step "Phase 4 — batch на реальном YouTube (subtitles, без API ключей)"
  rm -rf "$QA_DIR/batch4"
  if $YT batch "https://www.youtube.com/watch?v=jNQXAC9IVRw" \
       --limit 1 --backend subtitles \
       --output-dir "$QA_DIR/batch4" --batch-name "qa-01"; then
    ok "batch exit 0"
  else
    fail "batch exit $?"
    return 1
  fi

  if [[ -f "$QA_DIR/batch4/qa-01/manifest.json" ]]; then
    ok "manifest.json создан"
  else
    fail "manifest.json отсутствует"
    return 1
  fi

  if [[ -f "$QA_DIR/batch4/qa-01/combined.md" ]]; then
    ok "combined.md создан"
  else
    fail "combined.md отсутствует"
    return 1
  fi

  note "результат: $QA_DIR/batch4/qa-01/"
}

# ── Phase 5.1: research single-language via Gemini ─────────────────────
phase5_1() {
  step "Phase 5.1 — research --languages en (Gemini)"
  require_key "GEMINI_API_KEY" || return 1

  rm -rf "$QA_DIR/r-en"
  # 365d + a broad evergreen topic so YouTube definitely returns something
  # under the cutoff. Narrower windows (30/90d) on niche/popular topics
  # often yield only classic videos that get filtered out.
  $YT research "AI agents" \
    --languages en --days 365 --limit 5 \
    --backend subtitles \
    --prompt "Bullet-point the main concepts mentioned across videos." \
    --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/r-en"
  local code=$?

  if [[ $code -ne 0 ]]; then
    fail "research exit $code"
    return 1
  fi
  ok "research exit 0"

  # Find batch dir (single subdir of r-en)
  local dir
  dir=$(find "$QA_DIR/r-en" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)
  if [[ -z "$dir" ]]; then
    fail "batch folder не найден внутри $QA_DIR/r-en"
    note "Если pipeline сказал 'После фильтра по дате осталось 0' — это"
    note "значит YouTube вернул только старые видео под этот запрос."
    note "Попробуй вручную с другим query или большим --days:"
    note "  $YT research \"твой запрос\" --languages en --days 180 --limit 5 \\"
    note "    --backend subtitles --prompt \"...\" --analyze-backend gemini \\"
    note "    --yes --output-dir $QA_DIR/r-en"
    return 1
  fi
  ok "batch folder: $(basename "$dir")"

  if ls "$dir"/analysis-*.md >/dev/null 2>&1; then
    ok "analysis-*.md создан"
  else
    fail "analysis-*.md отсутствует"
    return 1
  fi

  note "Открой: less $dir/analysis-*.md"
}

# ── Phase 5.1b: SP refinement path (--days not on a preset) ────────────
phase5_1b() {
  step "Phase 5.1b — research --days 14 (SP rounded UP + client refine)"
  require_key "GEMINI_API_KEY" || return 1

  rm -rf "$QA_DIR/r-en-14d"
  # --days 14 → no exact SP preset, nearest UP is "1 month". source.py
  # uses full extract so upload_date is populated, then pipeline filters
  # client-side to the precise 14-day window.
  $YT research "AI agents" \
    --languages en --days 14 --limit 3 \
    --backend subtitles \
    --prompt "Bullet-point what's new in AI agents this week." \
    --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/r-en-14d"
  local code=$?

  if [[ $code -ne 0 ]]; then
    fail "research exit $code"
    return 1
  fi
  ok "research exit 0"

  local dir
  dir=$(find "$QA_DIR/r-en-14d" -maxdepth 1 -mindepth 1 -type d | head -1)
  if [[ -z "$dir" ]]; then
    fail "batch folder не найден"
    return 1
  fi
  ok "batch folder: $(basename "$dir")"

  if ls "$dir"/analysis-*.md >/dev/null 2>&1; then
    ok "analysis-*.md создан"
  else
    fail "analysis-*.md отсутствует"
    return 1
  fi

  # Sanity check: manifest should list videos with upload_date within 14d.
  if [[ -f "$dir/manifest.json" ]]; then
    note "manifest:  $dir/manifest.json"
    note "проверь даты:  grep -i upload_date $dir/manifest.json"
  fi
}

# ── Phase 5.1c: research --since (explicit date instead of --days) ─────
phase5_1c() {
  step "Phase 5.1c — research --since (explicit date → days_hint → SP)"
  require_key "GEMINI_API_KEY" || return 1

  rm -rf "$QA_DIR/r-en-since"
  # 28 days ago — also non-exact preset → SP "1 month" + full extract.
  # Use python rather than `date` for portability (BSD date != GNU date).
  local since
  since=$(python3 -c "import datetime as d; print((d.date.today()-d.timedelta(days=28)).isoformat())")
  note "since=$since"

  $YT research "AI agents" \
    --languages en --since "$since" --limit 3 \
    --backend subtitles \
    --prompt "Bullet-point what's notable in this window." \
    --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/r-en-since"
  local code=$?

  if [[ $code -ne 0 ]]; then
    fail "research exit $code"
    return 1
  fi
  ok "research exit 0"

  local dir
  dir=$(find "$QA_DIR/r-en-since" -maxdepth 1 -mindepth 1 -type d | head -1)
  if [[ -z "$dir" ]]; then
    fail "batch folder не найден"
    return 1
  fi
  ok "batch folder: $(basename "$dir")"

  if ls "$dir"/analysis-*.md >/dev/null 2>&1; then
    ok "analysis-*.md создан"
  else
    fail "analysis-*.md отсутствует"
    return 1
  fi
}

# ── Phase 5.2: research multi-language with LLM translation ────────────
phase5_2() {
  step "Phase 5.2 — research --languages ru,en (translation через Gemini)"
  require_key "GEMINI_API_KEY" || return 1

  rm -rf "$QA_DIR/r-ml"
  $YT research "Клод новинки" \
    --languages ru,en --days 30 --limit 3 \
    --backend subtitles \
    --prompt "Сделай конспект ключевых идей." \
    --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/r-ml"
  local code=$?

  if [[ $code -ne 0 ]]; then
    fail "research exit $code"
    return 1
  fi
  ok "research exit 0"

  local dir
  dir=$(find "$QA_DIR/r-ml" -maxdepth 1 -mindepth 1 -type d | head -1)
  if [[ -z "$dir" ]]; then
    fail "batch folder не найден"
    return 1
  fi
  ok "batch folder: $(basename "$dir")"

  # Check manifest mentions both languages
  if [[ -f "$dir/manifest.json" ]]; then
    ok "manifest.json создан"
    note "проверь source_language в manifest:"
    note "  grep -i language $dir/manifest.json"
  fi
}

# ── Phase 5.3a: subscribes add + list ──────────────────────────────────
phase5_3a() {
  step "Phase 5.3a — subscribes add + list"

  # backup user state
  [[ -f ~/.youtube-transcribe/subscribes.toml ]] && \
    mv ~/.youtube-transcribe/subscribes.toml ~/.youtube-transcribe/subscribes.toml.qa-bak

  $YT subscribes add "https://www.youtube.com/@anthropic-ai" --group ai
  local code=$?

  if [[ $code -ne 0 ]]; then
    fail "subscribes add exit $code"
    [[ -f ~/.youtube-transcribe/subscribes.toml.qa-bak ]] && \
      mv ~/.youtube-transcribe/subscribes.toml.qa-bak ~/.youtube-transcribe/subscribes.toml
    return 1
  fi
  ok "add exit 0"

  $YT subscribes list
  ok "list работает"

  if grep -q "@anthropic-ai" ~/.youtube-transcribe/subscribes.toml 2>/dev/null; then
    ok "@anthropic-ai в subscribes.toml"
  else
    fail "@anthropic-ai не записан"
  fi

  note "subscribes.toml сохранён. Запусти phase5.3b для update."
  note "Бэкап старого файла: ~/.youtube-transcribe/subscribes.toml.qa-bak"
}

# ── Phase 5.3b: subscribes update flow ─────────────────────────────────
phase5_3b() {
  step "Phase 5.3b — subscribes update (first run + incremental)"
  require_key "GEMINI_API_KEY" || return 1

  if ! grep -q "@anthropic-ai" ~/.youtube-transcribe/subscribes.toml 2>/dev/null; then
    fail "subscribes.toml не содержит @anthropic-ai"
    note "Сначала запусти: scripts/qa.sh phase5.3a"
    return 1
  fi

  echo "--- First update (нужен --days, нет state) ---"
  rm -rf "$QA_DIR/subs1"
  $YT subscribes update --days 30 --group ai \
    --backend subtitles \
    --prompt "Что обсуждалось — три тезиса." \
    --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/subs1"
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "first update exit $code"
    return 1
  fi
  ok "first update exit 0"

  echo
  echo "--- Incremental update (без флагов, должен быть быстрым) ---"
  rm -rf "$QA_DIR/subs2"
  $YT subscribes update --group ai \
    --backend subtitles \
    --prompt "..." --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/subs2"
  code=$?
  if [[ $code -ne 0 ]]; then
    fail "incremental exit $code"
    return 1
  fi
  ok "incremental exit 0"
  note "Ожидание: либо новые видео, либо '[yellow]Нет новых видео[/yellow]'"
}

# ── Phase 5.3c: --no-rss yt-dlp fallback ───────────────────────────────
phase5_3c() {
  step "Phase 5.3c — subscribes update --no-rss (yt-dlp путь)"
  require_key "GEMINI_API_KEY" || return 1

  if ! grep -q "@anthropic-ai" ~/.youtube-transcribe/subscribes.toml 2>/dev/null; then
    fail "subscribes.toml пустой (запусти phase5.3a)"
    return 1
  fi

  # Force re-bootstrap: clear the channel's last_seen_* so --no-rss actually
  # has work to do. Without this, phase5.3b leaves state pointing at the
  # newest RSS video, and yt-dlp's channel scrape never finds anything newer.
  python3 - <<'PY'
import re
from pathlib import Path
p = Path.home() / ".youtube-transcribe" / "subscribes.toml"
text = p.read_text(encoding="utf-8")
text = re.sub(r'last_seen_video_id = "[^"]*"', 'last_seen_video_id = ""', text)
text = re.sub(r'last_seen_published = "[^"]*"', 'last_seen_published = ""', text)
p.write_text(text, encoding="utf-8")
PY
  note "reset last_seen_* для re-bootstrap"

  rm -rf "$QA_DIR/subs-nrss"
  $YT subscribes update --no-rss --days 7 --group ai \
    --backend subtitles \
    --prompt "..." --analyze-backend gemini \
    --yes \
    --output-dir "$QA_DIR/subs-nrss"
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "--no-rss exit $code"
    return 1
  fi
  ok "--no-rss exit 0 (yt-dlp path)"
}

# ── Phase 5.3d: Instagram channel — graceful no-cookies fail ───────────
phase5_3d() {
  step "Phase 5.3d — subscribes Instagram (anon fetch must fail gracefully)"

  # Backup existing subscribes.toml so we don't pollute user state.
  [[ -f ~/.youtube-transcribe/subscribes.toml ]] && \
    cp ~/.youtube-transcribe/subscribes.toml \
       ~/.youtube-transcribe/subscribes.toml.phase5_3d-bak

  # Use a real public account (natgeo). yt-dlp anon access to IG is broken
  # right now ("Unable to extract data") — this phase verifies the pipeline
  # treats that as a soft failure: warning printed, no traceback, exit 0,
  # other channels unaffected. Real IG fetch requires cookies (set via
  # `config set instagram.cookies_browser chrome`).
  $YT subscribes add "https://www.instagram.com/natgeo/" --group qa-ig
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "subscribes add (instagram) exit $code"
    [[ -f ~/.youtube-transcribe/subscribes.toml.phase5_3d-bak ]] && \
      mv ~/.youtube-transcribe/subscribes.toml.phase5_3d-bak \
         ~/.youtube-transcribe/subscribes.toml
    return 1
  fi
  ok "subscribes add @natgeo (instagram) exit 0"

  if grep -q 'platform = "instagram"' ~/.youtube-transcribe/subscribes.toml; then
    ok "platform=\"instagram\" записан в subscribes.toml"
  else
    fail "platform не записан"
  fi

  rm -rf "$QA_DIR/subs-ig"
  $YT subscribes update --group qa-ig --days 7 \
    --backend subtitles --no-analyze --yes \
    --output-dir "$QA_DIR/subs-ig"
  code=$?
  if [[ $code -ne 0 ]]; then
    fail "subscribes update (instagram) exit $code"
  else
    ok "subscribes update exit 0 (мягкая обработка анон-сбоя IG)"
    note "ожидание: yt-dlp warning или ChannelNotFoundError, no traceback"
    note "для реального IG fetch:"
    note "  yt-tr config set instagram.cookies_browser chrome"
  fi

  # Cleanup: remove the test channel + restore user's subscribes.toml.
  $YT subscribes remove "@natgeo" >/dev/null 2>&1 || true
  [[ -f ~/.youtube-transcribe/subscribes.toml.phase5_3d-bak ]] && \
    mv ~/.youtube-transcribe/subscribes.toml.phase5_3d-bak \
       ~/.youtube-transcribe/subscribes.toml
}

# ── Phase 5.3e: TikTok channel — real end-to-end smoke ────────────────
phase5_3e() {
  step "Phase 5.3e — subscribes TikTok (@duolingo, real yt-dlp scrape)"
  require_key "GEMINI_API_KEY" || return 1

  [[ -f ~/.youtube-transcribe/subscribes.toml ]] && \
    cp ~/.youtube-transcribe/subscribes.toml \
       ~/.youtube-transcribe/subscribes.toml.phase5_3e-bak

  # @duolingo is the most reliably-public TikTok profile that yt-dlp can
  # scrape anonymously (confirmed during Phase 5 design probe). NASA and
  # khan_academy fail with yt-dlp's "secondary user ID" quirk — don't pick
  # those for QA.
  $YT subscribes add "https://www.tiktok.com/@duolingo" --group qa-tt
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "subscribes add (tiktok) exit $code"
    [[ -f ~/.youtube-transcribe/subscribes.toml.phase5_3e-bak ]] && \
      mv ~/.youtube-transcribe/subscribes.toml.phase5_3e-bak \
         ~/.youtube-transcribe/subscribes.toml
    return 1
  fi
  ok "subscribes add @duolingo (tiktok) exit 0"

  if grep -q 'platform = "tiktok"' ~/.youtube-transcribe/subscribes.toml; then
    ok "platform=\"tiktok\" записан в subscribes.toml"
  else
    fail "platform не записан"
  fi

  rm -rf "$QA_DIR/subs-tt"
  # Use Gemini for actual ASR — TikTok has no subtitles. --max-duration 60
  # to skip multi-minute videos and keep the smoke fast / cheap.
  $YT subscribes update --group qa-tt --days 30 --max-duration 60 \
    --backend gemini --no-analyze --yes \
    --output-dir "$QA_DIR/subs-tt"
  code=$?
  if [[ $code -ne 0 ]]; then
    fail "subscribes update (tiktok) exit $code"
  else
    ok "subscribes update (tiktok) exit 0"
    local dir
    dir=$(find "$QA_DIR/subs-tt" -maxdepth 1 -mindepth 1 -type d | head -1)
    if [[ -n "$dir" ]]; then
      ok "batch folder: $(basename "$dir")"
      local txt_count
      txt_count=$(find "$dir/videos" -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
      note "транскриптов: $txt_count"
    fi
  fi

  $YT subscribes remove "@duolingo" >/dev/null 2>&1 || true
  [[ -f ~/.youtube-transcribe/subscribes.toml.phase5_3e-bak ]] && \
    mv ~/.youtube-transcribe/subscribes.toml.phase5_3e-bak \
       ~/.youtube-transcribe/subscribes.toml
}

# ── Phase 5.4: history ────────────────────────────────────────────────
phase5_4() {
  step "Phase 5.4 — history list/show"
  $YT history list --last 5
  ok "history list работает"

  # Pick newest id straight from history.toml — Rich truncates the table
  # column with an ellipsis ("research_2026…") so we can't parse the CLI
  # output reliably without forcing a wide terminal.
  local run_id
  run_id=$(grep -oE 'id = "[^"]+"' ~/.youtube-transcribe/history.toml 2>/dev/null \
           | tail -1 | sed -E 's/^id = "(.*)"$/\1/')
  if [[ -n "$run_id" ]]; then
    echo
    $YT history show "$run_id"
    ok "history show $run_id"
  else
    note "Нет запусков в истории — сначала запусти phase5.1 / phase5.3b"
  fi
}

# ── Phase 8a: cookies file workflow — self-contained (no real cookies) ──
phase8a() {
  step "Phase 8a — cookies file workflow (validation, set/show/clear, perms)"

  local tmp="$QA_DIR/cookies-self"
  rm -rf "$tmp"; mkdir -p "$tmp"

  # Back up real config + cookies if present — restore at end so the test
  # doesn't trash the user's setup.
  local cfg=~/.youtube-transcribe/config.toml
  local ig_file=~/.youtube-transcribe/instagram-cookies.txt
  local tt_file=~/.youtube-transcribe/tiktok-cookies.txt
  local yt_file=~/.youtube-transcribe/youtube-cookies.txt
  [[ -f $cfg ]]     && cp "$cfg" "$tmp/config.toml.bak"
  [[ -f $ig_file ]] && cp "$ig_file" "$tmp/ig.bak"
  [[ -f $tt_file ]] && cp "$tt_file" "$tmp/tt.bak"
  [[ -f $yt_file ]] && cp "$yt_file" "$tmp/yt.bak"

  # === Fixtures ===
  local good="$tmp/good_cookies.txt"
  local bad="$tmp/not-cookies.txt"
  cat > "$good" <<'CKEOF'
# Netscape HTTP Cookie File
.instagram.com	TRUE	/	TRUE	9999999999	sessionid	fake_session_token_for_qa
.instagram.com	TRUE	/	FALSE	9999999999	csrftoken	fake_csrf
CKEOF
  echo "This is just a plain text file, definitely not cookies." > "$bad"

  # === 1. help shows the new subgroup ===
  if $YT subscribes cookies --help 2>&1 | grep -q "set"; then
    ok "1. subscribes cookies --help shows 'set'"
  else
    fail "1. subscribes cookies --help is missing 'set'"
  fi

  # === 2. rejects missing path (exit non-zero) ===
  if ! $YT subscribes cookies set instagram /tmp/this-does-not-exist.txt \
       >/dev/null 2>&1; then
    ok "2. missing path rejected with non-zero exit"
  else
    fail "2. expected non-zero exit on missing path"
  fi

  # === 3. rejects file that's not Netscape format ===
  local out
  out=$($YT subscribes cookies set instagram "$bad" 2>&1) || true
  if echo "$out" | grep -q "Netscape"; then
    ok "3. non-Netscape file rejected with clear message"
  else
    fail "3. expected Netscape rejection, got: $out"
  fi

  # === 4. happy-path set instagram ===
  if $YT subscribes cookies set instagram "$good" >/dev/null 2>&1; then
    ok "4. subscribes cookies set instagram (valid file) exit 0"
  else
    fail "4. set instagram (valid) failed"
  fi

  # === 5. file copied to canonical location ===
  if [[ -f $ig_file ]]; then
    ok "5. ~/.youtube-transcribe/instagram-cookies.txt created"
  else
    fail "5. canonical IG cookies file missing"
  fi

  # === 6. file has mode 0600 ===
  if [[ $(stat -f '%Lp' "$ig_file" 2>/dev/null) == "600" ]]; then
    ok "6. instagram-cookies.txt has mode 0600"
  else
    fail "6. wrong perms: $(stat -f '%Lp' "$ig_file" 2>/dev/null)"
  fi

  # === 7. config.toml updated ===
  if grep -q "^cookies_file" "$cfg" 2>/dev/null \
     || grep -A2 "^\[instagram\]" "$cfg" 2>/dev/null | grep -q "cookies_file"; then
    ok "7. config.toml has [instagram] cookies_file = ..."
  else
    fail "7. config.toml missing instagram cookies_file"
  fi

  # === 8. cookies show prints the registered file with ok status ===
  out=$($YT subscribes cookies show 2>&1)
  if echo "$out" | grep -q "instagram" && echo "$out" | grep -q "ok"; then
    ok "8. cookies show lists instagram as ok"
  else
    fail "8. cookies show output unexpected: $out"
  fi

  # === 9. set tiktok separately ===
  if $YT subscribes cookies set tiktok "$good" >/dev/null 2>&1 \
     && [[ -f $tt_file ]]; then
    ok "9. cookies set tiktok works too"
  else
    fail "9. tiktok set failed"
  fi

  # === 10. clear removes file + clears config ===
  if $YT subscribes cookies clear instagram >/dev/null 2>&1 \
     && [[ ! -f $ig_file ]]; then
    ok "10. cookies clear instagram removed file"
  else
    fail "10. clear instagram failed"
  fi

  # === 11. youtube-level: config set-cookies works ===
  if $YT config set-cookies "$good" >/dev/null 2>&1 \
     && [[ -f $yt_file ]] \
     && [[ $(stat -f '%Lp' "$yt_file" 2>/dev/null) == "600" ]]; then
    ok "11. config set-cookies (youtube) works + perms 0600"
  else
    fail "11. config set-cookies failed"
  fi

  # === 12. backward-compat: legacy `cookies_browser = "chrome"` loads cleanly ===
  local legacy_cfg="$tmp/legacy_config.toml"
  cat > "$legacy_cfg" <<'TOMLEOF'
default_preset = "smart"
default_backend = "gemini"

[behavior]
cookies_browser = "chrome"
TOMLEOF
  if uv run python -c "
from pathlib import Path
from skills.youtube_transcribe.config import load_config
cfg = load_config(Path('$legacy_cfg'))
assert cfg.cookies_file == '', f'cookies_file should be empty, got: {cfg.cookies_file!r}'
print('legacy-load-ok')
" 2>&1 | tail -1 | grep -q "legacy-load-ok"; then
    ok "12. pre-v0.8 [behavior] cookies_browser loads cleanly (ignored)"
  else
    fail "12. legacy config load failed"
  fi

  # === 13. clear tiktok too ===
  $YT subscribes cookies clear tiktok >/dev/null 2>&1 || true

  # === Restore user state ===
  [[ -f $tmp/config.toml.bak ]] && cp "$tmp/config.toml.bak" "$cfg"
  [[ -f $tmp/ig.bak ]] && cp "$tmp/ig.bak" "$ig_file"
  [[ -f $tmp/tt.bak ]] && cp "$tmp/tt.bak" "$tt_file"
  [[ -f $tmp/yt.bak ]] && cp "$tmp/yt.bak" "$yt_file"
  # Files that didn't exist before — make sure we cleaned up
  [[ ! -f $tmp/ig.bak ]] && rm -f "$ig_file"
  [[ ! -f $tmp/tt.bak ]] && rm -f "$tt_file"
  [[ ! -f $tmp/yt.bak ]] && rm -f "$yt_file"
  note "user state restored"
}

# ── Phase 8b: live cookies workflow — requires user-provided cookies ──
# This phase needs the user to have run `subscribes cookies set instagram <path>`
# (and optionally tiktok) BEFORE invoking. It then runs a real `subscribes
# update` for Instagram to verify the file-based auth works end-to-end.
phase8b() {
  step "Phase 8b — LIVE cookies workflow (требует твоих cookies)"

  # Verify the user has registered IG cookies first
  if ! $YT subscribes cookies show 2>&1 | grep -E "^\| instagram" \
       | grep -q "ok"; then
    fail "Сначала зарегистрируй IG cookies:"
    note "  1. Поставь расширение 'Get cookies.txt LOCALLY' в браузере"
    note "  2. Открой instagram.com (залогиненный) → Export → ~/Downloads/ig.txt"
    note "  3. yt-tr subscribes cookies set instagram ~/Downloads/ig.txt"
    note "Потом запусти phase8b повторно."
    return 1
  fi
  ok "instagram cookies зарегистрированы"

  # Back up subscribes.toml
  [[ -f ~/.youtube-transcribe/subscribes.toml ]] && \
    cp ~/.youtube-transcribe/subscribes.toml \
       ~/.youtube-transcribe/subscribes.toml.phase8b-bak

  # Add a public IG channel
  $YT subscribes add "https://www.instagram.com/natgeo/" --group qa-ig8b
  local code=$?
  if [[ $code -ne 0 ]]; then
    fail "subscribes add (instagram) exit $code"
    [[ -f ~/.youtube-transcribe/subscribes.toml.phase8b-bak ]] && \
      mv ~/.youtube-transcribe/subscribes.toml.phase8b-bak \
         ~/.youtube-transcribe/subscribes.toml
    return 1
  fi
  ok "subscribes add @natgeo (instagram) — ok"

  # Run update — with cookies, this should NOT fail with "Unable to
  # extract data" (which is the anonymous-IG failure mode).
  rm -rf "$QA_DIR/subs-ig-live"
  local out
  out=$($YT subscribes update --group qa-ig8b --days 30 \
         --backend subtitles --no-analyze --yes \
         --output-dir "$QA_DIR/subs-ig-live" 2>&1)
  echo "$out" | tail -8

  if echo "$out" | grep -q "Unable to extract data"; then
    fail "live update получил 'Unable to extract data' даже с cookies"
    note "Возможные причины:"
    note "  • cookies протухли (re-export и set заново)"
    note "  • IG поломал yt-dlp upstream (проверь yt-dlp -U)"
  elif echo "$out" | grep -q "Нет новых видео\|новых видео нет"; then
    ok "live update — cookies дошли до yt-dlp, видео не нашлось (это OK)"
  elif find "$QA_DIR/subs-ig-live" -name '*.txt' 2>/dev/null | grep -q .; then
    local n
    n=$(find "$QA_DIR/subs-ig-live" -name '*.txt' | wc -l | tr -d ' ')
    ok "live update — $n IG reel(s) скачано + транскрибировано"
  else
    fail "live update — неожиданный результат"
  fi

  # Cleanup
  $YT subscribes remove "@natgeo" >/dev/null 2>&1 || true
  [[ -f ~/.youtube-transcribe/subscribes.toml.phase8b-bak ]] && \
    mv ~/.youtube-transcribe/subscribes.toml.phase8b-bak \
       ~/.youtube-transcribe/subscribes.toml
}

# ── cleanup ───────────────────────────────────────────────────────────
cleanup() {
  step "Cleanup — удаляю $QA_DIR и восстанавливаю subscribes.toml"
  rm -rf "$QA_DIR"
  [[ -f ~/.youtube-transcribe/subscribes.toml.qa-bak ]] && \
    mv ~/.youtube-transcribe/subscribes.toml.qa-bak ~/.youtube-transcribe/subscribes.toml
  ok "done"
}

# ── menu ──────────────────────────────────────────────────────────────
menu() {
  cat <<'EOF'
Usage: scripts/qa.sh <phase>

  phase4         — реальный batch на YouTube (subtitles, без API ключей)
  phase5.1       — research --languages en --days 365 (SP exact preset, fast path)
  phase5.1b      — research --days 14 (SP rounded UP + client refine)
  phase5.1c      — research --since (explicit date → days_hint → SP)
  phase5.2       — research --languages ru,en + LLM translation
  phase5.3a      — subscribes add + list (нужна сеть для resolve)
  phase5.3b      — subscribes update first run + incremental
  phase5.3c      — subscribes update --no-rss (yt-dlp путь)
  phase5.3d      — subscribes Instagram (graceful no-cookies fail; v0.8)
  phase5.3e      — subscribes TikTok @duolingo (real yt-dlp scrape; v0.8)
  phase5.4       — history list/show
  phase8a        — cookies file workflow (self-contained, no real cookies)
  phase8b        — LIVE Instagram через cookies-файл (требует твоих cookies)
  cleanup        — удалить все QA-артефакты + восстановить subscribes.toml

Каждая фаза самостоятельна и сообщает PASS/FAIL.
Run from repo root: cd /Users/nekith78/youtube-transcribe && scripts/qa.sh <phase>
EOF
}

# ── entry ─────────────────────────────────────────────────────────────
case "${1:-}" in
  phase4)    phase4 ;;
  phase5.1)  phase5_1 ;;
  phase5.1b) phase5_1b ;;
  phase5.1c) phase5_1c ;;
  phase5.2)  phase5_2 ;;
  phase5.3a) phase5_3a ;;
  phase5.3b) phase5_3b ;;
  phase5.3c) phase5_3c ;;
  phase5.3d) phase5_3d ;;
  phase5.3e) phase5_3e ;;
  phase5.4)  phase5_4 ;;
  phase8a)   phase8a ;;
  phase8b)   phase8b ;;
  cleanup)   cleanup ;;
  *)         menu ;;
esac
