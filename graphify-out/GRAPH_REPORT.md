# Graph Report - /Users/nekith78/youtube-transcribe/skills/youtube_transcribe  (2026-05-13)

## Corpus Check
- Corpus is ~38,066 words - fits in a single context window. You may not need a graph.

## Summary
- 1133 nodes · 1674 edges · 120 communities (70 shown, 50 thin omitted)
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 394 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_ASR Backends (impl)|ASR Backends (impl)]]
- [[_COMMUNITY_Backend Factory + Smart Mode|Backend Factory + Smart Mode]]
- [[_COMMUNITY_Quality Heuristics|Quality Heuristics]]
- [[_COMMUNITY_Config & Wizard|Config & Wizard]]
- [[_COMMUNITY_Subscribes — Channels + RSS|Subscribes — Channels + RSS]]
- [[_COMMUNITY_Detection Pipeline|Detection Pipeline]]
- [[_COMMUNITY_LLM Call Helpers|LLM Call Helpers]]
- [[_COMMUNITY_Analyze Runner|Analyze Runner]]
- [[_COMMUNITY_Subscribes — CLI|Subscribes — CLI]]
- [[_COMMUNITY_Downloader & Format Utils|Downloader & Format Utils]]
- [[_COMMUNITY_Backend Base Types|Backend Base Types]]
- [[_COMMUNITY_Trigger Matcher (Aho-Corasick)|Trigger Matcher (Aho-Corasick)]]
- [[_COMMUNITY_Trigger Matcher (raw automaton)|Trigger Matcher (raw automaton)]]
- [[_COMMUNITY_Analyze Prompt Builder|Analyze Prompt Builder]]
- [[_COMMUNITY_Config Loader (Wizard side)|Config Loader (Wizard side)]]
- [[_COMMUNITY_CLI — transcribe  batch|CLI — transcribe / batch]]
- [[_COMMUNITY_Analyze Picker (TUI)|Analyze Picker (TUI)]]
- [[_COMMUNITY_Window Merge (visual segments)|Window Merge (visual segments)]]
- [[_COMMUNITY_Research Source Adapter|Research Source Adapter]]
- [[_COMMUNITY_Analyze Output Writer|Analyze Output Writer]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 112|Community 112]]
- [[_COMMUNITY_Community 113|Community 113]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 115|Community 115]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]
- [[_COMMUNITY_Community 118|Community 118]]
- [[_COMMUNITY_Community 119|Community 119]]

## God Nodes (most connected - your core abstractions)
1. `Segment` - 29 edges
2. `run_subscribes_update()` - 26 edges
3. `BackendError` - 24 edges
4. `get_api_key()` - 22 edges
5. `transcribe_cmd()` - 20 edges
6. `TranscriptionResult` - 20 edges
7. `load_config()` - 19 edges
8. `apply_v02_stages()` - 19 edges
9. `run_research()` - 19 edges
10. `BackendNotConfigured` - 19 edges

## Surprising Connections (you probably didn't know these)
- `_BareURLGroup` --uses--> `Config`  [INFERRED]
  transcribe.py → config.py
- `transcribe_cmd()` --calls--> `load_config()`  [INFERRED]
  transcribe.py → config.py
- `batch_cmd()` --calls--> `load_config()`  [INFERRED]
  transcribe.py → config.py
- `config_test()` --calls--> `load_config()`  [INFERRED]
  transcribe.py → config.py
- `analyze_cmd()` --calls--> `load_config()`  [INFERRED]
  transcribe.py → config.py

