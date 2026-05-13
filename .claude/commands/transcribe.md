---
description: |
  Transcribe a YouTube URL, local media file, or run BATCH on a channel/playlist/list.
  Usage — /transcribe <URL_or_path> [flags]   (single)
        — /transcribe batch <inputs...> [--limit N] [flags]   (batch — multiple URLs / channel / playlist / --from-file)
argument-hint: <URL_or_path> | batch <inputs...> [flags]
---

Run `youtube-transcribe $ARGUMENTS` and report results back to the user.

- If `$ARGUMENTS` starts with `batch ` (or contains a channel/playlist URL or 2+ URLs), the CLI routes to the batch sub-command. Otherwise — to single (`transcribe`).
- A bare URL/path without sub-command word is auto-routed to `transcribe`.

If `$ARGUMENTS` is empty, prompt the user for a URL, file path, channel URL, or list.

### After single (`./transcripts/<name>.txt|.srt`)
1. Read the generated `.txt`.
2. Give a one-paragraph summary.
3. Offer: full text, search inside, translate, generate subtitles, summarize per timestamp.

### After batch (`./transcripts/batch_<timestamp>_<slug>/`)
1. Read `combined.md` from the printed batch directory.
2. Offer: заметка по теме / сводка / план изучения / cross-video themes.
3. If `errors.log` exists in that directory, briefly summarize which videos failed and why.

If the command exits non-zero, the stdout/stderr will contain a friendly hint — relay it to the user (e.g., "API key missing", "yt-dlp blocked, try `--cookies-from-browser chrome`").
