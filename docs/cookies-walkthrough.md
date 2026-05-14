# Cookies UX walkthrough (manual QA)

A hand-run through the flow as a new user would experience it: from
the first `subscribes add` without cookies set → wizard → real
`update` against Instagram / TikTok.

**This file is an instruction for you (the human).** It can't be
automated end-to-end because:
- It needs **your real** browser cookies (Instagram session).
- The wizard waits on **interactive TTY input** — automated runs use
  mocks instead.

## Preparation (one time)

### 1. Back up your current state

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

### 2. Install a browser extension that exports cookies

Any Chromium-based browser (Chrome / Brave / Edge / Vivaldi): the
**"Get cookies.txt LOCALLY"** extension from the Chrome Web Store.
Firefox: the **"cookies.txt"** extension by lennon on
addons.mozilla.org.

Open `instagram.com` (logged in) in your browser. Click the extension
icon → choose **Current site only** → **Export** → save the file as
`~/Downloads/instagram_cookies.txt`.

---

## Scenario A: first `add` without cookies → wizard offer

### A.1. Simulate a clean user

Clear only the cookies settings (keep any existing subscribed
channels):

```bash
youtube-transcribe subscribes cookies clear instagram 2>/dev/null || true
youtube-transcribe subscribes cookies clear tiktok    2>/dev/null || true
```

### A.2. Add an Instagram channel

```bash
youtube-transcribe subscribes add https://www.instagram.com/natgeo/ --group walk-ig
```

**What you should see:**

```
✓ Added @natgeo (instagram, id=natgeo, group=walk-ig)
Cookies for instagram are not configured yet. Set them up now? [y/N]:
```

### A.3. Type `y` → wizard should launch

After `y` you should see:

```
Instagram cookies setup
Steps:
  1. Install the 'Get cookies.txt LOCALLY' extension (open-source) in
     any browser (Chrome / Firefox / Edge / Brave).
  2. Open instagram.com (logged in) → click the extension → Export.
  3. Enter the path to the downloaded file below.

Path to cookies.txt:
```

### A.4. Enter the path to your exported file

```
~/Downloads/instagram_cookies.txt
```

Expected output:

```
✓ instagram cookies saved: /Users/<you>/.youtube-transcribe/instagram-cookies.txt (mode 0600)
Change later: youtube-transcribe subscribes cookies set instagram <new-path>.
```

### A.5. Verify the cookies are registered

```bash
youtube-transcribe subscribes cookies show
```

The table should show:
- `instagram` | `/Users/.../instagram-cookies.txt` | `ok`
- `tiktok` | `—` | `not set`

---

## Scenario B: repeat `add` — wizard should NOT launch

```bash
youtube-transcribe subscribes add https://www.instagram.com/nasa/ --group walk-ig
```

**Expected:** the channel is added without any cookies prompt (cookies
are already configured). Just:

```
✓ Added @nasa (instagram, id=nasa, group=walk-ig)
```

---

## Scenario C: real `subscribes update` with your cookies

```bash
rm -rf /tmp/yt-walk-ig
youtube-transcribe subscribes update --platform instagram --group walk-ig --days 7 \
  --backend subtitles --no-analyze --yes \
  --output-dir /tmp/yt-walk-ig
```

**Three valid outcomes:**

1. **Best:** `✓ N IG reel(s) downloaded + transcribed` — full success.
2. **OK:** `No new videos since the last run.` — cookies accepted but
   no videos fall into the window.
3. **Bad:** `Unable to extract data` / `Instagram sent an empty media
   response` — your cookies didn't make it through / expired / yt-dlp
   upstream is broken.

For case (3) try:

```bash
# Clear → re-export → re-set
youtube-transcribe subscribes cookies clear instagram
youtube-transcribe subscribes cookies set instagram ~/Downloads/instagram_cookies.txt
```

Then re-run scenario C.

---

## Scenario D: `update --platform instagram` without cookies → safety-net offer

Clear cookies again to walk the "no cookies, offer to configure"
branch:

```bash
youtube-transcribe subscribes cookies clear instagram
youtube-transcribe subscribes update --platform instagram --group walk-ig --days 7 \
  --backend subtitles --no-analyze --yes \
  --output-dir /tmp/yt-walk-ig-d
```

**Expected:**

```
Cookies for instagram are not configured — yt-dlp will most likely fail. Set them up now? [y/N]:
```

Type `n` (or just Enter) → the pipeline runs without cookies, catches
the yt-dlp error, exits gracefully. Or `y` → the same wizard from
scenario A opens.

---

## Scenario E: TikTok with a similar flow

```bash
youtube-transcribe subscribes cookies clear tiktok 2>/dev/null || true
youtube-transcribe subscribes add https://www.tiktok.com/@duolingo --group walk-tt
```

Expected: `Cookies for tiktok are not configured yet. Set them up
now?` — TikTok follows the same flow. If you want to, run the wizard
with `~/Downloads/tiktok_cookies.txt`. If you don't (TikTok often
works anonymously for public accounts) — `n`, and a regular
`subscribes update` for @duolingo will work without cookies.

---

## What to watch for

- **The wizard runs only in a TTY** (your real terminal). Through
  Claude Code / a pipe / CI it's silently skipped — that's correct.
- **The prompt fires only the first time**; subsequent runs read the
  saved choice from config.
- **You can change it later** —
  `youtube-transcribe subscribes cookies set instagram <new-path>`.
- **You can remove it** —
  `youtube-transcribe subscribes cookies clear instagram`.

---

## Restoring your state

After the walkthrough:

```bash
# Drop the test channels
youtube-transcribe subscribes remove "@natgeo" 2>/dev/null || true
youtube-transcribe subscribes remove "@nasa" 2>/dev/null || true
youtube-transcribe subscribes remove "@duolingo" 2>/dev/null || true

# Restore from backup if you had your own data
[[ -f ~/yt-tr-walkthrough-bak/subscribes.toml ]] && \
  cp ~/yt-tr-walkthrough-bak/subscribes.toml ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/config.toml ]] && \
  cp ~/yt-tr-walkthrough-bak/config.toml ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/instagram-cookies.txt ]] && \
  cp ~/yt-tr-walkthrough-bak/instagram-cookies.txt ~/.youtube-transcribe/
[[ -f ~/yt-tr-walkthrough-bak/tiktok-cookies.txt ]] && \
  cp ~/yt-tr-walkthrough-bak/tiktok-cookies.txt ~/.youtube-transcribe/

# Delete the test batches and the backup folder
rm -rf /tmp/yt-walk-ig /tmp/yt-walk-ig-d ~/yt-tr-walkthrough-bak
echo "✓ restored"
```
