---
name: studying-yt-channels
description: Use when the user wants an in-depth study of a YouTube channel or selected channel videos as a reusable knowledge base, to resume that study, or to ask questions of an existing channel study.
---

# Studying YouTube Channels

Build a source-linked Knowledge Base that another session can consult without relying on this chat's summaries. Use the existing NeuroLearn plugin for acquisition. This skill applies to YouTube channels; a standalone video summary outside a saved study belongs to `neurolearn`.

## Choose the mode first

- **Create:** read [the workflow](references/workflow.md), [the data contract](references/data-contract.md), and [NeuroLearn acquisition](references/acquisition.md).
- **Resume:** read [the workflow](references/workflow.md), [the data contract](references/data-contract.md), and the saved study policy, scope, state, unfinished records, and input versions. Resume affected work; preserve successful source versions. A new upload does not silently expand the saved scope.
- **Query:** read [evidence and retrieval](references/evidence.md). Open the index and relevant source intervals; answer with evidence. This mode is read-only by default and does not restart acquisition, cleanup, or the build pipeline.

For delegated or large studies, read [parallel execution](references/parallelism.md). Assign explicit file ownership; the coordinator retains the index and exceptions rather than every transcript in its context.

## Scope and authorization

Default to **all Ordinary Videos** published by the channel at the inventory snapshot. Exclude Shorts and live streams/recordings unless requested. A topic, date window, selected IDs, or count supplied by the user overrides the default. Clarify genuinely ambiguous scope; never add an arbitrary sampling cap.

Inventory metadata before media acquisition. Record the channel ID, source URLs, publication formats, dates, and exclusions; deduplicate by video ID. Playlists may contain other channels' videos. Missing or approximate dates do not establish an exact date-window match.

For a new bulk run whose volume or spending boundary is not already authorized, show the selected count, known duration, unknowns, and acquisition cost estimate or explicitly unknown cost; obtain one confirmation. Reuse existing authorization, then finish within its bounds without repeated confirmation pauses. Honor the user's active provider and system-load constraints.

## Source-first pipeline

1. **Fix the inventory and scope.** Save the exact selected IDs and selection basis in a separate study directory outside the plugin. Keep the catalog and exclusion reasons.
2. **Acquire with NeuroLearn `smart`.** Follow the acquisition reference. Preserve complete received transcripts, timestamps, versions, actual provenance, and known gaps. A command must finish and its artifacts pass checks before analysis consumes them.
3. **Analyze every received transcript fully.** Save detailed claims, speaker/context, conditions, exceptions, quantities, source quotations and intervals, coverage, uncertainty, and transcript-led visual candidates. Titles and short summaries are navigation aids, not the analysis.
4. **Compare sources by topic.** Derive topics from studied content. Preserve different speakers, dates, contexts, and conflicting positions. Read original context before resolving a difference or combining recommendations.
5. **Inspect visuals late.** By default inspect only candidates suggested by transcript meaning: demonstrations, relevant diagrams, slides, or comparisons. Group candidates by video. Record whether the evidence is sampled frames or a continuously viewed clip; a speech-derived interval is not proof of a demonstration.
6. **Review evidence.** Run deterministic checks on every record. Independently check all material final conclusions, quotations, practically significant recommendations, and flagged ambiguities. Sample other records **and independently selected original passages** to detect omissions. Record the review coverage and expand it when defects appear.
7. **Finalize and clean temporary media.** Close media-dependent work, report complete or qualified completion accurately, validate the retained evidence, then use the scoped cleanup helper. Check retained references again afterward.
8. **Return a concise report.** Link the saved Knowledge Base, state requested/acquired/analyzed/visually inspected coverage and unresolved limitations, report actual cleanup, and propose a learning outline. Write teaching chapters only when requested, after source analysis.

## Evidence in results and future answers

Ground material conclusions in what was actually studied. Include in-text links to specific source times, explicit start–end intervals, and short supporting quotations. Ordinary YouTube timestamp links start playback; they do not stop it at the printed end time.

Distinguish the speaker's claim, the agent's synthesis, observed visual evidence, and independently verified facts. Check quotation wording against its retained transcript version and adjacent context. A transcript-derived quotation is not independently audio-verified. Keep uncertain wording uncertain.

For an exercise or technique, provide the original demonstration link and interval plus important source cautions. A long prose reconstruction does not replace seeing the movement.

The Knowledge Base includes complete received source text and detailed records, not only final summaries. Structural cue coverage does not prove semantic completeness, perfect ASR, or factual correctness of the speaker. External fact-checking is separate work when requested.

## Helpers and completion

Use Python 3.11+ (`python3` on macOS/Linux; verify `python` or `py -3` on Windows). Resolve helper paths relative to this loaded skill, not a hard-coded plugin cache version.

```bash
python3 <skill-directory>/scripts/study.py validate <study-root>
```

Read the data contract before initializing records or registering temporary media. Cleanup defaults to a dry run; apply it automatically only after the agreed completion gate, to the exact registered files of this study. Preserve full transcript versions, analyses, source records, review findings, indexes, and cited frames/crops. Unknown ownership, active work, changed files, shared/pre-existing files, or redirected paths prevent deletion. Never clean a global cache or another study.

The helper validates structure and recorded attestations; reviewers establish source faithfulness. Qualified completion may retain explicit source gaps, but unavailable or unreviewed videos are not counted as successfully analyzed.

## Example

“Study every ordinary video from this YouTube channel published in the last nine calendar months, preserve a reusable source-linked base, and return a short overview.”

Resolve the calendar window against the user's current date, inventory the channel without downloading media, record exact dates/IDs and unknowns, then acquire and analyze the authorized selection. Offer chapters only after that analysis.
