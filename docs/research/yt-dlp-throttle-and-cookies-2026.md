# yt-dlp throttle + cookie refresh — research (2026)

> Compiled 2026-05-28 for neurolearn. Question: correct self-throttle values
> and YouTube cookie refresh/staleness behaviour.

## Q1 — Self-throttle

### yt-dlp's own `-t sleep` preset is the baseline
`-t sleep` expands to:
```
--sleep-subtitles 5 --sleep-requests 0.75 --sleep-interval 10 --max-sleep-interval 20
```
- `--sleep-requests 0.75` — between metadata/extraction requests.
- `--sleep-interval 10` + `--max-sleep-interval 20` — **random** 10–20s before
  each download (jitter beats a fixed delay; constant cadence is itself a bot
  fingerprint).
- `--sleep-subtitles 5` — lighter delay before subtitle downloads → **yt-dlp
  already scales throttle by request weight** (subs 5s vs audio 10–20s).

### Real limit = request VOLUME, not just spacing (official wiki)
- Guest (no cookies): **~300 videos/hr** (~1000 requests/hr).
- Authenticated (cookies): **~2000 videos/hr** (~4000 requests/hr).
- 10–20s/video keeps you under ~300/hr — that's why it's the sweet spot.

### Fixed vs adaptive → use both
- Jittered fixed delay as floor + reactive backoff on errors.
- yt-dlp built-in backoff: `--retry-sleep [TYPE:]EXPR`, TYPE ∈
  http|fragment|file_access|extractor; EXPR = number | `linear=START:END:STEP`
  | `exp=START:END:BASE`. Retry knobs: `--retries 10`, `--extractor-retries 3`,
  `--fragment-retries 10`, `--file-access-retries 3`.
- **CAVEAT: retries can CAUSE the ban.** Default `--fragment-retries 10`
  hammers YouTube after a failure → bot wall (issue #15899). yt-dlp does NOT
  auto-abort on rate-limit (#14921 wontfix). **Lower fragment retries; cap
  retry-sleep growth; abort yourself on a block.**

### IP type dominates everything
- **Datacenter IPs auto-flagged** by reputation DBs — valid cookies still get
  blocked; throttle barely helps → need residential proxies.
- **Residential/home IPs** are lenient — moderate volume may need little/no
  throttle, cookies often unnecessary. Cookies must be used from the **same IP
  that exported them**.

### Recommended configs
**(a) Home/residential, moderate volume (the preset is enough):**
```
yt-dlp -t sleep --retries 10 --extractor-retries 3 --fragment-retries 3 \
  --retry-sleep linear=1:30:5 --concurrent-fragments 1
```
**(b) Heavier/batch or warm IP:**
```
yt-dlp --sleep-requests 3 --sleep-interval 30 --max-sleep-interval 90 \
  --sleep-subtitles 5 --retries 5 --extractor-retries 2 --fragment-retries 2 \
  --retry-sleep exp=2:120 --limit-rate 3M --concurrent-fragments 1
```
**(c) "Smart" strategy (recommended for the CLI):**
1. Default cheap path: `-t sleep` + low fragment-retries, no cookies, residential IP.
2. Treat a block as STATE: on rate-limit/bot-wall signature, **cool down ~60 min**
   (YouTube says "up to an hour"), don't hammer; next run escalate tier
   (preset → 30–90s → cookies).
3. Exponential backoff only at request layer, hard-capped, FEW retries.
4. Scale by weight: subtitles-only batches can run faster than audio pulls.

## Q2 — Cookies: expiry, staleness, detection

### Validity window (design for 3–5 days)
- Naive (logged-in tab left open): dies in **1–2 hours** (session rotates).
- Incognito, tab closed: **~3–5 days** (issue #13964); some report daily.
- Firefox-SQLite "~2 weeks" claim is **single-source/optimistic** — don't rely on it.

### YouTube rotates/flags; STALE cookies are net-NEGATIVE
- Open logged-in tab → session rotation invalidates the exported file.
- **Expired cookies suppress formats + fail downloads** — worse than anonymous.
  → If cookies are expired, **drop them entirely** rather than send.

### Correct export procedure
1. New **incognito** window, log into YouTube.
2. Same tab → navigate to `youtube.com/robots.txt` (stop session activity).
3. Export youtube.com cookies → Netscape `cookies.txt`.
4. **Close the incognito window** (never reopen → no rotation).
- Use from the **same IP**. Never mix `--cookies` + `--cookies-from-browser`.
- Chrome 127+ app-bound encryption breaks `--cookies-from-browser chrome`;
  use Firefox or fresh-incognito export. OAuth login into yt-dlp no longer works.

### Expiry-detection signatures (map to action)
| Signature | Meaning | Action |
|---|---|---|
| `Sign in to confirm you're not a bot` | expired cookies OR flagged IP OR missing PO token | re-export once; if persists with fresh cookies on clean IP → IP/PO-token |
| player `LOGIN_REQUIRED` (in `-v`) | auth not accepted | re-export cookies |
| `rate-limited by YouTube for up to an hour` | rate limit, NOT cookies | back off ~60 min; do NOT re-export |
| HTTP 403 | auth/bot/geo/rate mix | re-export + check IP |
| `Video unavailable` / empty player response | flagged session | re-export or drop cookies |

Disambiguation rule: re-export fresh once; if the bot-wall reappears with
known-good fresh cookies on a clean IP → cause is IP reputation / missing PO
token, not cookie expiry.

### Cadence, rotation, ban risk
- Re-export every **~3 days**; treat LOGIN_REQUIRED/bot-wall on previously-good
  cookies as an immediate re-export trigger.
- Account-ban risk is real at volume → **throwaway account**, never primary.
  Multiple rotating throwaway cookies spread IP/hourly caps but not ToS risk.
- **Default = NO cookies (anonymous) on residential; attach cookies only on
  escalation** (bot-wall / age-gated / members-only, or for the ~2000/hr
  authenticated budget). Cookies net-negative when stale, wrong-IP, or datacenter.

## Uncertain (2026)
- Cookie validity 3–5 d (GitHub consensus) vs ~2 wk (single source) → design 3–5 d.
- PO tokens increasingly required; yt-dlp can't generate them (external provider).
  If `Sign in to confirm` persists with fresh cookies on clean IP → missing PO token.
- Datacenter-IP blocking near-absolute → cloud deploy needs residential proxies.

## Sources
- yt-dlp Wiki Extractors (300/2000 per-hr caps, `-t sleep`, incognito export)
- yt-dlp README master (`-t sleep` expansion, retry-sleep syntax)
- Issues #11897 (sleep config), #14921 (no auto-abort, rate-limit string),
  #15899 (fragment-retries causes ban), #15392 (bot wall w/ cookies),
  #13964 (3–5 day expiry), #12009 (1–2h naive), #15724 (account-ban risk)
- DEV.to 2026 cookie guide; Decodo 403 guide
