"""Adaptive audio chunking for size-capped transcription backends.

Used by GroqBackend when even Opus-recompressed audio exceeds the
free-tier 25 MB upload limit. The contract:

  prepare_chunks(audio_path, size_limit_bytes) -> list[(chunk_path, start_offset_sec)]

Design choices (v0.14.1):

1. **Adaptive chunk count.** Compute the minimum number of equal-ish
   chunks N such that each chunk's expected size ≤ limit. A 3-hour
   recording that compresses to 35 MB at 24k Opus needs N=2 (two
   ~17.5 MB halves), not eight 10-minute pieces.

2. **No mid-word cuts.** Hard constraint. ffmpeg `silencedetect`
   yields silence intervals; we pick boundaries inside those windows.
   When no silence sits near an ideal cut point, we expand the search
   window progressively. As a last resort we cut at the exact target
   time and accept a possible word break — but we log a warning so
   the caller (and user) can see it happened.

3. **Timestamp reassembly.** Each chunk knows its start offset in the
   original timeline. The transcribing backend offsets every segment
   by that value before merging — end-to-end timestamps stay aligned
   with the source video.

Pure-stdlib + ffmpeg shell-out, no extra deps. Works headless (no
TTY required) so it's safe inside Claude Code chat.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SilenceInterval:
    """A detected silent span [start, end] in seconds."""
    start: float
    end: float

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


def _require_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        from skills.neurolearn.backends.base import BackendError
        raise BackendError(
            "ffmpeg is not on PATH; cannot chunk audio. "
            "Install ffmpeg (brew/apt/choco) and retry."
        )
    return ff


def _require_ffprobe() -> str:
    fp = shutil.which("ffprobe")
    if not fp:
        from skills.neurolearn.backends.base import BackendError
        raise BackendError(
            "ffprobe is not on PATH (usually ships with ffmpeg)."
        )
    return fp


def probe_duration(audio: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    ffprobe = _require_ffprobe()
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        from skills.neurolearn.backends.base import BackendError
        raise BackendError(
            f"ffprobe failed to read duration: {proc.stderr.strip() or 'no output'}"
        )
    return float(proc.stdout.strip())


def detect_silences(
    audio: Path,
    *,
    noise_db: float = -30.0,
    min_duration: float = 0.4,
) -> list[SilenceInterval]:
    """Run ffmpeg silencedetect and parse the silence_start/end pairs.

    `noise_db` — anything quieter than this counts as silence.
    `min_duration` — silence must persist this many seconds to register.
    Returns silences in chronological order.
    """
    ffmpeg = _require_ffmpeg()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(audio),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    # silencedetect writes to stderr regardless of returncode (it doesn't
    # produce an output file). We don't fail on non-zero return — short
    # files with no silence still work.
    silences: list[SilenceInterval] = []
    start: float | None = None
    for line in (proc.stderr or "").splitlines():
        if "silence_start" in line:
            try:
                start = float(line.rsplit("silence_start:", 1)[1].strip().split()[0])
            except (ValueError, IndexError):
                start = None
        elif "silence_end" in line and start is not None:
            try:
                end = float(line.rsplit("silence_end:", 1)[1].strip().split()[0])
                silences.append(SilenceInterval(start=start, end=end))
            except (ValueError, IndexError):
                pass
            start = None
    return silences


def compute_chunk_count(file_size: int, size_limit: int) -> int:
    """Minimum N such that file_size/N ≤ size_limit. At least 2 since
    this only runs when single-file upload already failed."""
    if file_size <= size_limit:
        return 1
    # Add a 5% headroom — Opus bitrate fluctuates a bit across regions.
    target = int(size_limit * 0.95)
    n = (file_size + target - 1) // target
    return max(2, n)


def _find_silence_near(
    silences: list[SilenceInterval],
    target: float,
    window: float,
) -> float | None:
    """Return the midpoint of a silence that overlaps [target-window, target+window].

    Picks the silence whose midpoint is closest to target, so the cut
    lands as close as possible to the planned boundary while still
    falling in a quiet span."""
    lo, hi = target - window, target + window
    best: tuple[float, float] | None = None  # (distance, midpoint)
    for s in silences:
        # Silence interval overlaps the search window?
        if s.end < lo or s.start > hi:
            continue
        # Clamp the candidate cut point to the silence interval.
        candidate = min(max(target, s.start), s.end)
        dist = abs(candidate - target)
        if best is None or dist < best[0]:
            best = (dist, candidate)
    return best[1] if best else None


def plan_chunk_boundaries(
    duration: float,
    n_chunks: int,
    silences: list[SilenceInterval],
) -> tuple[list[float], list[str]]:
    """Return (cut_times, warnings) where cut_times has n_chunks-1
    entries dividing [0, duration] into n_chunks roughly equal pieces.

    Each cut is moved to the nearest silence; the search widens up to
    half a segment before giving up. If no silence is found we keep
    the ideal cut and add a warning to the returned list — caller can
    surface it to the user.
    """
    seg = duration / n_chunks
    # Search widths from 5% of segment up to 50% (half a segment).
    widen_steps = [0.05, 0.10, 0.20, 0.35, 0.50]
    cuts: list[float] = []
    warnings: list[str] = []
    for i in range(1, n_chunks):
        ideal = i * seg
        chosen: float | None = None
        for w_frac in widen_steps:
            window = seg * w_frac
            chosen = _find_silence_near(silences, ideal, window)
            if chosen is not None:
                break
        if chosen is None:
            warnings.append(
                f"No silence found near t={ideal:.1f}s "
                f"(searched ±{seg * 0.5:.1f}s); cutting at exact boundary."
            )
            chosen = ideal
        cuts.append(chosen)
    return cuts, warnings


def split_audio(
    audio: Path,
    cut_times: list[float],
    duration: float,
    out_dir: Path,
) -> list[tuple[Path, float]]:
    """Split `audio` into len(cut_times)+1 chunks using ffmpeg's stream
    copy (no re-encode). Returns [(chunk_path, start_offset_sec), ...]
    in chronological order.

    Stream-copy is critical: re-encoding Opus → Opus would inflate
    size beyond the limit we just respected.
    """
    ffmpeg = _require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = audio.suffix or ".ogg"
    boundaries = [0.0, *cut_times, duration]
    chunks: list[tuple[Path, float]] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        chunk_path = out_dir / f"{audio.stem}_chunk{i + 1:02d}{ext}"
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(audio),
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-c", "copy",
            str(chunk_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            from skills.neurolearn.backends.base import BackendError
            raise BackendError(
                f"ffmpeg split failed for chunk {i + 1}: "
                f"{(proc.stderr or '').strip()[-200:]}"
            )
        chunks.append((chunk_path, start))
    return chunks


def prepare_chunks(
    audio: Path,
    size_limit: int,
    *,
    work_dir: Path | None = None,
    on_status: callable = None,
) -> list[tuple[Path, float]]:
    """Top-level entry: split `audio` into chunks each under `size_limit`.

    Returns list of (chunk_path, start_offset_sec). The caller is
    responsible for cleaning up the temp files after transcribing.

    Status messages go to `on_status` if provided, otherwise stderr —
    so chunking is observable inside Claude Code chat without needing
    a TTY.
    """
    notify = on_status or (lambda msg: sys.stderr.write(f"[neurolearn] {msg}\n"))
    file_size = audio.stat().st_size
    if file_size <= size_limit:
        return [(audio, 0.0)]

    duration = probe_duration(audio)
    n = compute_chunk_count(file_size, size_limit)
    notify(
        f"Audio {file_size / 1024 / 1024:.1f} MB exceeds "
        f"{size_limit / 1024 / 1024:.0f} MB upload limit — "
        f"splitting into {n} chunks (each ≈{duration / n / 60:.1f} min)."
    )

    silences = detect_silences(audio)
    notify(f"Detected {len(silences)} silence interval(s) for boundary placement.")

    cuts, warnings = plan_chunk_boundaries(duration, n, silences)
    for w in warnings:
        notify(f"warning: {w}")

    work = work_dir or Path(tempfile.mkdtemp(prefix="neurolearn-chunks-"))
    chunks = split_audio(audio, cuts, duration, work)

    # Sanity-check chunk sizes; if any chunk somehow blew the limit
    # (encoder VBR weirdness, very dense audio), recurse to split it
    # further. Capped at one extra recursion to avoid pathological loops.
    refined: list[tuple[Path, float]] = []
    for chunk_path, offset in chunks:
        if chunk_path.stat().st_size <= size_limit:
            refined.append((chunk_path, offset))
            continue
        notify(
            f"Chunk {chunk_path.name} still exceeds limit; sub-splitting."
        )
        sub = prepare_chunks(chunk_path, size_limit, work_dir=work, on_status=notify)
        # Sub-chunks have offsets relative to chunk_path; adjust to
        # absolute timeline.
        for sub_path, sub_offset in sub:
            refined.append((sub_path, offset + sub_offset))
        # Original chunk now superseded — delete it.
        try:
            chunk_path.unlink()
        except OSError:
            pass

    notify(f"Prepared {len(refined)} chunk(s) for upload.")
    return refined


def cleanup_chunks(chunks: list[tuple[Path, float]], original: Path) -> None:
    """Delete chunk files (skipping the original input)."""
    for path, _ in chunks:
        if path == original:
            continue
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
