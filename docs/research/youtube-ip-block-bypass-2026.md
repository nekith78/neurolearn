# YouTube Download-at-Scale Without IP Blocks — Research Report (2026)

> Research compiled 2026-05-28 for neurolearn. Goal: download YouTube audio
> at scale without IP blocks. Free-first, least-cost paid fallback.

## 1. TL;DR — Recommended layered strategy (free-first)

1. **Prefer subtitles over audio download.** When a video has captions, fetch
   the subtitle track instead of downloading audio — a tiny text request vs a
   multi-MB media pull, so far fewer/lighter anti-bot signals per video.
   neurolearn already has a subtitles backend (PO-token + TLS impersonation) —
   make it the default-first step for every YouTube URL.
2. **Get the bgutil PO Token provider actually running in HTTP-server mode.**
   The pip plugin is installed, but a provider needs a running Node server (or
   script binary) to mint tokens — right now it likely degrades to "no PO
   token". Stand up the local HTTP server
   (`docker run … brainicism/bgutil-ytdlp-pot-provider` on port 4416).
   **Caveat: PO tokens make traffic look legitimate but do NOT by themselves
   remove IP blocks** — necessary, not sufficient.
3. **Throttle yourself.** `--sleep-requests 1`, `--sleep-interval 5
   --max-sleep-interval 15`, `--limit-rate 2M`, low `--concurrent-fragments`.
   Free, and meaningfully delays per-IP rate-limits.
4. **Use cookies cautiously, not by default.** A logged-in `cookies.txt` raises
   limits but in 2025-2026 yt-dlp warns it can get the *account*+IP banned
   faster, and cookies expire in 3-5 days. Throwaway account only; escalate to
   cookies only when anonymous + PO-token is blocked.
5. **If you own a VPS with an IPv6 /64**, rotate the IPv6 source address
   (Invidious `smart-ipv6-rotator`, ~twice/day). Most cost-effective near-100%
   method and **free** if you already have IPv6.
6. **Least-cost paid fallback: pay-as-you-go residential proxies at ~$1/GB**
   (DataImpulse / PacketStream). Audio-only m4a is ~1 MB/min, so 1 GB ≈ hours
   of audio. Datacenter proxies are useless for YouTube — residential/mobile
   only.
7. **Cache/dedup aggressively** — never re-download a video you already have.
   Spread heavy batches over time rather than bursting.
8. **Keep yt-dlp current** (already auto-updated). Stale binary = "Unable to
   extract player response", which looks like a block but isn't.

The "always works, free-first" stack = **subtitles-first → PO-token HTTP server
→ self-throttle → IPv6 rotation (if available)**, with **$1/GB residential
proxy** as the one cheap paid escape hatch.

## 2. Why YouTube blocks you (current 2026 mechanics)

- **Per-IP rate limiting / bot detection.** High frequency from one IP →
  "Sign in to confirm you're not a bot", HTTP 429, `IpBlocked`/`RequestBlocked`.
  Threshold is unpublished/adaptive; anonymous IPs throttle after ~5-10 bursty
  fetches.
- **PO Tokens (Proof of Origin).** Per-request cryptographic token a real
  player computes via Google's BotGuard JS. Two scopes: *Player* token (fetch
  format URLs) and *GVS* token (the media bytes). YouTube now **binds the GVS
  token to the video ID** → fresh token per video → you want an automated
  provider, not manual extraction.
- **TLS / ClientHello fingerprinting.** Independent of cookies/PO token;
  countered by `curl_cffi` impersonation.
- **Datacenter-IP reputation.** Cloud/VPS IPv4 ranges widely pre-blocked — why
  a "fresh VPS IP" often fails while residential IPs don't.

Honest framing: **PO tokens defeat the bot-check/403 layer, but per-IP
rate-limiting is an IP-reputation problem** — only fewer requests, a different
IP, or IP rotation fixes that.

## 3. What neurolearn already has (codebase audit) + gaps

