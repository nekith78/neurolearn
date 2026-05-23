# Unlimited research — escaping YouTube / Instagram / TikTok blocks

If you do heavy research across multiple projects, you'll eventually hit
rate-limit / "Sign in to confirm you're not a bot" / 403 errors. This
page covers the layers neurolearn uses to push that ceiling far above
where casual users hit it, plus what to do if you outgrow even the
default setup.

## The cascade in one picture

Every `transcribe` / `batch` / `research` / `subscribes update` call
that touches an online URL goes through this:

```
Attempt 1 ──► If user picked "heavy": always use registered cookies
            ── Else: try anonymous (preserves cookie session lifetime)
            ── In both cases: PO Token plugin auto-attaches if installed

If blocked AND cookies registered AND attempt 1 was anonymous:
  Attempt 2 ──► Retry with cookies

If still blocked OR no cookies registered:
  Stop with platform-specific fix instruction
  (exit code 8 — distinct from generic transcription errors)
```

Three independent layers stack:

1. **Cookies** — a logged-in YouTube/IG/TT session has ~10× higher rate limits than anonymous.
2. **PO Token plugin** (`bgutil-ytdlp-pot-provider`, installed by default) — generates the cryptographic anti-bot token YouTube wants from real browser sessions.
3. **Residential proxy** (optional, your IP-level escape hatch) — rotates the source IP so YouTube doesn't see all your requests from one address.

You can run with just one layer, two, or all three. The cost / benefit:

| Setup | Cost | Effort | Typical ceiling |
|---|---|---|---|
| Anonymous only | $0 | 0 | ~5-10 video fetches before blocks |
| + Cookies | $0 | 2 min | ~50-200 videos / day, dependent on IP |
| + PO Token plugin (default) | $0 | 0 (auto-installs) — needs Node.js 16+ | adds 30-50% headroom on top |
| + Residential proxy | $5-15/month | 5 min setup | effectively unlimited |

## Layer 1 — Cookies (free, 2 minutes)

This is the single biggest reliability improvement. A logged-in YouTube
session gets dramatically more lenient rate limits than anonymous
requests.

### YouTube

1. Open `youtube.com` in your browser (logged in).
2. Install the **"Get cookies.txt LOCALLY"** extension (Chrome / Firefox / Edge / Brave — same Netscape format everywhere).
3. Click the extension → Export. Save to e.g. `~/Downloads/yt-cookies.txt`.
4. Register:
   ```bash
   neurolearn config set-cookies --from-file ~/Downloads/yt-cookies.txt
   ```

### Instagram

Same flow with `instagram.com`:

```bash
neurolearn subscribes cookies set instagram --from-file ~/Downloads/ig-cookies.txt
```

### TikTok

```bash
neurolearn subscribes cookies set tiktok --from-file ~/Downloads/tt-cookies.txt
```

> **Both forms work.** The `--from-file <path>` named option is the same
> as the positional `set-cookies <path>` — but `--from-file` is the form
> to use from Claude Code chat, since it matches the `set-key --from-file`
> security pattern (file path stays out of conversation logs).

### Why not `--cookies-from-browser`?

yt-dlp's `--cookies-from-browser` flag reads **every** cookie for every
domain from your browser store into process memory. neurolearn doesn't
support it; we accept only an explicit Netscape `cookies.txt` file so
you control exactly which session is sent.

## Layer 2 — PO Token plugin (auto-installed)

Since v0.15.0, neurolearn ships with `bgutil-ytdlp-pot-provider` as a
regular dependency. When you `uv sync`, the plugin auto-installs and
auto-registers with yt-dlp via the standard plugin discovery mechanism
(`yt_dlp_plugins/extractor/`). No configuration needed.

**What it does:** when yt-dlp requests a YouTube video, the plugin
intercepts and adds a per-session "Proof of Origin Token" — a short
cryptographic signature that YouTube's player generates in real
browsers. Without it, YouTube treats the request as suspicious
(scripted) and lowers the rate-limit ceiling significantly.

**Runtime requirement:** Node.js 16+ on PATH. The Python plugin shim
calls a small Node helper to generate the token. If Node isn't there,
the plugin logs a warning and yt-dlp degrades gracefully to no-PO-Token
operation.

Check whether PO Token is active:

```bash
neurolearn doctor
```

Look for `Anti-block (v0.15.0)` section:

