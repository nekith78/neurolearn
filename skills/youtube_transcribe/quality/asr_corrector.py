"""ASR error correction via cheap text-only LLM (spec §17 carry-over).

Takes a transcript that failed quality check and asks a cheap LLM
(gemini-flash / claude-haiku / gpt-4o-mini) to fix obviously broken
or garbled words while preserving timestamps, segment boundaries,
slang, jargon, and names.

Opt-in via `cfg["correct_asr"]=True` (preset / CLI flag). Defaults
to backend="gemini" but can use any of the three LLM providers.

Single call per video; cost ≈ $0.001-$0.01 depending on transcript
length and chosen backend.
"""
from __future__ import annotations

import json
import re

from skills.youtube_transcribe.utils.output_writer import Segment


_CORRECTION_PROMPT = """\
You are correcting an ASR (automatic speech recognition) transcript that
likely has errors: truncated words, garbled sequences, mis-recognised
foreign terms. Output a corrected JSON array.

Rules:
- Same number of segments as input.
- Preserve each segment's `start` and `end` exactly (do not change timing).
- Fix ONLY obviously broken words (e.g. "elephats" → "elephants",
  "prveит" → "привет").
- DO NOT change slang, jargon, brand names, technical terms, code, or
  proper nouns. Preserve them verbatim.
- DO NOT translate. Keep the original language ({language}).
- DO NOT add new content or remove segments.

Input transcript (JSON):
{transcript_json}

Output: JSON array of {{start, end, text}}, same length as input.
Return ONLY the JSON array, no preamble, no markdown fence.
"""


def _build_input_json(segments: list[Segment]) -> str:
    payload = [
        {"start": float(s.start), "end": float(s.end), "text": s.text}
        for s in segments
    ]
    return json.dumps(payload, ensure_ascii=False)


def _parse_corrected_segments(
    raw: str, original: list[Segment],
) -> list[Segment]:
    """Parse LLM response. On any error, return `original` unchanged."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return original
    if not isinstance(data, list) or len(data) != len(original):
        return original

    out: list[Segment] = []
    for orig, item in zip(original, data):
        if not isinstance(item, dict) or "text" not in item:
            return original
        out.append(Segment(start=orig.start, end=orig.end, text=str(item["text"])))
    return out


def correct_transcript_via_llm(
    segments: list[Segment],
    language: str,
    *,
    api_key: str,
    backend: str = "gemini",
) -> list[Segment]:
    """Run a single LLM call to fix obvious ASR errors. Best-effort.

    backend: "gemini" | "claude" | "openai". Default "gemini" (cheap, fast).
    Returns the corrected segments. On any failure (no API, parse error,
    wrong length), returns the original segments unchanged.
    """
    if not segments:
        return segments

    transcript_json = _build_input_json(segments)
    prompt = _CORRECTION_PROMPT.format(
        language=language, transcript_json=transcript_json,
    )

    try:
        if backend == "gemini":
            text = _call_gemini(prompt, api_key)
        elif backend == "claude":
            text = _call_claude(prompt, api_key)
        elif backend == "openai":
            text = _call_openai(prompt, api_key)
        else:
            return segments
    except Exception:
        return segments

    return _parse_corrected_segments(text, segments)


def _call_gemini(prompt: str, api_key: str) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-2.5-flash", contents=[prompt],
    )
    return resp.text or ""


def _call_claude(prompt: str, api_key: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(blocks)


def _call_openai(prompt: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "") if resp.choices else ""
