"""GeminiVisionBackend — multimodal annotation via Gemini File API.

v0.10 optimization wave (see docs/tutorial-pipeline guidance):
  • MEDIA_RESOLUTION_LOW (66 tok/sec vs 258) — 4× video-token savings.
    UI tutorials still legible; high-detail content not affected.
  • response_schema enforcement — Gemini cannot return invalid JSON,
    parser never crashes on a stray fence or missing field.
  • temperature=0.2 + max_output_tokens=300 — determinism, capped cost.
  • Async parallelism (Semaphore(10)) — N windows processed concurrently
    instead of sequentially.
  • Prompt caching (CreateCachedContentConfig) — system prompt cached once
    per video; subsequent windows reuse it (~75% input-token savings).
  • Per-segment confidence + needs_refinement signals so the orchestrator
    can route low-confidence outputs to Claude refinement.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from skills.neurolearn.backends.vision_base import VisionBackend, VisualSegment
from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision import frames as frames_mod
from skills.neurolearn.vision.prompts import format_prompt

_VISION_CALL_TIMEOUT_S = 120  # seconds — guard a hung vision API call


# JSON schema Gemini MUST follow. response_mime_type=application/json plus
# this schema makes the model emit a structured object every time.
_SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Concise description of what's happening visually (≤300 chars).",
        },
        "key_objects": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Names of UI elements / objects in focus.",
        },
        "importance": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": (
                "1.0 = transcript and frames unambiguously confirm the action; "
                "0.5 = some doubt remains about which element/state; "
                "0.0 = action not visible. Drives Claude refinement."
            ),
        },
        "needs_refinement": {
            "type": "boolean",
            "description": (
                "True when the frame contains small text or similar-looking "
                "elements you couldn't read precisely. Triggers Claude refinement."
            ),
        },
        "box_2d": {
            "type": "array",
            "items": {"type": "integer"},
            "description": (
                "Bounding box of the single most relevant on-screen region a "
                "reader should look at (the tooltip / panel / dialog being "
                "shown), so the screenshot can be cropped to it. Normalized "
                "0-1000 as [ymin, xmin, ymax, xmax]. If the whole frame is "
                "relevant, return [0,0,1000,1000]."
            ),
        },
    },
    "required": [
        "description", "key_objects", "importance",
        "confidence", "needs_refinement", "box_2d",
    ],
}


# Concurrency caps per Gemini tier. The actual API limits are higher,
# but a conservative cap leaves room for retries inside the same minute.
# v0.11.0: free tier raised from 3 to 6. Gemini 2.5-flash free tier is
# 10 RPM (Google raised it from 5 in 2026-Q1). 6 concurrent calls @ ~2 s
# each averages ~7 RPM, leaving room for retries. Saves ~8-12 s on a
# 20-window video without risking 429s.
_TIER_CONCURRENCY: dict[str, int] = {
    "free": 6,
    "paid": 10,
    "paid-tier2": 20,
    "paid-tier3": 50,
}


def concurrency_for_tier(tier: str) -> int:
    """Pick a sensible max_concurrent for the given Gemini tier. Unknown
    tier strings fall back to the safe `free` floor."""
    return _TIER_CONCURRENCY.get(tier, _TIER_CONCURRENCY["free"])


@dataclass
class TokenUsage:
    """Per-call billing summary.

    Populated from Gemini SDK's `usage_metadata`. Aggregated by the caller
    into BudgetTracker (skills/neurolearn/budget.py).
    """
    prompt_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0     # contribution of cached content (subtract from prompt for cost)
    total_tokens: int = 0


@dataclass
class GeminiVisionBackend:
    api_key: str
    model: str = "gemini-2.5-flash"
    frames_per_window: int = 3
    max_retries: int = 3
    # Concurrency floor — tuned per Gemini tier. v0.11.0: free-tier
    # 2.5-flash RPM was raised by Google from 5 to 10. We keep this
    # default in sync with _TIER_CONCURRENCY["free"] above (6, which
    # averages ~7 RPM with retries and stays under the cap).
    # Paid Tier 1 gets 1000 RPM → 10 is safe and fast.
    # Callers override via gemini_tier (config) or this kwarg directly.
    max_concurrent: int = 6
    # When True (driven by tutorial preset / asymmetric frame mode), the
    # caller passes `event_ts` so we can take frames at offsets
    # `-1.5s / +0.3s / +2.0s` instead of evenly spaced through the window.
    use_asymmetric_offsets: bool = False
    # Populated by annotate_segments — read by orchestrator into the
    # BudgetTracker. Initialised empty; one TokenUsage per window.
    last_run_usage: list[TokenUsage] = field(default_factory=list)

    def annotate_segments(
        self,
        video_path: Path,
        windows: list[DetectionWindow],
        prompt_template: str,
        language: str,
        video_id: str,
        out_dir: Path,
    ) -> list[VisualSegment]:
        """Sync facade. Drives the async pipeline internally so callers
        don't need to be async (yet)."""
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
        client = genai.Client(api_key=self.api_key)
        # v0.21: send each window's extracted keyframe STILLS inline (see
        # _annotate_window_async) instead of uploading the whole video via the
        # Files API. Inline avoids the Files-API ACTIVE-state race (400
        # FAILED_PRECONDITION) and the long-video timestamp drift, is cheaper,
        # and matches the proven per-window pattern — timestamps come from our
        # transcript, never from Gemini. Implicit caching still applies to the
        # stable instruction prefix shared across windows.

        frames_dir = out_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Extract keyframes synchronously (ffmpeg-bound, not API-bound).
        # The expensive part is the LLM call — that's where we parallelise.
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
                    prompt_template=prompt_template,
                    language=language,
                    keyframes=keyframes,
                )

        results = await asyncio.gather(
            *[_run_one(w, kf) for w, kf in per_window_keyframes],
            return_exceptions=False,
        )
        return [r for r in results if r is not None]

    def _extract_frames_for_window(
        self,
        video_path: Path,
        window: DetectionWindow,
        frames_dir: Path,
        video_id: str,
    ) -> list[Path]:
        # v0.23: a procedure/craft moment (stepwise narration) gets denser
        # coverage — more frames spread across the window so each step is
        # captured — while a showcase keeps the compact bracket. Window span
        # has to be meaningful for this to help (the LLM moment-selector
        # returns the real time range for a procedure).
        from skills.neurolearn.detection.moment_kind import (
            classify_moment_kind, PROCEDURE,
        )
        if (
            classify_moment_kind(getattr(window, "transcript_context", "") or "")
            == PROCEDURE
            and (window.end - window.start) >= 6.0
        ):
            return frames_mod.extract_keyframes(
                video_path=video_path,
                start=window.start,
                end=window.end,
                count=max(self.frames_per_window, 5),
                out_dir=frames_dir,
                video_id=video_id,
            )
        if self.use_asymmetric_offsets:
            # Tutorial preset: speech-anchored offsets. window.start is
            # already `seg.start - 1.5`, so the speech event lands at
            # window.start + 1.5. Take frames at -1.5 / +0.3 / +2.0
            # relative to that event.
            event_ts = window.start + 1.5
            return frames_mod.extract_keyframes_asymmetric(
                video_path=video_path,
                event_ts=event_ts,
                out_dir=frames_dir,
                video_id=video_id,
            )
        return frames_mod.extract_keyframes(
            video_path=video_path,
            start=window.start,
            end=window.end,
            count=self.frames_per_window,
            out_dir=frames_dir,
            video_id=video_id,
        )

    # v0.12.0: `_maybe_create_cache()` was REMOVED. Free-tier Gemini
    # accounts get TotalCachedContentStorageTokensPerModelFreeTier=0
    # so `client.caches.create()` always 4xx'd. Implicit caching now
    # handles this automatically.

    async def _annotate_window_async(
        self,
        *,
        client: genai.Client,
        window: DetectionWindow,
        prompt_template: str,
        language: str,
        keyframes: list[Path],
    ) -> VisualSegment | None:
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

        config = types.GenerateContentConfig(
            temperature=0.2,
            # v0.21: Gemini 2.5/3.x flash are *thinking* models — they spend
            # ~300-560 tokens reasoning before the JSON. We disable thinking
            # (describing a still needs none) so the whole budget goes to the
            # answer, and keep generous headroom so a deep-depth description
            # never truncates (a too-small cap → finish_reason=MAX_TOKENS and
            # only a "Here is the JSON:" preamble leaks out).
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=768,
            response_mime_type="application/json",
            response_schema=_SEGMENT_SCHEMA,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        )

        # v0.21: send the window's keyframe STILLS inline alongside the
        # prompt. The prompt already carries the transcript context and our
        # timestamps; Gemini only describes what's on screen. Inline bytes
        # sidestep the Files-API ACTIVE-state race entirely.
        contents: list = [user_prompt]
        for fp in keyframes[: self.frames_per_window]:
            try:
                contents.append(types.Part.from_bytes(
                    data=fp.read_bytes(), mime_type="image/jpeg",
                ))
            except OSError:
                continue
        if len(contents) == 1:
            # No frame readable — nothing to look at, skip this window.
            return None

        usage: TokenUsage | None = None
        # Default exponential backoff used when the server doesn't tell
        # us how long to wait. Gemini 429s include a `retryDelay` value
        # in seconds — we honor that when present (so we wake up right
        # after the per-minute quota window resets, not earlier and not
        # 31 seconds later).
        default_backoffs = [3.0, 6.0, 12.0]
        last_err: Exception | None = None
        response = None
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=_VISION_CALL_TIMEOUT_S,
                )
                usage = _extract_usage(response)
                break
            except Exception as e:
                last_err = e
                if attempt >= self.max_retries - 1:
                    break
                # Prefer the server-suggested retry delay (seconds).
                # Falls back to exponential backoff when we can't parse one.
                retry_delay = _parse_retry_delay_seconds(e)
                wait = retry_delay if retry_delay is not None else default_backoffs[attempt]
                # Cap wait at 60s so a single failed call doesn't stall
                # the whole pipeline.
                await asyncio.sleep(min(wait, 60.0))
        if response is None:
            # All retries failed — record a zero-cost usage entry so
            # downstream budget logging stays correct.
            self.last_run_usage.append(TokenUsage())
            return VisualSegment(
                start=window.start,
                end=window.end,
                description=f"(error: {last_err})",
                keyframes=[f"frames/{p.name}" for p in keyframes],
                detected_objects=[],
                trigger_reason=window.reason,
                importance="medium",
                confidence=0.0,
                needs_refinement=False,
            )

        if usage is not None:
            self.last_run_usage.append(usage)

        desc, key_objects, importance, confidence, needs_refinement = (
            _parse_structured_response(response.text or "")
        )
        # v0.21: crop the keyframes to the region Gemini flagged (box_2d) so
        # the embedded screenshot shows the tooltip/panel, not the whole game
        # screen. Same call → no extra request. Falls back to full frames.
        kf_paths = _crop_keyframes_to_box(
            keyframes, _parse_box_2d(response.text or ""),
        )
        return VisualSegment(
            start=window.start,
            end=window.end,
            description=desc,
            keyframes=kf_paths,
            detected_objects=key_objects,
            trigger_reason=window.reason,
            importance=importance,
            confidence=confidence,
            needs_refinement=needs_refinement,
        )