## Hyperedges (group relationships)
- **Quality signal aggregation in HeuristicChecker** — heuristicchecker_check, spell_outofvocabratio, boh_coverage, repetition_trigramrate, repetition_nonspeechratio, perplexity_anomalyscore [INFERRED 0.95]
- **Shared LLM provider call helpers used by ASR-correction/translation/summary** — asrcorrector_callgemini, asrcorrector_callclaude, asrcorrector_callopenai, asrcorrector_callollama, asrcorrector_correct, translator_translate [EXTRACTED 1.00]
- **End-to-end webui transcription flow** — webui_runone, resolver_resolve, pipeline_runpipeline, pipeline_v02_module, outputwriter_writetxttimestamps, outputwriter_writevisualmd [INFERRED 0.95]
- **all backends implement Transcriber and are instantiated by factory** —  [INFERRED 0.95]
- **research pipeline orchestrates search→date-filter→match→llm-screen→transcribe→history** —  [INFERRED 0.95]
- **anchor language picking uses script detection over candidate languages** —  [INFERRED 0.90]
- **subscribes update — fetch+filter+transcribe+analyze+state** — cli_update_cmd, pipeline_run_subscribes_update, store_load_subscribes, rss_fetch_rss, pipeline_fetch_via_yt_dlp, state_update_last_seen, pipeline_append_history, history_store_append_run, backend_resolver_resolve_analyze_backend [INFERRED 0.95]
- **analyze step — source resolution, prompt build, LLM call, output write** — source_resolver_resolve_source, picker_pick_videos, prompt_builder_build_prompt, runner_run_analysis, output_writer_write_analysis, output_writer_append_analysis, select_parser_parse_select [INFERRED 0.95]
- **Cross-OS schedule snippet generators (cron/launchd/systemd/Task Scheduler)** — schedule_detect_platform, schedule_parse_interval, schedule_generate_cron_line, schedule_generate_launchd_plist, schedule_generate_systemd_units, schedule_generate_taskscheduler_xml, cli_schedule_install_cmd [INFERRED 0.95]
- **Vision backends (Gemini/Claude/OpenAI) implement VisionBackend protocol** — gemini_gemini_vision_backend, claude_vision_claude_vision_backend, openai_vision_openai_vision_backend, frames_extract_keyframes, prompts_format_prompt [INFERRED 0.95]
- **Detection pipeline: triggers → matcher → window_merge → frame_diff/scene refinement** — triggers_load_triggers, matcher_match_segment, window_merge_merge_overlapping_windows, window_merge_refine_with_frame_diff, scene_find_scene_boundaries, llm_classify_find_visual_moments_via_llm, window_merge_select_windows_by_budget [INFERRED 0.85]
- **Preset resolution: registry defaults < builtin presets < user config < CLI overrides** — registry_registry_list, loader_load_preset_values, loader_resolve_with_env_checks, wizard_run_wizard [INFERRED 0.85]

## Communities (120 total, 50 thin omitted)

### Community 0 - "ASR Backends (impl)"
Cohesion: 0.06
Nodes (45): AssemblyAIBackend, _build_transcriber(), AssemblyAI backend — best/nano speech models.  Uses assemblyai>=0.64.0 SDK. API:, Lazy-import assemblyai and return a configured Transcriber instance., BackendError, BackendNotConfigured, Base abstractions for all transcription backends., Generic backend failure. (+37 more)

