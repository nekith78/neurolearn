"""LLM-based auto-summary of transcripts (v0.5.1).

Single LLM call, generates a structured Markdown summary:
- 1-paragraph TL;DR
- Bullet list of key points
- Notable quotes with timestamps

Same backend switch as ASR correction / translation: gemini / claude /
openai / ollama. Cheap text-only call.
"""
from __future__ import annotations

from skills.youtube_transcribe.quality.asr_corrector import (
    _call_claude, _call_gemini, _call_ollama, _call_openai,
)
from skills.youtube_transcribe.utils.output_writer import Segment


_SUMMARY_PROMPT = """\
You are summarizing a video transcript. Produce a structured Markdown
summary in {language}.

Format (use these EXACT section headers):

## TL;DR
<one paragraph, 2-4 sentences>

## Key points
- <bullet 1>
- <bullet 2>
- ...

## Notable quotes
- [HH:MM:SS] "<quote>"
- ...

Rules:
- Be concise. Don't repeat the same idea twice.
- Quotes should be exact spans from the transcript (not paraphrased).
- Timestamps in `HH:MM:SS` (no fractional seconds).
- 3–7 key points; 0–5 notable quotes.

Transcript (with timecodes in seconds):
{transcript_text}

Output ONLY the markdown summary. No preamble, no code fence.
"""


def _format_transcript_for_summary(segments: list[Segment]) -> str:
    """Compact `[HH:MM:SS] text` lines, truncated at 60k chars."""
    lines = []
    total = 0
    for s in segments:
        h = int(s.start // 3600)
        m = int((s.start % 3600) // 60)
        sec = int(s.start % 60)
        line = f"[{h:02d}:{m:02d}:{sec:02d}] {s.text.strip()}"
        if total + len(line) > 60_000:
            lines.append("[...truncated...]")
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def summarize_transcript(
    segments: list[Segment],
    language: str = "en",
    *,
    api_key: str | None,
    backend: str = "gemini",
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Returns Markdown summary or empty string on failure."""
    if not segments:
        return ""

    prompt = _SUMMARY_PROMPT.format(
        language=language or "en",
        transcript_text=_format_transcript_for_summary(segments),
    )

    try:
        if backend == "gemini":
            return _call_gemini(prompt, api_key or "")
        if backend == "claude":
            return _call_claude(prompt, api_key or "")
        if backend == "openai":
            return _call_openai(prompt, api_key or "")
        if backend == "ollama":
            return _call_ollama(prompt, model=ollama_model, host=ollama_host)
    except Exception:
        return ""
    return ""