Files inspected: `utils/downloader.py`, `utils/anti_block_cascade.py`,
`backends/subtitles.py`, `subscribes/cookies_onboarding.py`, `transcribe.py`
(doctor), `config.py`, `pyproject.toml`.

**Already implemented (a genuinely strong base):**

- **PO Token plugin declared** — `bgutil-ytdlp-pot-provider>=1.3` in
  `pyproject.toml`; Python shim auto-registers via yt-dlp plugin discovery
  (the `PoTokenProvider BgUtilHTTP`/`BgUtilScriptNode` lines in logs = providers
  *register*; does NOT prove a token was minted).
- **TLS impersonation** — `curl_cffi>=0.10,<0.15`; subtitles backend uses
  `impersonate=` (`backends/subtitles.py:333`).
- **Cookies, file-only** — strict Netscape path, per-platform slots, 0600,
  TOCTOU-safe write.
- **Anti-block cascade** — `anti_block_cascade.py` plans attempts
  (anonymous → cookies), classifies block vs permanent failures.
- **Subtitles-first capability exists** — two-path fetch with block-class
  errors (`IpBlocked`, `PoTokenRequired`) falling through (`subtitles.py:303`).
- **Audio is m4a passthrough** — small files.
- **yt-dlp auto-update** (24h).
- **Doctor exposes anti-block readiness** as JSON.

**Gaps:**

| Gap | Impact |
|---|---|
| No PO-token *server* management (plugin installed, nothing starts the bgutil HTTP server or verifies a token was minted; doctor only checks `find_spec` + `which node`) | Plugin likely degrades to **no token** at runtime → still bot-checked. Biggest "looks wired but isn't" risk. |
| No `--proxy` wiring anywhere | No way to escape a blocked IP without code edits. |
| No self-throttling (`--sleep-requests`/`--sleep-interval`/`--limit-rate`) | Bursty batches trip per-IP limits fast. |
| No `player_client` control | Can't pin to PO-token-free clients (`tv`, `web_embedded`) when defaults break. |
| No IPv6/`--source-address` rotation | Free near-100% method unavailable. |
| No subtitles-before-audio default for plain transcribe | Downloads heavy media even when free captions exist. |
| Stale Node hint — doctor says "Node.js 16+"; bgutil 1.3.1 needs **Node ≥ 20** (`transcribe.py:1843`) | Users on Node 16-18 install plugin, it silently can't run. |

## 4. Techniques — how-to, reliability, cost, ban-risk

### 4.1 Subtitles instead of audio (biggest free win)
- **How:** try subtitle track first; download audio only when captions are
  absent/insufficient (`--write-auto-subs --sub-langs en --skip-download`).
  Make the existing subtitles backend step 0 of the smart cascade.
- **Reliability:** High for the *blocking* problem (text requests far lighter).
  Limited by caption coverage (near-universal for English auto-captions).
- **Cost:** Free; also saves Groq Whisper quota. **Ban risk:** lowest.

### 4.2 PO Tokens via bgutil (necessary, not sufficient)
- **HTTP server (recommended):** `docker run --name bgutil-provider -d --init
  -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider`; yt-dlp + pip plugin
  auto-discover. Override base via `--extractor-args
  "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"`.
- **Script mode:** per-call binary; simpler but spawns Node every call, caches
  poorly — **not for high volume**.
- **Requires Node ≥ 20.** Without a running provider → no token (graceful, but
  still bot-checked).
- **Verify it works:** `yt-dlp -v <url>` should show
  `[pot] PO Token Providers: bgutil:http-1.3.1 (external)` AND a token fetched —
  not just provider registered.
- **Reliability vs IP blocks:** Partial — fixes token layer, NOT per-IP
  rate-limiting. **Cost:** Free. **Ban risk:** none.

