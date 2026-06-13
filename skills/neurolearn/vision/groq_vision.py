"""GroqVisionBackend — keyframe annotation via Groq Llama-4-Scout vision.

v0.12.0 primary vision backend. Replaces Gemini per-frame in the default
cascade for several reasons:

- Llama-4-Scout free tier: 30 RPM / 1000 RPD (~5x faster than Gemini 2.5-flash
  free 10 RPM / 250 RPD and 50x more daily quota than Gemini 3.5-flash's 20).
- Per-call price 3-5x cheaper than Gemini Flash even on paid tiers.
- Structured-output via response_format={"type":"json_schema","strict":true}
  enforces our 5-field shape without retries.
- No prompt caching (Groq cache list as of May 2026 covers only GPT-OSS), but
  the per-call cost is so low (~$0.000077 for our 700-token system prompt)
  that caching has zero ROI here.

Prompt selection: this backend pulls the [prompts.<type>.groq] variant
from prompts_default.toml (or user TOML), because Llama-4-Scout responds
differently than Gemini — see C1+C2 commits and the Llama 4 prompting
research at qa-out/v0.12.0-vision-compare/REPORT_V2.md.

API mechanics: Groq has no video upload. We extract keyframes via ffmpeg
(shared with GeminiVisionBackend) and POST them as base64 data URLs in
the `chat.completions.create` content array. Llama-4-Scout supports up
to 5 images per request but quality drops noticeably past 3; we cap at
3 per call by default.
"""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

# Imported lazily inside _annotate_async so users without GROQ_API_KEY
# don't pay the SDK import cost. Tests patch
# `skills.neurolearn.vision.groq_vision._import_groq` to inject a mock.
from skills.neurolearn.backends.vision_base import VisualSegment
from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision.frames import (
    extract_keyframes,
    extract_keyframes_asymmetric,
)
from skills.neurolearn.vision.prompts import format_prompt

_VISION_CALL_TIMEOUT_S = 120  # seconds — guard a hung vision API call


def _import_groq():
    """Lazy import wrapper — tests patch this to inject a fake SDK."""
    from groq import Groq
    return Groq


# JSON schema Llama-4-Scout MUST follow. Same field set as
# vision/gemini.py's _SEGMENT_SCHEMA so downstream code (output_writer,
# claude-mode manifest.json reader) is identical regardless of backend.
_SEGMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "description": {
            "type": "string",
            "description": "Concise factual description (≤30 words).",
        },
        "key_objects": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Named UI labels / objects extracted verbatim.",
        },
        "importance": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "needs_refinement": {"type": "boolean"},
    },
    "required": [
        "description", "key_objects", "importance",
        "confidence", "needs_refinement",
    ],
}


# Groq free-tier rate limits for Llama-4-Scout (verified May 2026):
# 30 RPM, 1000 RPD, 30k TPM. We cap concurrent in-flight at 5 by
# default (well under 30 RPM with retries).
_DEFAULT_MAX_CONCURRENT = 5

# Llama-4-Scout reliability drops past 3 images per request. Vision
# research at qa-out/v0.12.0-vision-compare/REPORT_V2.md showed
# descriptions on the 4th and 5th image get noticeably terser.
_MAX_IMAGES_PER_REQUEST = 3

# Default Groq vision model. Users can override via cfg.groq_vision_model
# or by passing model= directly. We pin a known-stable version here so
# Groq's silent rotation of model aliases doesn't break us.
_DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


