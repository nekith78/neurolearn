# DRAFT — YouTube Data API v3 integration

Status: **draft / decision log**, 2026-11-12. Not an implementation plan yet.
Purpose: keep the decisions made in the design discussion so they are not
lost. To be reworked into a proper spec + plan before any code.

## Core principle (decided)

- The YouTube Data API becomes the **primary** path for every task it can
  serve. The existing yt-dlp paths stay **unchanged as fallbacks**.
- Fallback fires when: no key configured, quota exhausted, API error /
  timeout, or the API cannot answer (e.g. a field it does not expose).
- The key is **optional**. No key → the tool behaves exactly as today.
  It is not part of the onboarding gate.
- Key storage: `neurolearn config set-key youtube --from-file <path>`
  (new key backend), env name TBD (`YOUTUBE_API_KEY`).
- Transcription is untouched: the API cannot download audio/video or
  third-party captions. yt-dlp / youtube-transcript-api stay.
- A local daily quota counter guards the limits (resets midnight Pacific).

## Verified facts (official docs, read 2026-11-12)

- Free quota per day: 10,000 units (general bucket) + 100 `search.list`
  calls (own bucket since 2026-06-01) + 100 `videos.insert` calls +
  10,000 units for `videos.batchGetStats` (own bucket, since 2026-06-03).
- All read methods cost 1 unit. No billing — quota only.
- `commentThreads.list` / `comments.list`: 100 items per page.
- `videos.list`, `playlistItems.list`: 50 items per page.
- API has no "pinned" / "creator heart" comment flags (yt-dlp has both).
- yt-dlp comment extraction works today without a key (live run:
  50 top comments + replies in ~5 s). Like counts and timestamps from
  yt-dlp are approximate.

## Existing functions — API primary, current path as fallback

| # | Function | Today | With API | Fallback |
|---|---|---|---|---|
| E1 | `subscribes update` (YouTube) | flat tab listing has no dates → one full extract per video (`subscribes/pipeline.py`) | uploads playlist via `playlistItems.list` (dates included) + `videos.list` for duration | current `_fetch_tab` early-exit walk |
| E2 | `batch <channel> --since/--until` | flat entries have no `upload_date`; filter passes them (`utils/resolver.py::_apply_filters`) | dates from API, filter becomes effective | current flat expand |
| E3 | `research` search | yt-dlp search + YouTube `sp` presets 1/7/30/365 days; other windows need full extract | `search.list` with exact `publishedAfter/Before`, `order`, `videoDuration`, `relevanceLanguage` | current SP-preset path, **kept as is** |
| E4 | channel resolution | yt-dlp flat extract with a `channel_id` workaround | `channels.list` by handle / id | current resolver |

Notes:
- E3: the 1/7/30/365 presets are a **deliberate design** (they mirror
  YouTube's own UI filters, server-side). They are not replaced — they
  remain the fallback, and the only path when the 100/day search bucket
  is spent. Budget search calls: one call returns up to 50 results.
- E2: "filter passes undated entries" is inferred from reading the code,
  not from a run. Confirm with a real run before changing behavior.
- E1: early-exit logic and the videos/shorts/streams tab split are
  load-bearing in the current design; the API path must preserve the
  same content selection (regular uploads vs shorts vs streams).

## New functions (decided: do)

| # | Function | Source | Why |
|---|---|---|---|
| N1 | Comments (`--with-comments`, maybe `neurolearn comments <URL>`) | API primary; yt-dlp fallback and for pinned/heart flags | audience reaction is useful context for analysis |
| N2 | Video stats in outputs (views, likes, comment count, tags, description) | `videos.list` | popularity is not used anywhere today; enables min-views filter and ranking in `research` |
| N3 | Channel video listing with stats (date, type, duration, views, likes, comment count) as plain data | uploads playlists + `videos.list` | gives the agent/user the raw material to pick videos by any criteria in chat |

Rejected:
- Built-in "outliers" / "what took off" presets (2026-11-12): no baked-in
  selection logic or thresholds. The tool only exposes the data; selection
  criteria are set ad hoc by the user in chat.
- Import of the user's own YouTube subscriptions (needs OAuth; manual
  `subscribes add` is the intended workflow).

Comment output decisions (from the earlier discussion, defaults TBD):
- **Default cap = 100 top-level comments (decided 2026-11-12).** That is
  exactly one `commentThreads.list` call (1 quota unit). The up-to-5
  inline replies per thread that come in the same response are kept;
  no extra `comments.list` calls by default. More comments / full
  replies only when the user asks for them. The yt-dlp fallback uses
  the same default cap.