### 4.3 Player clients
- **PO-token-FREE (2026 wiki):** `tv`, `android_vr`, `web_embedded`.
- **PO-token-REQUIRED (GVS):** `web`, `web_safari`, `mweb`, `android`, `ios`, …
- **Caveat:** `tv` needs cookies or formats come back DRM'd. yt-dlp default
  already prefers currently-untokened clients.
- **How:** `--extractor-args "youtube:player_client=tv,web_embedded"` as a
  fallback knob. **Reliability:** Medium/volatile (churns per release).

### 4.4 Rate limiting / politeness (free, always helps)
- `--sleep-requests 1`, `--sleep-interval 5 --max-sleep-interval 15`,
  `--limit-rate 2M`, low/no `--concurrent-fragments` (16 from one IP →
  throttled). Raises per-IP ceiling; cheapest insurance.

### 4.5 Cookies / authenticated requests
- `--cookies <file>` raises limits, unlocks age-restricted. **2025-2026:** yt-dlp
  no longer recommends YouTube cookies by default — account+IP ban risk; cookies
  expire 3-5 days. Use **throwaway accounts**, rotate several. **Ban risk: HIGH.**

### 4.6 Proxies
- **Datacenter:** useless (pre-blocked). **Residential/mobile:** what works.
- **Cheapest PAYG (2026):** DataImpulse ~$1.00/GB (no expiry); PacketStream
  $1.00/GB; Evomi ~$0.49/GB (sub). IPRoyal PAYG ~$7.35/GB.
- **Why cheap for us:** audio-only m4a ~1 MB/min → 1 GB ≈ ~16h audio; subtitles
  cut it further. Few $/month even heavy.
- **How:** `--proxy "http://user:pass@gateway:port"` (HTTP/SOCKS5). Use the
  provider's rotating gateway. **Free proxies: don't** (slow, datacenter,
  credential-theft risk).
- **Reliability:** **Highest** (residential rotating ≈ near-100%). **Ban risk:** low.

### 4.7 IP rotation without proxies
- **IPv6 /64 rotation (free if you own IPv6):** Invidious `smart-ipv6-rotator.py`,
  rotate /64 ~2×/day. yt-dlp consumes transparently (`--source-address` /
  `--force-ipv6`). Requires an owned /64 on a supporting VPS (Hetzner, OVH,
  Vultr, DO, Scaleway, BuyVM, Netcup) — not behind home NAT.
- **VPN rotation:** commercial-VPN/datacenter ranges often flagged — less
  reliable than residential proxies or owned IPv6.
- **IPv6 /64 = very high reliability and free** for the right host.

### 4.8 Alternative frontends (mostly dead-end 2026)
- **Invidious:** public instances down to ~3 under Google blocking; self-host
  only (and it fights the same IP layer). **Piped:** ~15 public, under pressure.
  **cobalt.tools:** hits YouTube from its own rate-limited servers.
- **Verdict:** don't build on public instances; self-hosting gains nothing over
  direct yt-dlp + the stack above.

### 4.9 Architectural mitigations (free, high-leverage)
- **Dedup/cache** (existing `state.json` + history) — every avoided download is
  a saved request. **Spread over time** (existing `schedule`). **Subtitles-first**
  (4.1) — the dominant win.

## 5. Recommended combined solution ("always works")

**Free path (do all):**
1. Subtitles-first cascade (audio only on caption miss).
2. Run bgutil PO-token HTTP server + verify token minting (Node ≥ 20 / Docker).
3. Self-throttle every call: `--sleep-requests 1 --sleep-interval 5
   --max-sleep-interval 15 --limit-rate 2M`, single-stream fragments.
4. Dedup + spread batches over time.
5. If VPS with owned IPv6 /64: add `smart-ipv6-rotator` on a 2×/day cron →
   free stack approaches ~100%.
6. Cookies only as escalation, throwaway account.

**Least-cost paid path (no IPv6 / very high volume):**
- Rotating residential proxy PAYG ~$1/GB (DataImpulse/PacketStream):
  `--proxy "http://user:pass@gateway:port"`. With subtitles + audio-only m4a,
  realistic spend is a few $/month.

