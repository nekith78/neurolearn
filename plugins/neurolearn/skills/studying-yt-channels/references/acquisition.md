# NeuroLearn acquisition and visual extraction

## Existing plugin entry point

Read the sibling `../neurolearn/SKILL.md` relative to this skill's directory. Follow its launcher discovery, doctor/onboarding, and credential rules. The canonical NeuroLearn command reference and the installed `--help` remain the authority for supported flags. Do not copy a provider cascade or modify NeuroLearn core merely to run this study.

From the plugin skills directory, the launcher is `neurolearn/scripts/run_neurolearn.py`. Resolve its absolute path from the loaded plugin; cached version directories and a particular personal checkout are not permanent addresses.

Before a work command, run the NeuroLearn adapter's doctor procedure and inspect only the required configuration/status fields; keep secrets and unrelated private paths out of reports. Check effective acquisition and post-stage settings against the user's current policy. A missing key is not exhausted API quota. Use already-authorized supported controls or pause affected work if a compliant call is unavailable; never silently change global settings.

## Acquisition unit

Use backend `smart` for the source-to-transcript path, retaining its actual resulting backend. Backend selection and the similarly named preset are different controls.

For the currently supported single-video interface, the intended invocation is:

```bash
python3 <neurolearn-launcher> transcribe <youtube-video-url> --backend smart --preset smart --config <skill-directory>/assets/transcript-only.toml --vision-backend off --output-format all --output-dir <exclusive-attempt-directory>
```

Verify those options in the installed CLI before use. Explicitly deferring visuals prevents early video extraction, including automatic tutorial promotion. A later visual stage uses the original video URL and candidates derived from the transcript.

The bundled `assets/transcript-only.toml` fixes post-stages to local heuristics and file output, with translation, ASR correction, perplexity models, diarization, and early visuals disabled. Use it to prevent private preset overrides from silently enabling additional work. It does not change acquisition backend configuration or its approved API fallback, and it does not rewrite private settings. Separately requested enrichment can use an explicitly authorized configuration.

Single-video attempt directories isolate per-command manifests and preserve TXT/SRT/segment JSON with actual backend provenance. Do not run multiple writers in one output directory. Only release outputs after the process has finished, the source identity is checked, and transcript files and timestamps have been validated.

When the original source language is known, supply its supported `--language` code and check the exported transcript language before releasing it. An automatically selected translated track is a historical acquisition attempt, not a substitute for the intended original-language source. Preserve it, diagnose the mismatch, and reacquire only affected sources; never assume that a parsed CLI flag reached the actual acquisition configuration.

Batch mode may be used only after verifying equivalent per-video segment output, actual backend provenance, and isolation in the installed version. A requested backend such as `smart` is not proof of the backend that produced a particular transcript. A permissive transcript loader or a quality score is not a complete structural or semantic check.

Retries and fallbacks inside NeuroLearn remain its responsibility. Track the outer command, preserve failed attempts, and retry only a classified recoverable operation within the existing budget; do not multiply whole-batch retries or infer permission for local transcription from network/quality errors.

## Visual stage

Run it late, only for transcript-led candidates by default. Check the installed `frames --help` interface and reuse a per-video source cache for that video's intervals. The extraction tool may download the whole video even when only selected timestamps are needed.

Give each video an exclusive extraction directory and one active visual owner. Shared temporary frame names and per-command manifests make a common multi-video extraction folder unsuitable for concurrent writers. Distinct crop variants need distinct paths. Keep used evidence frames/crops outside the temporary cleanup tree or explicitly retain them in the data contract.

Use the agent's own vision to inspect obtained frames. Extraction is not observation. Report sampled poses as sampled poses; precise full demonstration boundaries require the corresponding observation and may remain uncertain. Provide the video start link plus a printed interval for the user to watch.