@dataclass
class GroqTokenUsage:
    """Per-call billing summary from Groq's `usage` block."""
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class GroqVisionBackend:
    """Llama-4-Scout vision backend with structured JSON output."""

    api_key: str
    model: str = _DEFAULT_MODEL
    frames_per_window: int = 1   # Scout works best on 1 frame; bump for tutorials
    max_concurrent: int = _DEFAULT_MAX_CONCURRENT
    max_retries: int = 3
    # When True (driven by tutorial preset), pulls 3 asymmetric frames
    # (-1.5s / +0.3s / +2.0s relative to window center) and includes
    # them all in a single Scout call (capped at _MAX_IMAGES_PER_REQUEST).
    use_asymmetric_offsets: bool = False
    last_run_usage: list[GroqTokenUsage] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Public sync facade
    # ------------------------------------------------------------------

    def annotate_segments(
        self,
        video_path: Path,
        windows: list[DetectionWindow],
        prompt_template: str,
        language: str,
        video_id: str,
        out_dir: Path,
    ) -> list[VisualSegment]:
        """Sync entry point mirroring GeminiVisionBackend.annotate_segments."""
        self.last_run_usage = []
        if not windows:
            return []
        return asyncio.run(self._annotate_async(
            video_path=video_path,
            windows=windows,
            prompt_template=prompt_template,
            language=language,
            video_id=video_id,
            out_dir=out_dir,
        ))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _annotate_async(
        self,
        *,
        video_path: Path,
        windows: list[DetectionWindow],
        prompt_template: str,
        language: str,
        video_id: str,
        out_dir: Path,
    ) -> list[VisualSegment]:
        Groq = _import_groq()
        client = Groq(api_key=self.api_key)

        frames_dir = out_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Extract frames synchronously (ffmpeg-bound, not API-bound).
        per_window_keyframes: list[tuple[DetectionWindow, list[Path]]] = []
        for w in windows:
            try:
                keyframes = self._extract_frames_for_window(
                    video_path, w, frames_dir, video_id,
                )
            except Exception:
                continue
            if not keyframes:
                continue
            per_window_keyframes.append((w, keyframes))

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _run_one(w: DetectionWindow, keyframes: list[Path]):
            async with semaphore:
                return await self._annotate_window_async(
                    client=client,
                    window=w,
                    keyframes=keyframes,
                    prompt_template=prompt_template,
                    language=language,
                )

        tasks = [_run_one(w, k) for (w, k) in per_window_keyframes]
        raw_results = await asyncio.gather(*tasks, return_exceptions=False)

        # Each entry is (VisualSegment, GroqTokenUsage) or None.
        out_segments: list[VisualSegment] = []
        for entry in raw_results:
            if entry is None:
                continue
            segment, usage = entry
            out_segments.append(segment)
            if usage:
                self.last_run_usage.append(usage)
        return out_segments

    def _extract_frames_for_window(
        self,
        video_path: Path,
        window: DetectionWindow,
        frames_dir: Path,
        video_id: str,
    ) -> list[Path]:
        if self.use_asymmetric_offsets and getattr(window, "event_ts", None):
            return extract_keyframes_asymmetric(
                video_path=video_path,
                event_ts=window.event_ts,
                out_dir=frames_dir,
                video_id=video_id,
            )
        return extract_keyframes(
            video_path=video_path,
            start=window.start,
            end=window.end,
            count=self.frames_per_window,
            out_dir=frames_dir,
            video_id=video_id,
        )

    async def _annotate_window_async(
        self,
        *,
        client,
        window: DetectionWindow,
        keyframes: list[Path],
        prompt_template: str,
        language: str,
    ) -> tuple[VisualSegment, GroqTokenUsage] | None:
        user_prompt = format_prompt(
            prompt_template,
            language=language,
            transcript_snippet=(
                window.transcript_context
                or window.phrase
                or "(no transcript context for this moment)"
            ),
            start_sec=window.start,
            end_sec=window.end,
        )

        # Cap at _MAX_IMAGES_PER_REQUEST; Scout descriptions on 4th+
        # image are markedly worse.
        images_to_send = keyframes[:_MAX_IMAGES_PER_REQUEST]

        content_parts: list[dict] = [
            {"type": "text", "text": user_prompt},
        ]
        for frame_path in images_to_send:
            try:
                b64 = base64.b64encode(frame_path.read_bytes()).decode("ascii")
            except OSError:
                continue
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        # If all frames failed to read, skip this window.
        if len(content_parts) == 1:
            return None

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=self.model,
                    messages=[{"role": "user", "content": content_parts}],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "vision_segment",
                            "schema": _SEGMENT_SCHEMA,
                            "strict": True,
                        },
                    },
                    max_tokens=400,
                    temperature=0.2,
                    timeout=_VISION_CALL_TIMEOUT_S,
                )
                break
            except Exception as e:  # noqa: BLE001 — Groq SDK exception types vary
                last_exc = e
                if attempt + 1 >= self.max_retries:
                    return None
                # Exponential backoff: 3s, 6s, 12s. We don't parse the
                # Retry-After header — Groq's free tier rarely sends it
                # in a machine-readable shape across SDK versions.
                await asyncio.sleep(3.0 * (2 ** attempt))
        else:
            return None

        # Parse structured response.
        raw_text = ""
        try:
            raw_text = response.choices[0].message.content or ""
        except (AttributeError, IndexError):
            return None
        try:
            payload = json.loads(raw_text.strip())
        except json.JSONDecodeError:
            return None

        usage = GroqTokenUsage(
            prompt_tokens=int(getattr(response.usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(response.usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(response.usage, "total_tokens", 0) or 0),
        )

        segment = VisualSegment(
            start=window.start,
            end=window.end,
            description=str(payload.get("description", "")),
            keyframes=[str(p.name) for p in images_to_send],
            detected_objects=list(payload.get("key_objects", []) or []),
            trigger_reason=window.phrase or "",
            importance=payload.get("importance", "medium"),
            confidence=float(payload.get("confidence", 1.0)),
            needs_refinement=bool(payload.get("needs_refinement", False)),
        )
        return segment, usage
