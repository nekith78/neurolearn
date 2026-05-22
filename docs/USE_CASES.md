# Use cases

Concrete patterns where neurolearn earns its place in the toolbox. The
flagship — combining Claude's own research with neurolearn-fetched video
transcripts — is at the top. Everything else is supporting cast.

## 1. Comprehensive research: Claude's web research + neurolearn's video research

**This is the use case neurolearn was built for.**

Claude (in the chat or via API) is great at researching written sources:
documentation, papers, blog posts, GitHub issues, news, web pages it can
browse. But a huge chunk of the most current and most candid information
on any technical or business topic lives in **spoken form** — podcasts,
conference talks, interviews, long-form YouTube discussions, livestreams.
Researchers, founders, engineers say things in interviews they never
write down.

Neither side alone gives you the full picture. Together they do.

### The workflow

1. **Frame the topic** in chat — "I'm researching X, give me a brief plus open questions."
2. **Claude runs its web research** — searches, reads, summarises what's written.
3. **Claude also runs neurolearn** to fetch the spoken-form layer:
   ```bash
   neurolearn research "your topic" \
     --days 90 --languages en,ru --limit 20 \
     --filter "actual deep dives, not surface-level news"
   ```
4. **neurolearn produces a `combined.md`** with 20 transcribed videos + metadata, dropped into the chat as one big text file.
5. **Claude integrates both layers** and writes the synthesis — written + spoken, cross-referenced, with verbatim quotes from both worlds.

The result is research no single source can give: you get the documented
landscape (from web sources) plus the practitioner take, off-the-record
discussions, interview footnotes (from video).

### A concrete example

> "Research the current state of agentic AI safety. Give me a position
> paper-style summary plus a list of contested questions."

Claude internally:

- Searches arXiv, OpenReview, Anthropic / OpenAI / DeepMind blog posts.
- Reads recent industry safety reports.
- Runs `neurolearn research "agentic AI safety" --days 90 --languages en --limit 20 --filter "researcher talks, panels, interviews"`.
- The 20 videos transcribed include podcasts with safety researchers, conference talks, debate panels — material that's nowhere in written form.
- Claude reads `combined.md`, cross-references with the written sources, surfaces points raised in interviews but missing from papers.

Output: a synthesis that catches what *only* gets said out loud (specific
fears, internal disagreements, in-progress thinking) alongside what's been
written down (formal positions, published methods).

### Cross-pollination with your subscribes

If you maintain a `subscribes` list of trusted channels (researchers,
experts, journalists you follow), narrow research to that pool:

```bash
neurolearn research "claude code agent design" \
  --in-subscribes --group ai-research --days 30 \
  --prompt "What new design patterns came up"
```

Now your video search is restricted to people you've already vetted — no
SEO noise, just signal.

---

## 2. Daily / weekly channel digest

You follow 10–30 YouTube / Instagram / TikTok creators but don't have
time to watch everything. neurolearn fetches new uploads, transcribes,
and a chat-side LLM writes a digest:

```bash
neurolearn subscribes update --days 7 --group ai \
  --prompt "What changed this week? Group by theme. Skip filler content." \
  --analyze-backend gemini
```

Schedule it with cron / launchd / Task Scheduler — neurolearn generates the
snippet for you:

```bash
neurolearn subscribes schedule install --every 1d --prompt "Daily AI digest"
```

You read 200 words instead of watching 8 hours.

---

## 3. Turn a long-form video into a structured PDF

Recorded a 2-hour tutorial / workshop / lecture? Get a textbook-style PDF
out of it — title, table of contents, sectioned content with bullet
key-points, inline timestamps, embedded keyframes:

```bash
neurolearn transcribe https://youtu.be/<long-talk> --with-visuals
neurolearn report --latest --report-type tutorial
```

Three built-in layouts (tutorial / vlog / generic) plus custom layouts via
[`~/.neurolearn/report_prompts.toml`](USAGE.md#custom-prompts) — including
cooking-recipe, conference-talk, sales-call, anything you write a prompt
for.

---

## 4. Multi-language research without speaking the language

Search YouTube in multiple languages at once. neurolearn detects your
query's language, translates it to the others you ask for, dedupes
results, and transcribes everything in the original language. The
chat-side LLM does the cross-language synthesis:

```bash
neurolearn research "когнитивные искажения в трейдинге" \
  --languages ru,en,es --limit 30 \
  --prompt "Compare what experts in different languages emphasise"
```

You get the Russian researcher's view, the English finance YouTuber's
take, and the Spanish trading podcast — all in one analysis.

---

## 5. Offline / private transcription

`--backend whisper-local` runs Whisper on your hardware. No audio
leaves the machine. No API key needed. Same `Transcriber` Protocol as
the cloud backends, so the rest of the pipeline (output, batch,
analyze) works identically:

```bash
neurolearn transcribe sensitive-call.mp4 --backend whisper-local --language en
neurolearn batch ./recordings/ --backend whisper-local
```

On Apple Silicon: `mlx-whisper`. On NVIDIA / CPU: `faster-whisper`.
Choice automatic. See [BACKENDS.md](BACKENDS.md#hardware-guide) for
hardware speed estimates.

---

## 6. Build a training / RAG dataset from channels

Need transcripts of a specific creator or community for a fine-tune,
embedding index, or RAG corpus? `batch` reads channels / playlists /
URL lists and writes per-video `.txt` + `.srt` + a unified `combined.md`
+ machine-readable `manifest.json`:

```bash
neurolearn batch https://youtube.com/@anthropicai \
  --since 2024-01-01 --no-shorts --min-duration 300 \
  --backend whisper-local --workers 2 \
  --output-dir ./dataset/anthropic-talks
```

The `manifest.json` carries video IDs, durations, languages, timestamps —
straight feed into your indexing pipeline.

---

## 7. Verify what was actually said (instead of trusting the title)

Headlines lie. A YouTube title can promise "DEFINITIVE PROOF" while the
30-minute video walks it back in the last 5 minutes. Transcribe it,
search for what you actually care about:

```bash
neurolearn transcribe https://youtu.be/<clickbait> --backend subtitles
grep -A2 -B2 -i "but actually" transcripts/<title>.txt
```

Or hand the transcript to Claude with "What's the actual claim here, and
how strongly is it supported?" — and you find out in 30 seconds instead
of 30 minutes.

---

## 8. Quote-mining for writing

Working on an article / blog post / talk and need quote material from
experts? Transcribe a batch of relevant interviews, then ask the chat-side
LLM:

```bash
neurolearn batch --search "Karpathy interview 2026" --limit 10
# in chat: "Pull every quote in this batch where Karpathy talks
# about model scaling specifically. Keep exact wording + timestamps."
```

The timestamps are accurate end-to-end (v0.14.1 chunking preserves them
on multi-hour videos), so you can verify any quote by jumping straight
to the source.