- **Default order = YouTube's own order (decided 2026-11-12).** API
  `order=relevance`, kept as returned — no local re-sort by likes.
  Other orders (newest, by likes) only on explicit request.
  Live comparison against the site order (via yt-dlp `comment_sort=top`):
  small video (1.1k comments) — top 20 identical; very large video
  (64k comments) — pinned comment first in both, 13 of top 20 shared,
  order differs. So API relevance approximates, not reproduces, the
  site order on large videos; yt-dlp reproduces it exactly.
- Compact chat-facing file (`likes | author | flags | text`, replies
  indented, long texts truncated). Claude reads it in chat; no LLM API.
- yt-dlp path: separate `skip_download` call, no cookies first, cookies
  only on block.

## Live test results (real key, 2026-11-12)

Channels tested: `@anthropic-ai`, `@NASA`, `@MrBeast`. ~40 quota units
and 3 search calls spent.

- **Key works**; API-key-only access is enough for everything below.
- `channels.list?forHandle=@x` → channel id + uploads playlist + subscriber
  / video counts. Unknown handle returns **empty `items`, not an error**.
- **Per-type upload playlists work via `playlistItems.list`**: replace the
  `UC` prefix of the channel id with `UU` (all), `UULF` (long-form),
  `UUSH` (shorts), `UULV` (live). All newest-first, every item has
  `videoPublishedAt`, 50 per page. A channel with no streams returns
  **404 `playlistNotFound`** for `UULV` (treat as empty).
- Shorts are not identifiable by duration (seen 86 s shorts and 76 s
  regular videos) — `UUSH` membership is the reliable signal.
- `videos.list` with 50 ids in one call → duration, views, likes,
  comment count, `liveStreamingDetails` (present only for streams),
  tags/description/language. `commentCount` is **absent** when comments
  are disabled. Unknown id → silently missing from `items`.
- `commentThreads.list`: 100 threads per call in ~1 s, exact
  `publishedAt` / `updatedAt`, exact `likeCount`, `totalReplyCount`.
  `order=relevance` is **not** sorted by likes — sort locally if needed.
  Only **5 replies inline** per thread; full replies via
  `comments.list?parentId=` (74 of 74 returned in one call).
  Errors: 403 `commentsDisabled`, 404 `videoNotFound`.
- `search.list`: `publishedAfter` gives an exact window (14 days tested,
  all 50 results inside), `order=viewCount`, `videoDuration=long`,
  `relevanceLanguage` all work. Results carry **no duration / stats** —
  one follow-up `videos.list` call (1 unit) is needed.
- `videos:batchGetStats` works (views / likes / comment count only).

Current-code findings confirmed by runs:

- **E2 confirmed.** `resolver.resolve([<channel>/videos], since=2026-09-01)`
  returned all 30 targets — every `upload_date` is `None`, so the date
  filter is a no-op today. (Only 2 long-form uploads are actually in
  that window.)
- **New finding.** A bare channel URL (`youtube.com/@handle`, no `/videos`)
  resolves to **1 target whose `video_id` is the channel id** (yt-dlp
  returns the channel tabs, dedup collapses them). Seen at resolver
  level; not run through the full `batch` CLI.

## Decisions from the grilling round (2026-11-12, all accepted)

- **Q1 Comments entry points:** `--with-comments` flag on `transcribe` /
  `batch` / `analyze` **and** a standalone `neurolearn comments <URL>`
  (to add comments to an already-transcribed video). Off by default.
- **Q2 Pinned / creator-heart flags:** off by default, separate opt-in
  option (extra yt-dlp requests to the site).
- **Q3 API unavailable mid-run** (quota, error, timeout): automatic
  fallback + one notice line per run. No stop, no prompt.
- **Q4 Video stats:** always added when a key is present (no flag).
  No key → no stats; no dedicated fallback for stats.
- **Q5 `research` ordering:** default stays YouTube relevance.
  Popularity is opt-in (min-views filter, sort-by-views option).
- **Q6 Bare channel URL** (`youtube.com/@handle`): fixed in this work;
  means regular long-form uploads only (no shorts, no streams).
  Shorts stay reachable via `/shorts`.
- **Q7 Setup / diagnostics:** `doctor` shows key presence + quota spent
  today; wizard / `/setup` offers the key as an optional, skippable step.
- **Q8 Release order:**
  1. key + quota counter + comments + stats;
  2. subscribes + `batch` date filter + channel resolution + bare-URL fix;
  3. `research` search + channel video listing with stats.

## Open questions

1. Quota counter storage location (technical, decide in the plan).
2. Entry point for the channel listing with stats (decide in the plan).

## Next steps

1. User creates an API key; verify it with a live request.
2. Verify open question 1 and the E2 claim with real runs.
3. Turn this draft into a proper spec + phased plan.