**Code changes neurolearn needs (priority order):**
1. **Verify + manage the PO-token provider** (not just install): doctor check
   that a token is *minted* (run `yt-dlp -v` / ping `127.0.0.1:4416`);
   document/automate starting the HTTP server; fix **"Node 16+" → "Node ≥ 20"**
   hint (`transcribe.py:1843`).
2. **Expose `--proxy`** end-to-end: `proxy` config field + CLI flag → threaded
   into `build_ytdlp_command` and `_extract_flat` (`opts["proxy"]`), and into
   the anti-block cascade as a final escalation tier (anonymous → cookies →
   proxy).
3. **Add self-throttle flags** to `build_ytdlp_command` (configurable, on by
   default for batch/heavy mode).
4. **Make subtitles step 0** of the smart cascade for YouTube.
5. **Add `player_client` override** config/flag.
6. **(Optional) `--source-address`/IPv6** passthrough.

The cascade in `anti_block_cascade.py` is the right place for proxy + IPv6 as
escalation tiers.

## 6. Comparison table

| Technique | Reliability vs IP block | Cost | Effort | Ban risk |
|---|---|---|---|---|
| Subtitles instead of audio | High | Free | Low | None |
| PO Token (bgutil HTTP server) | Medium (fixes bot-check, not rate-limit) | Free | Med (run server, Node≥20) | None |
| `player_client` override | Medium, volatile | Free | High (churns) | Low |
| Self-throttle | Medium (raises ceiling) | Free (slower) | Low | Reduces |
| Cookies (throwaway) | High when fresh, decays 3-5d | Free | High | **High** |
| Datacenter proxy | Very low (pre-blocked) | Low | Low | Low |
| Residential proxy (rotating PAYG) | **Highest** | ~$1/GB | Low | Low |
| Mobile proxy | Highest | Higher | Low | Low |
| IPv6 /64 rotation (owned) | **Very high** | Free–cheap (VPS) | Med (one-time+cron) | Low |
| VPN rotation | Low–medium | $/mo | Low | Low |
| Public Invidious/Piped/cobalt | Low (blocked) | Free | n/a | n/a |
| Cache/dedup + spread | High (fewer requests) | Free | Low | None |

## 7. Sources

- [yt-dlp PO Token Guide (wiki)](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- [Brainicism/bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) — v1.3.1, Node ≥ 20, HTTP vs script mode
- [bgutil-ytdlp-pot-provider on PyPI](https://pypi.org/project/bgutil-ytdlp-pot-provider/)
- [yt-dlp CLI in 2026 (DEV)](https://dev.to/pickuma/yt-dlp-the-cli-video-downloader-developers-actually-use-in-2026-57jk) — sleep/limit-rate, concurrent-fragments throttling
- [yt-dlp in 2026 (roundproxies)](https://roundproxies.com/blog/yt-dlp/) — residential > datacenter
- [pinchflat wiki: YouTube Cookies](https://github.com/kieraneglin/pinchflat/wiki/YouTube-Cookies) + [yt-dlp #15724](https://github.com/yt-dlp/yt-dlp/issues/15724) — cookie ban risk
- [yt-dlp #13964](https://github.com/yt-dlp/yt-dlp/issues/13964) — cookie expiry 3-5 days
- [Invidious IPv6 rotator](https://docs.invidious.io/ipv6-rotator/)
- [huntapi: proxies for yt-dlp](https://www.huntapi.com/blog/yt-dlp-proxy-guide)
- [DataImpulse residential](https://dataimpulse.com/residential-proxies/) + [AffTank cheapest 2026](https://afftank.com/blog/cheapest-residential-proxies)
- [cybernews: best YouTube proxies 2026](https://cybernews.com/best-proxy/youtube-proxies/)
- [SumGuy: Invidious/Piped 2026 status](https://sumguy.com/invidious-piped-redlib-nitter-2026/)