```
Anti-block (v0.15.0):
  ✓ Node.js: available
  ✓ PO Token plugin: installed
  ✓ PO Token generation: active (heavy YouTube research should not get blocked)
```

If Node.js is missing, install it:

- macOS: `brew install node`
- Linux: `apt install nodejs` (Ubuntu/Debian), or pull from `nodejs.org`
- Windows: `choco install nodejs` or `winget install OpenJS.NodeJS`

## Layer 3 — Residential proxy (paid escape hatch)

For really heavy research (channels with 500+ videos, multiple parallel
projects pulling thousands of videos), cookies + PO Token still hit a
ceiling: YouTube starts flagging your single IP address as "high
volume". The fix is to rotate IPs.

### Recommended providers

| Provider | Pricing | Notes |
|---|---|---|
| [IPRoyal](https://iproyal.com/residential-proxies/) | $5-7/GB (rotating residential) | Solid, no contract. Has session control. |
| [Smartproxy](https://smartproxy.com/) | $7-9/GB | Larger pool, better rotation. |
| [Bright Data](https://brightdata.com/) | $10-15/GB | Enterprise-grade. Overkill for individuals. |

A typical research workflow (20 videos × 50 MB audio) uses ~1 GB. At
$5/GB, that's $5 for ~1000 videos. Realistic for monthly research,
overkill for one-off pulls.

### How to wire it into yt-dlp

yt-dlp accepts a `--proxy <url>` flag. neurolearn doesn't expose this
as a top-level CLI flag yet (it's coming in a future release), but you
can override per-call via env:

```bash
export HTTPS_PROXY=http://user:pass@proxy.iproyal.com:12321
neurolearn research "your topic" --days 30
```

Or set it system-wide if your whole shell session goes through the
proxy.

### Avoid: free / shared / datacenter proxies

YouTube's anti-bot has been trained on every public proxy list out
there. A free SOCKS5 proxy will get you blocked faster than going
direct. Same for personal VPNs (Mullvad, ProtonVPN) when their exit
IPs are well-known to YouTube's flagging.

**Rule of thumb:** the proxy must be a *residential* IP — i.e. an IP
that looks like a real ISP-assigned home connection, not a hosting
provider. Residential proxy services rotate through actual end-user
IPs (often via paid permission with the device owner), which is why
they cost money and why they work.

## How the wizard handles all this

`neurolearn config wizard` (Step 4) asks:

1. **Which platforms?** (multi-select)
2. **For each picked platform:** path to cookies.txt (optional — Enter to skip)
3. **For each picked platform:** light (< 20 videos/week) or heavy (20+)

The volume choice drives the cascade strategy at runtime:

- **Light** — try anonymous first, fall back to cookies if blocked. Preserves cookie session lifetime for casual usage.
- **Heavy** — start with cookies immediately. Anonymous would burn time on guaranteed blocks for high-volume research.

You can re-run the wizard at any time:

```bash
neurolearn config wizard
```

Or update individual settings via `config set` / `config set-cookies`.

## What the cascade looks like when it fails

When blocks exhaust the cascade, neurolearn exits with **code 8** and
prints a platform-specific fix instruction. Sample:

```
✗ Blocked by platform:
YouTube blocked the request (anti-bot / rate limit).
  Two-minute fix:
    1. Open youtube.com in your browser (logged in).
    2. Install 'Get cookies.txt LOCALLY' extension; click → Export.
    3. neurolearn config set-cookies --from-file <path-to-cookies.txt>
  For heavy research, also: make sure Node.js 16+ is installed
  (powers the PO Token plugin, which auto-loads at runtime).
```

If cookies WERE registered and you still got blocked, the message
points at the next layer up:

```
YouTube blocked the request even with cookies registered.
  Possible causes (in order of likelihood):
    1. Cookies expired — re-export from your browser, re-register.
    2. PO Token plugin can't run — install Node.js 16+ on PATH.
    3. Your IP is in a YouTube-flagged range (datacenter, VPN exit).
       Solution: residential proxy. See docs/UNLIMITED_RESEARCH.md.
```

Exit code 8 is distinct from exit code 4 (generic transcribe error),
so Claude in chat (or any script) can detect it and take the right
follow-up action.

## Summary — what to do, in order

1. Run `neurolearn config wizard` and pick your platforms + register cookies.
2. Verify `neurolearn doctor` shows the anti-block section all-green.
3. Pick "heavy" volume for any platform you do research-style work on.
4. If you still hit blocks after all that — get a residential proxy ($5-7/month).