### Community 1 - "Backend Factory + Smart Mode"
Cohesion: 0.05
Nodes (65): Backend factory + smart-mode composition.  Public API:   build_backend(name, cfg, Smart-mode composition: subtitles fast-path → fallback_backend.      Logic (spec, run_smart(), Exception, _build_search_url(), _extract(), _pick_sp_preset(), Multi-language YouTube search via yt-dlp + YouTube's built-in `sp` filter.  When (+57 more)

### Community 2 - "Quality Heuristics"
Cohesion: 0.05
Nodes (37): Return (True, None) if ready; (False, reason) otherwise., Transcriber, Detector, DetectionWindow + Detector Protocol., Anything that finds visual-important windows in a video., Protocol, QualityChecker, QualityReport (+29 more)

### Community 3 - "Config & Wizard"
Cohesion: 0.05
Nodes (40): backends.factory build_backend/run_smart, Config dataclass, CONFIG_DIR / CONFIG_PATH / ENV_PATH constants, get_api_key(), load_config(), maybe_auto_update_ytdlp(), ChannelEntry dataclass, _diagnose_ytdlp_error() (+32 more)

### Community 4 - "Subscribes — Channels + RSS"
Cohesion: 0.06
Nodes (44): _extract_flat(), _extract_handle(), Resolve a YouTube channel URL to a stable channel_id (UC...).  One-time call on, Return ResolvedChannel for a YouTube channel URL.      Raises ValueError if the, Extract @handle from a YouTube URL, if present., yt-dlp wrapper — isolated for tests to mock., resolve_channel(), ResolvedChannel (+36 more)

### Community 5 - "Detection Pipeline"
Cohesion: 0.08
Nodes (45): _build_config(), _array_contains(), _atomic_write(), cmd_add(), cmd_edit(), cmd_init(), cmd_list(), cmd_remove() (+37 more)

### Community 6 - "LLM Call Helpers"
Cohesion: 0.08
Nodes (31): analyze.runner.run_analysis, _call_claude(), _call_gemini(), _call_ollama(), _call_openai(), correct_transcript_via_llm(), _parse_corrected_segments(), QualityReport dataclass (+23 more)

### Community 7 - "Analyze Runner"
Cohesion: 0.09
Nodes (31): Send a fully-built prompt to one of the four LLM backends.  Thin wrapper over th, Return LLM response text, or "" on failure / empty response., run_analysis(), _build_input_json(), _call_claude(), _call_gemini(), _call_ollama(), _call_openai() (+23 more)

### Community 8 - "Subscribes — CLI"
Cohesion: 0.07
Nodes (32): _default_editor(), edit_cmd(), CLI for `youtube-transcribe subscribes` group: add / remove / list / edit / upda, Open subscribes.toml in $EDITOR (vi/notepad fallback)., Cross-OS fallback editor., Generate scheduler snippets (cron/launchd/systemd/Task Scheduler)., Print a schedule snippet + install instructions for the current OS., Print uninstall instructions for all supported platforms. (+24 more)

### Community 9 - "Downloader & Format Utils"
Cohesion: 0.11
Nodes (28): is_url(), _fmt_date(), _fmt_duration(), _format_timestamp_dotted(), format_timestamp_srt(), Format transcription segments into .txt and .srt files., Render combined.md with YAML front-matter + per-video sections (flat text, no ti, 01:02:03.456 — used in .txt with timestamps. (+20 more)

### Community 10 - "Backend Base Types"
Cohesion: 0.12
Nodes (29): AssemblyAIBackend, _build_transcriber, BackendError, BackendNotConfigured, Transcriber, TranscriptionResult, CustomBackend, _build_client (+21 more)

### Community 11 - "Trigger Matcher (Aho-Corasick)"
Cohesion: 0.11
Nodes (27): _build_automaton_cached(), _build_raw_automaton(), _build_strict_automaton(), _cosine(), _detect_lang(), _get_encoder(), _get_lemmatizer(), _get_universal_embeddings_cached() (+19 more)

### Community 12 - "Trigger Matcher (raw automaton)"
Cohesion: 0.08
Nodes (28): _build_automaton_cached, _build_raw_automaton, _build_strict_automaton, _cosine, _detect_lang, _get_encoder, _get_lemmatizer, _get_universal_embeddings_cached (+20 more)

### Community 13 - "Analyze Prompt Builder"
Cohesion: 0.1
Nodes (23): _fmt_duration(), _format_segments(), Build the final prompt sent to the LLM for `analyze`.  Concatenates a neutral sy, Read transcript from disk and format. Truncate at max_chars., _truncate(), _video_body(), _video_header(), _format_transcript_for_summary() (+15 more)

### Community 14 - "Config Loader (Wizard side)"
Cohesion: 0.12
Nodes (22): Config, _from_toml_dict(), load_config(), mask_key(), migrate_v01_to_v02(), Config loading/saving and API key handling.  Config layout (TOML):   ~/.youtube-, Migrate v0.1.x config.toml to v0.2 format.      Preserves user's existing settin, sk-1234567890abcdef → sk-1***cdef (+14 more)

### Community 15 - "CLI — transcribe / batch"
Cohesion: 0.1
Nodes (23): _api_key_for_backend(), _auto_batch_name(), cli(), config(), config_test(), config_wizard(), _ensure_gradio_installed(), CLI root + `transcribe` sub-command. Bare-URL form routes to `transcribe`. The ` (+15 more)

### Community 16 - "Analyze Picker (TUI)"
Cohesion: 0.16
Nodes (16): _fmt_duration(), pick_batch(), pick_videos(), PickerCancelled, Interactive selection of batch + videos via questionary.  TTY-gated. Caller is e, User hit Ctrl-C / esc in the picker., Single-select picker over subfolders containing manifest.json.      Newest first, Multi-select checkbox over videos. Returns chosen subset.      Raises PickerCanc (+8 more)

### Community 17 - "Window Merge (visual segments)"
Cohesion: 0.16
Nodes (15): DetectionWindow, merge_overlapping_windows(), Window merge (combine overlaps + close gaps) and budget selection., If matches fit within budget — return all. Otherwise:       1. Divide video into, Sort by start, merge if overlap or gap < max_gap. Keep best (priority_score) rea, Refine windows with perceptual-hash frame diffing (spec §5 brick C).      For ea, refine_with_frame_diff(), select_windows_by_budget() (+7 more)

### Community 18 - "Research Source Adapter"
Cohesion: 0.2
Nodes (15): _rss_to_candidate(), One video from YouTube search results., SearchCandidate, _backend_to_key(), _ChannelVideo, _fetch_via_yt_dlp(), _parse_iso(), Subscribes command orchestration — stateful incremental update.  State update ru (+7 more)

### Community 19 - "Analyze Output Writer"
Cohesion: 0.17
Nodes (15): analysis_filename(), append_analysis(), Write `analysis-*.md` files for the `analyze` sub-command., Default `analysis-YYYY-MM-DD-HHMM.md` filename., Write a fresh analysis file. Resolves filename collisions with `-N`., Append a block to `target`. Creates with `# Combined analyses` if new., _render_block(), _resolve_collision() (+7 more)

### Community 20 - "Community 20"
Cohesion: 0.18
Nodes (14): list_preset_names(), _load_builtin(), load_preset_values(), _load_toml(), Load preset values: built-in defaults < user config.toml < external --config < C, Resolve final values for `preset_name`. Priority (lowest to highest):       1. r, Same as load_preset_values, but applies silent fallbacks for missing API keys., resolve_with_env_checks() (+6 more)

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (12): list_cmd, filter_by_group(), _backend_to_key, _ChannelVideo (dataclass), _fetch_via_yt_dlp(), _parse_iso() (pipeline), run_subscribes_update(), _tty_checkpoint (+4 more)

### Community 22 - "Community 22"
Cohesion: 0.21
Nodes (13): _backend_to_key(), _fetch_from_subscribes(), _filter_by_window(), _load_default_cfg(), Research command orchestration — search → filter → transcribe → analyze., Pull latest videos from subscribes channels (via RSS)., Apply a date window. Candidates without a known date are kept.      Source seman, Show interactive checkbox picker; return chosen subset. (+5 more)

### Community 23 - "Community 23"
Cohesion: 0.15
Nodes (14): BatchFailure, BatchMeta, Метадата batch-прогона. Передаётся в writers, попадает в YAML/JSON., Один отказ в batch — для errors.log и manifest.json., Render machine-readable manifest.json mirroring combined.md structure., Write errors.log only if there were failures; otherwise return None., write_errors_log(), write_manifest_json() (+6 more)

### Community 24 - "Community 24"
Cohesion: 0.2
Nodes (9): Vision backend Protocol + VisualSegment data type., One annotated visual moment., Multimodal LLM that can describe video+audio together., VisionBackend, VisualSegment, _build_content(), OpenAIVisionBackend, _parse_response() (+1 more)

### Community 25 - "Community 25"
Cohesion: 0.16
Nodes (14): ClaudeVisionBackend.annotate_segments, ClaudeVisionBackend._build_content, ClaudeVisionBackend._call_with_retry, ClaudeVisionBackend._parse_response, extract_keyframes, _tmp_pattern, GeminiVisionBackend.annotate_segments, GeminiVisionBackend._call_with_retry (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.22
Nodes (12): entries_after(), fetch_rss(), _http_get(), _parse_iso(), parse_rss(), YouTube channel RSS feed — fetch via urllib, parse via xml.etree.  YouTube expos, Fetch + parse RSS for a channel. Empty list on any error., Parse YouTube channel RSS XML. Empty list on malformed input. (+4 more)

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (12): _persist_choice(), _prompt_for_default(), Resolve which LLM backend should run the post-transcribe `analyze` step.  Decisi, Return the analyze backend to use, or None to skip the step.      The `is_tty` p, One-shot interactive prompt. Returns one of _VALID_BACKENDS., resolve_analyze_backend(), Run subscribes update — fetch latest, filter, transcribe, analyze., update_cmd() (+4 more)

### Community 28 - "Community 28"
Cohesion: 0.17
Nodes (13): DetectionWindow, ClaudeVisionBackend, detect_frame_changes_in_window, _extract_frame_hashes, FrameDiff, GeminiVisionBackend, find_visual_moments_via_llm, _format_transcript (+5 more)

### Community 29 - "Community 29"
Cohesion: 0.26
Nodes (11): append_run(), _from_dict(), get_run(), list_runs(), Persistent log of research/subscribes runs as a TOML file.  Stored at ~/.youtube, Append a run to history.toml., Return runs newest-first. Filter by type if given., RunEntry (+3 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (12): DateWindow, in_window, parse_window, _build_prompt, _extract_indices, _fmt_dur, screen_candidates, match_titles (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.2
Nodes (12): _array_contains, _atomic_write, cmd_add, cmd_init, cmd_remove, cmd_reset, _ensure_section, _load_doc (+4 more)

### Community 32 - "Community 32"
Cohesion: 0.22
Nodes (9): attach_speakers_to_segments(), diarize_audio(), _get_pipeline(), is_diarization_available(), Speaker diarization via pyannote.audio (spec v0.5).  Returns list of (start, end, Lazy-load the pretrained pyannote pipeline., Both pyannote installed AND HF token present?, Run pyannote diarization on an audio/video file.      Returns list of (start_sec (+1 more)

### Community 33 - "Community 33"
Cohesion: 0.28
Nodes (5): GeminiVisionBackend, _parse_response(), GeminiVisionBackend — multimodal annotation via Gemini File API., format_prompt(), Prompt templates for vision-LLM annotation of video moments.

### Community 34 - "Community 34"
Cohesion: 0.22
Nodes (3): schedule_install_cmd, generate_cron_line(), generate_taskscheduler_xml()

### Community 35 - "Community 35"
Cohesion: 0.22
Nodes (9): list_preset_names, _load_builtin (presets), load_preset_values, _load_toml (presets), resolve_with_env_checks, fields_by_section, get_field, REGISTRY (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.29
Nodes (7): DateWindow, in_window(), parse_window(), Parse --days / --since / --until into a date window, and test membership.  Used, Inclusive date window [start, end]., Return a DateWindow or None if no filter given.      Raises ValueError on mutex, Inclusive membership test. Accepts date or datetime.

### Community 37 - "Community 37"
Cohesion: 0.36
Nodes (7): _build_prompt(), _extract_indices(), _fmt_dur(), LLM-based pre-screening of candidate videos by title+metadata.  Used by --filter, Return subset chosen by the LLM, or all candidates on parse failure.      `candi, Parse JSON array of ints from LLM output. None on failure., screen_candidates()

### Community 38 - "Community 38"
Cohesion: 0.25
Nodes (7): list_cmd(), List subscribed channels., filter_by_group(), list_groups(), Channel grouping helpers — filter and listing for subscribes.  Groups are user-d, Return channels matching the given group.      - None → all channels (no filter), Return sorted unique non-None group names.

### Community 39 - "Community 39"
Cohesion: 0.32
Nodes (7): find_visual_moments_via_llm(), _format_transcript(), _parse_response(), LLM full-pass classifier for visual moments (spec §5 brick D).  Sends the entire, Format segments as `[start_sec - end_sec] text` lines.      Truncates at ~60k ch, Strip code fences and parse JSON array. Returns [] on any error., Send transcript to Gemini text-only API, parse timecode list.      Returns list[

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (8): _fetch_from_subscribes, _rss_to_candidate, _build_search_url, _extract, _pick_sp_preset, search_multi_language, SearchCandidate, _SP_PRESETS

### Community 41 - "Community 41"
Cohesion: 0.29
Nodes (6): history_group(), list_cmd(), CLI for `youtube-transcribe history` — list and show past runs., View past research / subscribes runs., Show full details for one run., show_cmd()

### Community 42 - "Community 42"
Cohesion: 0.43
Nodes (4): _build_content(), ClaudeVisionBackend, _parse_response(), ClaudeVisionBackend — multimodal annotation via Claude Sonnet vision.  Unlike Ge

### Community 43 - "Community 43"
Cohesion: 0.38
Nodes (6): detect_frame_changes_in_window(), _extract_frame_hashes(), FrameDiff, Frame difference detection via perceptual hashing (imagehash).  Used inside trig, Use ffmpeg to dump frames at fps, hash each. Returns list[(timestamp, hash)]., Returns frame timestamps where visual changed substantially vs. previous frame.

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (6): build_prompt() (analyze), _fmt_duration() (analyze), _format_segments() (analyze), _truncate() (analyze), _video_body(), _video_header()

### Community 45 - "Community 45"
Cohesion: 0.47
Nodes (5): detect_platform(), PlatformInfo, _query_nvidia_vram_mb(), Auto-detect OS, GPU, VRAM to pick the right Whisper implementation., Returns total VRAM in MiB if nvidia-smi works, else None.

### Community 46 - "Community 46"
Cohesion: 0.4
Nodes (5): extract_keyframes(), Extract keyframes from video via ffmpeg.  Output naming: <video_id>_<seconds>.jp, Pattern for ffmpeg output files (overridable in tests)., Extract <count> evenly-spaced keyframes from [start, end] window.      Files nam, _tmp_pattern()

### Community 47 - "Community 47"
Cohesion: 0.4
Nodes (5): ocr_keyframes(), OCR for keyframes — opt-in via --ocr flag.  Tries pytesseract first (requires sy, Single keyframe → text. Override-able for testing., Returns one OCR'd string per keyframe. Errors → empty string for that frame., _run_tesseract()

### Community 48 - "Community 48"
Cohesion: 0.4
Nodes (5): BatchFailure dataclass, BatchMeta dataclass, BatchVideoStatus dataclass, write_combined_md(), write_manifest_json()

### Community 49 - "Community 49"
Cohesion: 0.33
Nodes (5): _extract_flat(), resolve_channel(), add_cmd, add_channel(), _to_dict()

### Community 50 - "Community 50"
Cohesion: 0.5
Nodes (4): _add_one_based(), parse_select(), Parse `--select` strings like `"1,3,5-7"` to 0-based index lists., Parse 1-based selection string, return sorted 0-based unique indices.      Forma

### Community 52 - "Community 52"
Cohesion: 0.4
Nodes (5): BACKEND_CHOICES, _BareURLGroup, cli, _derive_basename, transcribe_cmd

### Community 53 - "Community 53"
Cohesion: 0.4
Nodes (3): resolve_analyze_backend(), update_cmd, Channel (dataclass)

### Community 55 - "Community 55"
Cohesion: 0.4
Nodes (5): build_queries_per_language, detect_script, pick_anchor_language, _script_of_language, translate_query

### Community 56 - "Community 56"
Cohesion: 0.5
Nodes (5): cmd_weight_set, cmd_weight_unset, _find_phrase_in_array, _parse_weight_args, _resolve_arr

### Community 57 - "Community 57"
Cohesion: 0.5
Nodes (3): match_titles(), Case-insensitive substring filter on a `title` attribute.  Used by --match flag, Return candidates whose `.title` contains `pattern` (case-insensitive).      Emp

### Community 58 - "Community 58"
Cohesion: 0.5
Nodes (4): BatchVideoStatus, Один итоговый ряд таблицы по результату прогона одного видео., _build_video_status(), Convert a successful pipeline result into a BatchVideoStatus manifest entry.

### Community 59 - "Community 59"
Cohesion: 0.5
Nodes (3): find_scene_boundaries(), Scene boundary detection via PySceneDetect.  Returns scene START timestamps in s, Returns list of scene-change timestamps in seconds.      threshold: ContentDetec

### Community 61 - "Community 61"
Cohesion: 0.67
Nodes (3): append_analysis(), _render_block(), write_analysis()

## Knowledge Gaps
- **446 isolated node(s):** `Config loading/saving and API key handling.  Config layout (TOML):   ~/.youtube-`, `Pack Config into nested dict matching the spec layout.`, `Migrate v0.1.x config.toml to v0.2 format.      Preserves user's existing settin`, `sk-1234567890abcdef → sk-1***cdef`, `youtube-transcribe — universal transcription skill.` (+441 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **50 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `apply_v02_stages()` connect `Window Merge (visual segments)` to `Community 32`, `Community 33`, `Quality Heuristics`, `Detection Pipeline`, `Analyze Runner`, `Downloader & Format Utils`, `Community 42`, `Community 47`, `Community 24`?**
  _High betweenness centrality (0.238) - this node is a cross-community bridge._
- **Why does `run_subscribes_update()` connect `Research Source Adapter` to `Backend Factory + Smart Mode`, `Subscribes — Channels + RSS`, `Community 36`, `Community 38`, `Community 37`, `Config Loader (Wizard side)`, `CLI — transcribe / batch`, `Analyze Output Writer`, `Community 23`, `Community 57`, `Community 26`, `Community 27`, `Community 29`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Why does `transcribe_cmd()` connect `Downloader & Format Utils` to `Backend Factory + Smart Mode`, `Config Loader (Wizard side)`, `CLI — transcribe / batch`, `Window Merge (visual segments)`, `Community 20`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `Segment` (e.g. with `HeuristicChecker` and `_ApiAdapter`) actually correct?**
  _`Segment` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `run_subscribes_update()` (e.g. with `_handle_subscribes_update()` and `update_cmd()`) actually correct?**
  _`run_subscribes_update()` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `BackendError` (e.g. with `_BareURLGroup` and `_ApiAdapter`) actually correct?**
  _`BackendError` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `get_api_key()` (e.g. with `_api_key_for_backend()` and `config_show()`) actually correct?**
  _`get_api_key()` has 21 INFERRED edges - model-reasoned connections that need verification._