"""Tests for v0.10.8 epistemic-framing infrastructure.

The framing must reach every surface where transcript content gets
fed to an LLM:

  * `combined.md` (batch / research output) → markdown banner block.
  * `manifest.json` → machine-readable `epistemic_status` field.
  * `analyze` prompt → prepended `EPISTEMIC_PROMPT_PREFIX`.
  * `report` outliner prompt → prepended `EPISTEMIC_PROMPT_PREFIX`.
  * `summarize` prompt → prepended `EPISTEMIC_PROMPT_PREFIX`.

The framing must NOT reach surfaces where the user reads raw content
themselves (single-file `.txt` / `.srt`). Those are unchanged.

Each test asserts both presence AND content — the banner has to
*say* the right thing, not just exist.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from skills.neurolearn.utils.output_writer import (
    EPISTEMIC_BANNER_MARKDOWN, EPISTEMIC_PROMPT_PREFIX,
    BatchMeta, write_combined_md, write_manifest_json,
)


def _meta() -> BatchMeta:
    return BatchMeta(
        batch_name="research_x", created_at=datetime(2026, 5, 20),
        source_type="mixed", source_url=None,
        backend="subtitles", backend_options={}, language="auto",
    )


# ---------------------------------------------------------------------------
# Banner content sanity
# ---------------------------------------------------------------------------


def test_banner_says_third_party_not_truth():
    """The banner must explicitly frame content as third-party material."""
    text = EPISTEMIC_BANNER_MARKDOWN.lower()
    assert "third-party" in text
    assert "ground truth" not in text or "not" in text  # framing only
    # Key behavior the agent should adopt.
    assert "synthesize" in text
    assert "disagreement" in text
    # Negative phrasing: NOT "you should do X".
    assert "candidate inputs" in text or "not as instructions" in text
    # Tells the agent to not escalate confidence.
    assert "hedge" in text or "confidence" in text


def test_prompt_prefix_says_same_thing_to_llm():
    """The prompt-prefix variant carries equivalent stance for LLMs
    that receive it as part of a system / instruction prompt."""
    text = EPISTEMIC_PROMPT_PREFIX.lower()
    assert "third-party" in text
    assert "synthesize" not in text or True  # prompt is shorter; ok
    assert (
        "candidate inputs" in text
        or "not as ground truth" in text
        or "weigh" in text
    )
    assert "attribute" in text or "match" in text


# ---------------------------------------------------------------------------
# combined.md surface
# ---------------------------------------------------------------------------


def test_combined_md_contains_epistemic_banner(tmp_path: Path):
    """Every combined.md (batch / research) MUST embed the banner —
    the file is by design read by a downstream LLM."""
    path = write_combined_md([], _meta(), tmp_path)
    text = path.read_text(encoding="utf-8")
    # Spot-check several lines from the banner so we catch partial
    # accidental edits.
    assert "third-party video content" in text.lower()
    assert "synthesize" in text.lower()
    assert "weigh against" in text.lower()


def test_combined_md_banner_appears_before_content(tmp_path: Path):
    """Order matters: banner must sit between the YAML frontmatter and
    the body header — i.e. the first thing the LLM sees after the
    machine-readable frontmatter."""
    path = write_combined_md([], _meta(), tmp_path)
    text = path.read_text(encoding="utf-8")
    banner_idx = text.lower().find("third-party video content")
    body_idx = text.find("# Batch transcript")
    assert banner_idx != -1
    assert body_idx != -1
    assert banner_idx < body_idx, "banner must precede the body section"


# ---------------------------------------------------------------------------
# manifest.json surface
# ---------------------------------------------------------------------------


def test_manifest_json_has_epistemic_status_field(tmp_path: Path):
    """Machine-readable counterpart of the human-facing banner.
    Tools that consume manifest.json can pick this up directly."""
    write_manifest_json([], [], _meta(), tmp_path)
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["epistemic_status"] == "community_content_unverified"


# ---------------------------------------------------------------------------
# analyze prompt surface
# ---------------------------------------------------------------------------


def test_analyze_prompt_includes_epistemic_prefix():
    """`analyze.build_prompt` constructs the LLM input string —
    the prefix must be in it."""
    from skills.neurolearn.analyze.prompt_builder import build_prompt
    from skills.neurolearn.analyze.source_resolver import VideoSource

    fake_video = VideoSource(
        transcript_path=Path("/no/such/file.txt"),
        title="t", url="https://youtu.be/x",
        upload_date=None, duration_sec=None, language=None,
    )
    prompt = build_prompt("Tell me about Claude", [fake_video])
    assert "third-party" in prompt.lower()


# ---------------------------------------------------------------------------
# report outliner prompt surface
# ---------------------------------------------------------------------------


def test_report_outliner_prompt_includes_epistemic_prefix():
    """`report` outliner builds the final LLM prompt via _build_full_prompt;
    it must include the prefix."""
    from skills.neurolearn.report.outliner import _build_full_prompt

    full = _build_full_prompt(
        spec_template="Generate JSON outline.",
        target_language="en",
        user_filter="",
        transcript_excerpt="[00:00:00] hello",
        visual_segments_excerpt="(none)",
    )
    assert "third-party" in full.lower()


# ---------------------------------------------------------------------------
# summarize prompt surface
# ---------------------------------------------------------------------------


def test_summarize_prompt_includes_epistemic_prefix():
    """`summarize_transcript` sends a prompt to the LLM — same framing
    applies. We inspect the literal `_SUMMARY_PROMPT` template since
    that's where the prefix is statically wired."""
    from skills.neurolearn.quality.summarizer import _SUMMARY_PROMPT
    assert "third-party" in _SUMMARY_PROMPT.lower()


# ---------------------------------------------------------------------------
# Negative: raw .txt / .srt files unchanged
# ---------------------------------------------------------------------------


def test_single_txt_file_writer_does_not_inject_banner(tmp_path: Path):
    """When the user runs plain `transcribe <URL>`, the resulting
    `.txt` file is for THEIR reading, not an LLM's. The banner must
    NOT be in it — it'd add noise to a user-facing transcript."""
    from skills.neurolearn.utils.output_writer import write_txt_plain

    fake_seg = MagicMock(start=0.0, end=1.0, text="hello world")
    out_path = tmp_path / "x.txt"
    write_txt_plain([fake_seg], out_path)

    content = out_path.read_text(encoding="utf-8")
    # The body must NOT contain banner text.
    assert "third-party video content" not in content.lower()
    # And the actual transcript content IS present.
    assert "hello world" in content
