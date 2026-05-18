"""Gemini backend — Google AI Studio (google-genai 2.x).

Accepts either a local audio file (uploaded via the Files API) or a
public YouTube URL passed directly as `file_uri`. The URL path skips
the local download + upload roundtrip entirely — Gemini fetches the
video on its side.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from skills.neurolearn.backends.base import (
    BackendError,
    BackendNotConfigured,
    TranscriptionResult,
)
from skills.neurolearn.config import get_api_key
from skills.neurolearn.utils.downloader import is_url, is_youtube_url
from skills.neurolearn.utils.output_writer import Segment


_PROMPT = """\
Transcribe this audio precisely. Return ONLY valid JSON in this exact shape:
{
  "language": "<2-letter ISO code or 'unknown'>",
  "segments": [
    {"start": <seconds, float>, "end": <seconds, float>, "text": "<utterance>"},
    ...
  ]
}
Use precise timestamps. Do not add commentary, do not wrap in markdown fences."""


def _build_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def _extract_json(text: str) -> dict:
    """Strip optional markdown fences and return the first top-level JSON
    object. Gemini occasionally streams the same outline twice (or appends
    a brief explanation after the JSON); `json.JSONDecoder.raw_decode`
    parses up to the end of the first valid object and ignores trailing
    data — that's exactly what we want here."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    # Skip any leading non-JSON preamble — find the first `{`.
    brace = cleaned.find("{")
    if brace > 0:
        cleaned = cleaned[brace:]
    obj, _ = json.JSONDecoder().raw_decode(cleaned)
    if not isinstance(obj, dict):
        raise json.JSONDecodeError(
            f"Expected JSON object, got {type(obj).__name__}", cleaned, 0,
        )
    return obj


def _build_youtube_part(url: str):
    """Wrap a YouTube URL in a genai Part suitable for generate_content.

    Per the Gemini video-understanding docs, `Part.from_uri` with a
    `youtube.com` / `youtu.be` URL makes the model fetch the video
    server-side — no download or upload from our side. Free-tier
    accounts are capped at 8 hours/day; the model 429s past that.
    """
    from google.genai import types
    return types.Part.from_uri(file_uri=url, mime_type="video/*")


@dataclass
class GeminiBackend:
    name: str = field(default="gemini", init=False)
    # v0.10.3: True because YouTube URLs are accepted natively. Non-YouTube
    # URLs still error with a clear hint — the caller (smart composer)
    # is responsible for downloading those first.
    supports_url: bool = field(default=True, init=False)
    supports_local_file: bool = field(default=True, init=False)

    model: str = "gemini-2.5-flash"
    language_hint: str = "auto"

    def is_configured(self) -> tuple[bool, str | None]:
        key = get_api_key("gemini")
        if not key:
            return False, (
                "GEMINI_API_KEY is not set. Get a key at https://aistudio.google.com/apikey "
                "and register it via `neurolearn config set-key gemini`."
            )
        return True, None

    def transcribe(
        self,
        audio_or_url: str | Path,
        *,
        language: str = "auto",
        **opts,
    ) -> TranscriptionResult:
        src = str(audio_or_url)

        # YouTube URLs go through file_uri (no download on our side).
        if is_youtube_url(src):
            return self._transcribe_youtube_url(src)

        # Any other URL: Gemini can't fetch it. Be explicit so the smart
        # composer (or the user) knows to download audio first.
        if is_url(src):
            raise BackendError(
                "Gemini backend only accepts YouTube URLs directly. "
                f"For other URLs (Instagram, TikTok, etc.) the caller must "
                f"download the audio first. Got: {src}"
            )

        # Local file path — upload to Files API, then transcribe.
        audio = Path(audio_or_url)
        if not audio.exists():
            raise BackendError(f"Audio file not found: {audio}")
        return self._transcribe_local_file(audio)

    # ------------------------------------------------------------------ paths

    def _transcribe_youtube_url(self, url: str) -> TranscriptionResult:
        api_key = get_api_key("gemini")
        if not api_key:
            raise BackendNotConfigured("GEMINI_API_KEY missing.")
        client = _build_client(api_key)
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=[_PROMPT, _build_youtube_part(url)],
            )
        except Exception as e:
            raise BackendError(f"Gemini API error (YouTube URL): {e}") from e
        return self._parse_response(response)

    def _transcribe_local_file(self, audio: Path) -> TranscriptionResult:
        api_key = get_api_key("gemini")
        if not api_key:
            raise BackendNotConfigured("GEMINI_API_KEY missing.")
        client = _build_client(api_key)
        try:
            uploaded = client.files.upload(file=str(audio))
            response = client.models.generate_content(
                model=self.model,
                contents=[_PROMPT, uploaded],
            )
        except Exception as e:
            raise BackendError(f"Gemini API error: {e}") from e
        return self._parse_response(response)

    # ------------------------------------------------------------------ parse

    def _parse_response(self, response) -> TranscriptionResult:
        raw_text = getattr(response, "text", "") or ""
        try:
            data = _extract_json(raw_text)
        except json.JSONDecodeError as e:
            raise BackendError(
                f"Gemini returned a non-JSON response. Try another backend or retry. "
                f"Error: {e}"
            ) from e

        segments: list[Segment] = []
        for s in data.get("segments", []):
            segments.append(Segment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=str(s.get("text", "")).strip(),
            ))

        text = " ".join(s.text for s in segments)
        return TranscriptionResult(
            text=text,
            segments=segments,
            language_detected=data.get("language"),
            backend_name=self.name,
            duration_seconds=segments[-1].end if segments else 0.0,
        )