def _extract_usage(response) -> TokenUsage:
    """Pull token counts from a Gemini response. Resilient to SDK shape changes."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return TokenUsage()
    prompt = int(getattr(meta, "prompt_token_count", 0) or 0)
    out = int(getattr(meta, "candidates_token_count", 0) or 0)
    cached = int(getattr(meta, "cached_content_token_count", 0) or 0)
    total = int(getattr(meta, "total_token_count", 0) or 0)
    return TokenUsage(
        prompt_tokens=prompt,
        output_tokens=out,
        cached_tokens=cached,
        total_tokens=total,
    )


def _parse_structured_response(
    text: str,
) -> tuple[str, list[str], str, float, bool]:
    """Parse the JSON Gemini returned. Schema-enforced so we expect a
    valid object, but be defensive — log + fall back to text if shape
    drifted between SDK versions."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.split("\n") if not line.startswith("```"))
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, [], "medium", 0.5, False

    description = str(data.get("description", text))[:2000]
    raw_objects = data.get("key_objects", [])
    key_objects = [str(o) for o in raw_objects] if isinstance(raw_objects, list) else []

    importance = data.get("importance", "medium")
    if importance not in ("low", "medium", "high"):
        importance = "medium"

    try:
        confidence = float(data.get("confidence", 1.0))
    except (TypeError, ValueError):
        confidence = 1.0
    confidence = max(0.0, min(1.0, confidence))

    needs_refinement = bool(data.get("needs_refinement", False))
    return description, key_objects, importance, confidence, needs_refinement


def _parse_box_2d(text: str) -> tuple[int, int, int, int] | None:
    """Pull the optional `box_2d` ([ymin,xmin,ymax,xmax], 0-1000) from Gemini's
    JSON. Returns None when absent or malformed."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = "\n".join(ln for ln in text.split("\n") if not ln.startswith("```"))
    try:
        box = json.loads(text).get("box_2d")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        ymin, xmin, ymax, xmax = (int(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        return None
    return (ymin, xmin, ymax, xmax)


def _crop_keyframes_to_box(
    keyframes: list[Path], box: tuple[int, int, int, int] | None,
) -> list[str]:
    """Crop each keyframe to `box` and return the cropped relative paths. A
    near-full-frame box (≥90% each side) or any failure leaves the frame
    uncropped — cropping a whole-screen moment gains nothing."""
    rel = [f"frames/{p.name}" for p in keyframes]
    if box is None:
        return rel
    ymin, xmin, ymax, xmax = box
    if (xmax - xmin) >= 900 and (ymax - ymin) >= 900:
        return rel
    from skills.neurolearn.frames_cmd import crop_image
    out: list[str] = []
    for p in keyframes:
        try:
            out.append(f"frames/{crop_image(p, box).name}")
        except Exception:
            out.append(f"frames/{p.name}")
    return out


def _parse_retry_delay_seconds(exc: Exception) -> float | None:
    """Pull a `retryDelay` (seconds) out of a Gemini 429 exception.

    Gemini's RESOURCE_EXHAUSTED responses embed a Google `RetryInfo`
    detail with a string like `"retryDelay": "31s"`. Honoring it makes
    retries land right after the per-minute quota resets, instead of
    sleeping the default backoff and missing the window.

    Returns the delay in seconds, or None when the exception doesn't
    carry one (e.g. transient network failure, server-side timeout).
    """
    import re
    text = str(exc)
    if "429" not in text and "RESOURCE_EXHAUSTED" not in text:
        return None
    # Format observed in production: "retryDelay": "31s" or 'retryDelay': '31s'
    match = re.search(
        r"retry[_-]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
        text,
        re.IGNORECASE,
    )
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None
