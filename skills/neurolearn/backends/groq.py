"""Groq backend — Whisper API on LPU hardware."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skills.neurolearn.backends.base import (
    BackendError,
    BackendNotConfigured,
    TranscriptionResult,
)
from skills.neurolearn.config import get_api_key
from skills.neurolearn.utils.output_writer import Segment

# v0.14.1: Groq audio upload limits per tier. Source:
# https://console.groq.com/docs/audio (May 2026).
#   Free tier:  25 MB hard limit. ~15-17 min of typical 192k m4a.
#   Paid tier:  100 MB. ~60-70 min of the same.
# We leave a 1 MB buffer below the wire limit to account for HTTP
# multipart overhead.
_GROQ_AUDIO_LIMIT_BYTES = {
    "free": 25 * 1024 * 1024 - 1_000_000,        # ~24 MB usable
    "paid": 100 * 1024 * 1024 - 2_000_000,       # ~98 MB usable
    "paid-tier2": 100 * 1024 * 1024 - 2_000_000,
    "paid-tier3": 100 * 1024 * 1024 - 2_000_000,
}

# Whisper internally works at 16 kHz mono. Anything higher is wasted
# bandwidth. v0.14.1 switched from AAC 32k to Opus 24k mono: same
# transcription accuracy, ~30% smaller payload. Math: Opus 24k mono
# ≈ 11 MB/hour, so ~2h15m fits the 25 MB free-tier cap before
# chunking kicks in (was ~1h45m on AAC 32k). Opus in OGG container
# is on Groq's accepted-formats list.
_RECOMPRESS_SAMPLE_RATE = 16_000
_RECOMPRESS_CHANNELS = 1
_RECOMPRESS_BITRATE = "24k"
_RECOMPRESS_CODEC = "libopus"
_RECOMPRESS_EXT = ".ogg"


def _build_client(api_key: str):
    from groq import Groq
    return Groq(api_key=api_key)


def _groq_size_limit_for_tier(tier: str | None) -> int:
    """Return the upload-byte limit for the configured Groq tier.

    Unknown tier strings (typos, future tiers) fall back to the
    conservative free-tier ceiling so we never silently send a
    payload that 4xx's on the wire."""
    return _GROQ_AUDIO_LIMIT_BYTES.get(tier or "free", _GROQ_AUDIO_LIMIT_BYTES["free"])


