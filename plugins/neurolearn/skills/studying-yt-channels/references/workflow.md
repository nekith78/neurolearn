# Create and resume a channel study

## Inventory and selection

1. Resolve the channel's stable ID and canonical URL, rather than trusting a similar display name.
2. Use the metadata tools shipped with NeuroLearn, including its installed yt-dlp where appropriate, without media downloads. Inspect the installed interface instead of assuming a metadata-only `batch` flag exists.
3. Default to the channel's ordinary-video publications. Distinguish Shorts, streams, scheduled/unavailable items, playlist membership, and channel ownership. Keep the complete discovery snapshot and explicit exclusions.
4. Apply the user's filters deterministically. For an exact date window, enrich records lacking exact dates; classify unresolved dates as unresolved rather than guessing from titles or approximate ages. Save the calendar interpretation, timezone, inventory date, and selection rule.
5. Calculate count and known duration from the selected records. State missing duration/date data. For potentially material API work, use the active budget-awareness workflow: inspect call sites and retry/chunk bounds, verify current official pricing before quoting currency, and retain the authorized limit. A request for all selected videos is not permission to silently shrink them.

The selection is a snapshot. Resuming continues that snapshot unless the user requests an update. If scope or spending is already sufficiently authorized, do not ask again merely because this is a new stage.

## Durable workspace

Initialize a fresh dedicated directory with the bundled helper and follow the data contract. Catalogs, policy, full source text, analysis, review findings, topic index, final results, and state are retained. Acquisition attempts use separate directories; temporary media stays under the managed temporary tree.

Save the policy (scope, output language, provider restrictions, authorization, review method, visual policy), the exact source list, and progress before the bulk run. One coordinator updates shared state. A stopped or failed command does not create a ready artifact.

For a legacy study with a different schema, inspect its owning manifests, index, and source records read-only. Do not overwrite it or register existing files for cleanup to make it fit the new helper. A deliberate migration is separate work; historical evidence remains usable through its original references.

## Primary analysis

Read each full received transcript. Long videos may be split into explicit contiguous ranges with enough neighboring context, but a single source owner reconciles the complete video and its boundary conditions afterward.

Each analysis retains:

- A detailed content map accounting for all received cues, including non-substantive passages.
- Substantive claims with stable IDs, speaker or unknown attribution, conditions, cautions, quantities, and supporting source intervals/quotations.
- Topics and cross-references, examples distinguished from general guidance, and publication/context details.
- Transcription uncertainties, missing speech/timing issues, unresolved questions, and proposed visual intervals.

Corrections and alternate transcripts are new versions with provenance. Do not relabel an old backend or silently rewrite a damaged source. Cue accounting measures processed text, not missing speech outside it.

## Topic synthesis and late visuals

After every selected source has primary analysis or an explicit failed/unavailable outcome, derive the thematic index from the actual content. Compare detailed records and return to original passages for differences, exceptions, and combined conclusions. Similar titles or multiple videos by the same speaker are not independent factual corroboration.

Then inspect transcript-led visual candidates, grouped by video. Record the actual inspected timestamps, retained frame/crop paths, observation method, and limitations. If visual acquisition is blocked, preserve a source link and the unresolved status; do not invent the movement or claim visual verification.

## Review, completion, and cleanup

Use the evidence reference for independent review. Fix findings in the owning source artifact, record the change, and recheck dependent conclusions. Final synthesis includes direct evidence links and quotations; a topic summary alone is not its source.

Qualified completion is allowed with explicit unresolved wording and source gaps. Every selected video has an outcome; failed or unreviewed sources remain visible. Close active checks, validate the base, and preserve cited visual evidence before cleaning managed temporary files. Report actual removed bytes and remaining exclusions from cleanup, then validate retained references again.

The user-facing closeout is brief: saved base location, exact requested/completed coverage, main themes, important limitations, cleanup outcome, and proposed learning outline. A later chapter or question opens the retained evidence rather than reconstructing it from this closeout.
