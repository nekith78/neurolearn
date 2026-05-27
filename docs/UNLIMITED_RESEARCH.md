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

Layers stack, free-first:

0. **Self-throttle + subtitles-first** (built-in, on by default) — paces yt-dlp requests so you stay under YouTube's per-IP hourly budget (~300 videos/hr anonymous), and prefers free subtitles over downloading audio. This is the layer that protects you out of the box, with zero setup.
1. **Cookies** — a logged-in YouTube/IG/TT session has ~10× higher rate limits than anonymous.
2. **PO Token provider** (`bgutil-ytdlp-pot-provider`, plugin installed by default) — mints the cryptographic anti-bot token YouTube wants. The plugin ships with neurolearn, but a **provider server must be running** to actually generate tokens (see Layer 2).
3. **Residential proxy** (optional, your IP-level escape hatch) — rotates the source IP so YouTube doesn't see all your requests from one address.

You can run with just the defaults, or stack more. The cost / benefit:

| Setup | Cost | Effort | Typical ceiling |
|---|---|---|---|
| Anonymous, no throttle | $0 | 0 | ~5-10 video fetches before blocks |
| **+ Self-throttle (default `light`)** | $0 | 0 (built-in) | stays under the ~300/hr guest budget |
| + Cookies | $0 | 2 min | ~50-200 videos / day, dependent on IP |
| + PO Token provider running | $0 | one `docker run` (Node ≥ 20 for the npx path) | adds 30-50% headroom on top |
| + Residential proxy | ~$1/GB PAYG | 5 min setup | effectively unlimited |

> **Tune throttle:** `throttle` in `config.toml` — `off` / `light` (default) / `polite` / `heavy`. `light` adds a random ~5-12s pause before each *audio* download (and ~3s before subtitle fetches); bump to `polite`/`heavy` if you still get blocked. Deep-dive with exact numbers: [docs/research/yt-dlp-throttle-and-cookies-2026.md](research/yt-dlp-throttle-and-cookies-2026.md) and [docs/research/youtube-ip-block-bypass-2026.md](research/youtube-ip-block-bypass-2026.md).

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
regular dependency. When you `uv sync`, the plugin auto-registers with
yt-dlp via the standard plugin discovery mechanism.

**What it does:** when yt-dlp requests a YouTube video, the plugin
adds a per-session "Proof of Origin Token" — a short cryptographic
signature that YouTube's player generates in real browsers. Without it,
YouTube treats the request as suspicious (scripted) and lowers the
rate-limit ceiling significantly.

> **Important (the common gotcha):** the pip plugin is only the yt-dlp
> *shim*. A token is only actually minted when a **provider server is
> running**. Just having the plugin installed (and even Node present) is
> NOT enough — without a running provider, yt-dlp logs a warning and
> degrades gracefully to no-PO-Token operation (no crash, just fewer
> tokens). This is why `po_token_can_generate` can read `false` even with
> the plugin installed.

**Start the provider** (one-time — pick one):

```bash
# Docker (no local Node needed; recommended, cross-OS):
docker run --name bgutil-provider -d --init --restart unless-stopped \
  -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
```

```bash
# Or, if you have Node >= 20 and prefer no Docker (run in its own terminal):
npx --yes bgutil-ytdlp-pot-provider
```

`--restart unless-stopped` brings the Docker server back after a reboot, so
you only do this once. The setup wizard (`config wizard`) also offers to
start it for you when you pick YouTube.

**Check whether PO Token can actually generate:**

```bash
neurolearn doctor
```

Look for the `Anti-block` section — all three must be ✓:

```
Anti-block (v0.15.0):
  ✓ Node.js: v22.3.0 (>= 20)
  ✓ PO Token plugin: installed
  ✓ PO Token server (:4416): reachable
  ✓ PO Token generation: active (minting YouTube anti-bot tokens)
```

If `PO Token server (:4416)` is `not running`, start the provider above.
If Node is `< 20` and you want the npx path (not Docker), upgrade Node:

- macOS: `brew install node`
- Linux: `nodejs.org` / your distro's Node 20+ package
- Windows: `winget install OpenJS.NodeJS`

## Layer 3 — Residential proxy (paid escape hatch)

For really heavy research (channels with 500+ videos, multiple parallel
projects pulling thousands of videos), cookies + PO Token still hit a
ceiling: YouTube starts flagging your single IP address as "high
volume". The fix is to rotate IPs.

### Recommended providers

| Provider | Pricing | Notes |
|---|---|---|
| [DataImpulse](https://dataimpulse.com/) / [PacketStream](https://packetstream.io/) | ~$1/GB pay-as-you-go | Cheapest viable; credit doesn't expire. Best for individuals. |
| [Evomi](https://evomi.com/) | ~$0.49/GB (plan) | Cheapest per-GB on a subscription. |
| [IPRoyal](https://iproyal.com/residential-proxies/) | $5-7/GB | Solid, session control. |
| [Bright Data](https://brightdata.com/) | $10-15/GB | Enterprise-grade. Overkill for individuals. |

Audio-only m4a is ~1 MB/min, and with subtitles-first most videos cost
~nothing (captions are KB, no audio download) — so only the caption-less
videos consume proxy bandwidth. Realistic spend at ~$1/GB PAYG is a few
dollars/month even for heavy research. **Datacenter proxies are useless
for YouTube** (pre-flagged) — residential/mobile only.

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
4. **If you picked YouTube and Docker is available:** offers to start the PO
   Token provider server right there (the `docker run` above). Optional —
   declining just leaves tokens off; throttle + cookies still apply.

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
  For fewer blocks, also start the PO Token provider (one-time):
    docker run --name bgutil-provider -d --init --restart unless-stopped \
      -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
```

If cookies WERE registered and you still got blocked, the message
points at the next layer up:

```
YouTube blocked the request even with cookies registered.
  Possible causes (in order of likelihood):
    1. Cookies expired — re-export from your browser, re-register.
    2. PO Token provider not running — start it (mints anti-bot tokens):
       docker run --name bgutil-provider -d --init --restart unless-stopped \
         -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
    3. Your IP is in a YouTube-flagged range (datacenter, VPN exit).
       Solution: residential proxy. See docs/research/youtube-ip-block-bypass-2026.md.
```

Exit code 8 is distinct from exit code 4 (generic transcribe error),
so Claude in chat (or any script) can detect it and take the right
follow-up action.

## Summary — what to do, in order

1. Nothing — self-throttle (`light`) + subtitles-first are on by default.
2. Run `neurolearn config wizard`: pick platforms, register cookies, and let
   it start the PO Token provider (YouTube).
3. Verify `neurolearn doctor` shows the anti-block section all-green
   (`PO Token server (:4416): reachable`).
4. Pick "heavy" volume for any platform you do research-style work on.
5. Still hitting blocks? Bump `throttle = polite`/`heavy` in config, then —
   only if needed — add a residential proxy (~$1/GB PAYG).