def _recompress_audio_for_groq(src: Path, dst: Path) -> None:
    """Re-encode `src` to mono 16 kHz Opus at 24 kbps in `dst`.

    Raises BackendError if ffmpeg is missing or the conversion fails —
    callers (transcribe → smart cascade) catch BackendError and fall
    through to the next backend (whisper-local), so a recompress
    failure doesn't break the user's run.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise BackendError(
            "ffmpeg is not on PATH; cannot recompress audio under Groq's "
            "25 MB upload limit. Install ffmpeg (brew/apt/choco) and retry, "
            "or pass `--backend whisper-local` for offline transcription."
        )
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-ac", str(_RECOMPRESS_CHANNELS),
        "-ar", str(_RECOMPRESS_SAMPLE_RATE),
        "-c:a", _RECOMPRESS_CODEC,
        "-b:a", _RECOMPRESS_BITRATE,
        "-application", "voip",  # Opus speech-tuned mode
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # ffmpeg's stderr is the most useful diagnostic — surface a
        # short tail so the user can see codec errors etc.
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise BackendError(
            "ffmpeg failed while compressing audio for Groq upload. "
            f"Tail: {' | '.join(tail) or '(no stderr)'}"
        )


@dataclass
class GroqBackend:
    name: str = field(default="groq", init=False)
    supports_url: bool = field(default=False, init=False)
    supports_local_file: bool = field(default=True, init=False)

    model: str = "whisper-large-v3-turbo"
    # v0.14.1: cfg passes its `groq_tier` here so we can pick the right
    # upload limit (free 25 MB, paid 100 MB). Defaults to "free" so the
    # conservative cap always applies when not wired explicitly.
    tier: str = "free"

    def is_configured(self) -> tuple[bool, str | None]:
        if not get_api_key("groq"):
            return False, (
                "GROQ_API_KEY is not set. Get one at https://console.groq.com/keys "
                "and register via `neurolearn config set-key groq`."
            )
        return True, None

    def transcribe(
        self,
        audio_or_url: str | Path,
        *,
        language: str = "auto",
        **opts,
    ) -> TranscriptionResult:
        audio = Path(audio_or_url)
        if not audio.exists():
            raise BackendError(f"Audio file not found: {audio}")

        key = get_api_key("groq")
        if not key:
            raise BackendNotConfigured("GROQ_API_KEY missing.")

        # v0.14.1: prepare upload payload. May be:
        #   - the original file (already small enough)
        #   - a single Opus-recompressed temp file
        #   - multiple chunked Opus files when even recompression
        #     doesn't fit the tier's upload limit (transparent to
        #     the user; works in Claude Code chat without TTY).
        uploads, tmp_recompress = self._prepare_uploads(audio)

        client = _build_client(key)
        lang = None if language == "auto" else language

        merged_text_parts: list[str] = []
        merged_segments: list[Segment] = []
        detected_lang: str | None = None
        total_duration = 0.0

        # v0.15.1: collect every trim-tmp we create so cleanup catches them
        trim_tmp_paths: list[Path] = []

        try:
            for idx, (chunk_path, offset) in enumerate(uploads, start=1):
                # v0.15.1: silence-trim leading + trailing edges of each
                # chunk BEFORE upload. Whisper hallucinates on silence;
                # removing the trigger at the input is more reliable than
                # filtering invented text on the output. The leading-trim
                # amount is added back to every segment timestamp so the
                # final timeline still matches the original audio.
                try:
                    from skills.neurolearn.utils.audio_chunker import trim_silence_edges
                    upload_path, trim_offset = trim_silence_edges(
                        chunk_path, chunk_path.parent,
                    )
                except Exception as trim_err:
                    sys.stderr.write(
                        f"[neurolearn] silence-trim failed for chunk {idx} "
                        f"({trim_err}); uploading untrimmed.\n"
                    )
                    upload_path, trim_offset = chunk_path, 0.0
                if upload_path != chunk_path:
                    trim_tmp_paths.append(upload_path)
                    sys.stderr.write(
                        f"[neurolearn] Trimmed {trim_offset:.1f}s of leading "
                        f"silence from chunk {idx} before upload.\n"
                    )

                if len(uploads) > 1:
                    sys.stderr.write(
                        f"[neurolearn] Uploading chunk {idx}/{len(uploads)} "
                        f"({upload_path.stat().st_size / 1024 / 1024:.1f} MB, "
                        f"offset {offset:.1f}s)…\n"
                    )
                try:
                    with upload_path.open("rb") as f:
                        resp = client.audio.transcriptions.create(
                            file=(upload_path.name, f.read()),
                            model=self.model,
                            language=lang,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"],
                        )
                except Exception as e:
                    raise BackendError(f"Groq API error: {e}") from e

                merged_text_parts.append((getattr(resp, "text", "") or "").strip())
                if detected_lang is None:
                    detected_lang = getattr(resp, "language", None)
                total_duration += float(getattr(resp, "duration", 0.0) or 0.0)

                for s in getattr(resp, "segments", None) or []:
                    s_start = float(s.get("start", 0.0)) if isinstance(s, dict) else float(s.start)
                    s_end = float(s.get("end", 0.0)) if isinstance(s, dict) else float(s.end)
                    s_text = (s.get("text") if isinstance(s, dict) else s.text) or ""
                    # Final timestamp = whisper_relative + chunk_start + leading_trim
                    final_offset = offset + trim_offset
                    merged_segments.append(Segment(
                        start=s_start + final_offset,
                        end=s_end + final_offset,
                        text=s_text.strip(),
                    ))
        finally:
            self._cleanup_uploads(uploads, audio, tmp_recompress)
            for trim_tmp in trim_tmp_paths:
                try:
                    if trim_tmp.exists():
                        trim_tmp.unlink()
                except OSError:
                    pass

        # v0.14.2: drop Whisper hallucinations on trailing silence
        # ("Продолжение следует..." spanning 30s, "Subscribe to my
        # channel" filler on tail-of-credits, etc.). Filter runs on
        # the reassembled timeline so it sees the full picture.
        from skills.neurolearn.utils.hallucination_filter import filter_hallucinations
        merged_segments, dropped = filter_hallucinations(merged_segments)
        if dropped:
            sys.stderr.write(
                f"[neurolearn] Dropped {len(dropped)} hallucinated "
                f"segment(s) (silence-fill / known-filler).\n"
            )

        # Re-derive joined text from filtered segments so the .txt
        # output stays consistent with the .srt.
        filtered_text = " ".join(s.text for s in merged_segments if s.text).strip()

        return TranscriptionResult(
            text=filtered_text or " ".join(t for t in merged_text_parts if t).strip(),
            segments=merged_segments,
            language_detected=detected_lang,
            backend_name=self.name,
            duration_seconds=total_duration,
        )

    # ------------------------------------------------------------------
    # v0.14.1: size handling — recompress → chunk → upload list
    # ------------------------------------------------------------------

    def _prepare_uploads(
        self, audio: Path
    ) -> tuple[list[tuple[Path, float]], Path | None]:
        """Return (uploads, recompress_tmp).

        `uploads` is `[(path, start_offset_sec), ...]` — at least one
        entry, always under the tier limit.

        `recompress_tmp` is the Opus-recompressed temp file (or None
        if we uploaded the original). Tracked separately so chunk
        cleanup can delete it after we're done iterating chunks.
        """
        from skills.neurolearn.utils import audio_chunker

        limit = _groq_size_limit_for_tier(self.tier)
        size = audio.stat().st_size
        if size <= limit:
            return [(audio, 0.0)], None

        mb = size / (1024 * 1024)
        limit_mb = limit / (1024 * 1024)
        sys.stderr.write(
            f"[neurolearn] Audio file is {mb:.1f} MB — over Groq's "
            f"{limit_mb:.0f} MB {self.tier}-tier upload limit. "
            f"Re-encoding to Opus 24 kbps mono (Whisper uses 16 kHz "
            f"mono internally, so this is lossless to transcription "
            f"quality).\n"
        )

        tmp = Path(tempfile.gettempdir()) / f"{audio.stem}_groq_compress{_RECOMPRESS_EXT}"
        try:
            _recompress_audio_for_groq(audio, tmp)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

        new_size = tmp.stat().st_size
        sys.stderr.write(
            f"[neurolearn] Recompressed to {new_size / (1024 * 1024):.1f} MB.\n"
        )

        if new_size <= limit:
            return [(tmp, 0.0)], tmp

        # Still too large — chunk the recompressed file at silence
        # boundaries. Each chunk gets its own upload + segment offset.
        chunks = audio_chunker.prepare_chunks(tmp, limit)
        return chunks, tmp

    def _cleanup_uploads(
        self,
        uploads: list[tuple[Path, float]],
        original: Path,
        recompress_tmp: Path | None,
    ) -> None:
        """Delete every temp file we created — keep the user's
        original input untouched."""
        for path, _ in uploads:
            if path == original or path == recompress_tmp:
                continue
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        if recompress_tmp is not None and recompress_tmp.exists():
            try:
                recompress_tmp.unlink()
            except OSError:
                pass
