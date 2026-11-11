#!/usr/bin/env python3
"""Offline integrity checks and explicit, study-owned temporary-media cleanup."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MEDIA_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov", ".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".flac", ".jpg", ".jpeg", ".png", ".webp", ".part", ".ytdl"}
KINDS = {"video", "audio", "unused_frame", "download"}
COMPLETE = {"complete", "qualified_complete"}


class StudyError(ValueError):
    """The supplied study does not meet the requested operation's contract."""


def require(condition, message):
    if not condition:
        raise StudyError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def exclusive_owner(root):
    lock = root / ".study.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise StudyError("Another lifecycle operation owns .study.lock; inspect it before retrying") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        lock.unlink()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_path(root, relative, *, exists=True):
    require(isinstance(relative, str) and relative, "Expected a relative path")
    require(not any(c in relative for c in ("\\", ":", "\x00")), f"Unsafe path: {relative!r}")
    parts = relative.split("/")
    require(all(p not in {"", ".", ".."} for p in parts), f"Unsafe path: {relative!r}")
    path = root
    for part in parts:
        path = path / part
        require(not path.is_symlink(), f"Symlink is not allowed: {relative}")
        require(not path.is_junction() if hasattr(path, "is_junction") else True, f"Junction is not allowed: {relative}")
    require(path.resolve().is_relative_to(root), f"Path escapes study root: {relative}")
    if exists:
        require(path.exists() and stat.S_ISREG(path.stat().st_mode), f"Missing regular file: {relative}")
    return path


def document(root, relative):
    value = json.loads(safe_path(root, relative).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Expected JSON object: {relative}")
    return value


def sequence(value, label):
    require(isinstance(value, list), f"Expected list: {label}")
    return value


def fingerprint(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "Media is not a regular file")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "device": info.st_dev, "inode": info.st_ino, "links": info.st_nlink}


def load_study(root):
    root = Path(root).expanduser()
    require(not root.is_symlink(), "Study root cannot be a symlink")
    root = root.resolve()
    info = document(root, "study.json")
    require(info.get("schema_version") == 1 and info.get("platform") == "youtube", "Expected managed YouTube study schema v1")
    require(isinstance(info.get("study_id"), str) and info["study_id"], "Missing study_id")
    ids = sequence(info.get("selected_video_ids"), "selected_video_ids")
    require(all(isinstance(v, str) and VIDEO_ID.fullmatch(v) for v in ids), "Invalid selected video ID")
    require(len(ids) == len(set(ids)), "Duplicate selected video IDs")
    require(info.get("status") in COMPLETE | {"in_progress"}, "Invalid study status")
    sequence(info.get("active_jobs"), "active_jobs")
    sequence(info.get("retained_files"), "retained_files")
    return root, info


def init_study(root, channel_id, video_ids):
    root = Path(root).expanduser()
    require(isinstance(channel_id, str) and re.fullmatch(r"UC[A-Za-z0-9_-]+", channel_id), "Expected YouTube channel ID")
    require(all(VIDEO_ID.fullmatch(v) for v in video_ids) and len(video_ids) == len(set(video_ids)), "Invalid or duplicate video IDs")
    require(not root.exists() and not root.is_symlink(), "init requires a new, non-existing study root")
    root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    info = {"schema_version": 1, "study_id": str(uuid.uuid4()), "platform": "youtube",
            "channel_id": channel_id, "managed_root": str(root), "created_at": now(),
            "selected_video_ids": list(video_ids), "status": "in_progress", "active_jobs": [],
            "retained_files": [], "qualification_notes": []}
    atomic_json(root / "study.json", info)
    atomic_json(root / "media-ledger.json", {"study_id": info["study_id"], "files": []})
    return info


def checked_file(root, reference, retained):
    require(isinstance(reference, dict), "Expected file reference object")
    relative = reference.get("path")
    path = safe_path(root, relative)
    require(fingerprint(path)["sha256"] == reference.get("sha256"), f"Hash mismatch: {relative}")
    retained.add(relative)
    return path


def segment_range(value, segments):
    require(isinstance(value, dict), "Expected source interval object")
    first, last = value.get("first_segment"), value.get("last_segment")
    require(type(first) is int and type(last) is int and 0 <= first <= last < len(segments), "Invalid segment interval")
    return first, last


def time_range(start, end, limit=None):
    require(type(start) in {int, float} and type(end) in {int, float}, "Expected numeric timestamps")
    require(math.isfinite(start) and math.isfinite(end) and 0 <= start <= end, "Invalid timestamps")
    require(limit is None or end <= limit + 0.05, "Timestamp exceeds source duration")


def source_quote(evidence, segments):
    first, last = segment_range(evidence, segments)
    quote = evidence.get("quote")
    text = " ".join(s["text"] for s in segments[first:last + 1])
    require(isinstance(quote, str) and quote.strip() and quote in text, "Quote is absent from its declared source interval")
    if "start_s" in evidence or "end_s" in evidence:
        time_range(evidence.get("start_s"), evidence.get("end_s"))
        require(evidence["start_s"] >= segments[first]["start"] - 0.05 and evidence["end_s"] <= segments[last]["end"] + 0.05,
                "Evidence timestamps exceed declared segment range")
    return quote


def validate_video(root, info, video_id, retained):
    rel = f"videos/{video_id}/record.json"
    record = document(root, rel)
    retained.add(rel)
    require(record.get("video_id") == video_id, "Record video ID mismatch")
    require(record.get("kind") in {"video", "short", "stream"}, "Invalid publication kind")
    require(record.get("url") in {f"https://www.youtube.com/watch?v={video_id}", f"https://youtu.be/{video_id}"}, "Source URL video ID mismatch")
    status = record.get("status")
    require(status in {"pending", "analyzed", "unavailable", "failed"}, "Invalid source status")
    if status != "analyzed":
        if status in {"unavailable", "failed"}:
            require(isinstance(record.get("reason"), str) and record["reason"].strip(), "Missing source failure reason")
            require(info["status"] != "complete", "Missing source requires qualified_complete")
        require(status != "pending" or info["status"] == "in_progress", "Pending source prevents completion")
        return status, {}
    transcripts = sequence(record.get("transcripts"), "transcripts")
    require(transcripts, "Analyzed source needs a transcript")
    require(all(isinstance(t, dict) for t in transcripts), "Invalid transcript reference")
    paths = [t.get("path") for t in transcripts]
    require(len(paths) == len(set(paths)), "Duplicate transcript version paths")
    require(record.get("primary_transcript") in paths, "Primary transcript is not a retained version")
    primary = None
    primary_ref = None
    for ref in transcripts:
        transcript_path = checked_file(root, ref, retained)
        require(isinstance(ref.get("backend"), str) and ref["backend"], "Missing actual transcript backend")
        if ref["path"] == record["primary_transcript"]:
            primary, primary_ref = json.loads(transcript_path.read_text(encoding="utf-8")), ref
    require(isinstance(primary, dict), "Expected transcript JSON object")
    require(primary.get("backend") == primary_ref["backend"] and primary_ref["backend"] != "smart", "Declared backend must match actual transcript backend")
    segments = sequence(primary.get("segments"), "segments")
    require(segments, "Empty transcript cannot be analyzed")
    if primary.get("duration_sec") is not None:
        time_range(0, primary["duration_sec"])
    previous = -1
    for seg in segments:
        require(isinstance(seg, dict) and isinstance(seg.get("text"), str), "Invalid transcript segment")
        time_range(seg.get("start"), seg.get("end"), primary.get("duration_sec"))
        require(seg["start"] >= previous, "Transcript segments are out of order")
        previous = seg["start"]
    analysis_path = checked_file(root, record.get("analysis"), retained)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    require(isinstance(analysis, dict) and analysis.get("video_id") == video_id, "Analysis video ID mismatch")
    require(analysis.get("transcript_path") == primary_ref["path"] and analysis.get("transcript_sha256") == primary_ref["sha256"], "Analysis refers to another transcript version")
    review = analysis.get("review", {})
    require(isinstance(review, dict), "Expected source review object")
    if sequence(analysis.get("uncertainties", []), "uncertainties") or review.get("status") == "qualified":
        require(info["status"] != "complete", "Source limitations require qualified_complete")
    coverage = []
    for span in sequence(analysis.get("coverage"), "coverage"):
        first, last = segment_range(span, segments)
        coverage.extend(range(first, last + 1))
    require(sorted(coverage) == list(range(len(segments))), "Coverage must account for every segment exactly once")
    claims = {}
    for claim in sequence(analysis.get("claims"), "claims"):
        require(isinstance(claim, dict) and isinstance(claim.get("id"), str) and claim["id"] not in claims, "Invalid or duplicate claim ID")
        require(isinstance(claim.get("text"), str) and claim["text"].strip(), "Empty claim")
        evidence = sequence(claim.get("evidence"), "claim evidence")
        require(evidence, "Claim lacks evidence")
        claims[claim["id"]] = {"quotes": [source_quote(e, segments) for e in evidence], "requires_review": claim.get("requires_review", False)}
    review = analysis.get("review", {})
    require(isinstance(review, dict) and review.get("status") in {"passed", "qualified", "not_selected"}, "Missing source review outcome")
    checked = sequence(review.get("checked_claim_ids", []), "checked_claim_ids")
    require(set(checked) <= set(claims), "Review refers to unknown claim")
    required = {k for k, c in claims.items() if c["requires_review"]}
    require(required <= set(checked), "Required source claims lack review attestation")
    if review["status"] != "not_selected":
        require(isinstance(review.get("reviewer"), str) and review["reviewer"].strip(), "Missing source reviewer")
    else:
        require(not checked and not required, "Unselected review cannot attest checked claims")
    for span in sequence(review.get("sample_transcript_ranges", []), "sample_transcript_ranges"):
        segment_range(span, segments)
    visual_ids = set()
    for visual in sequence(analysis.get("visuals", []), "visuals"):
        require(isinstance(visual, dict) and visual.get("status") in {"pending", "sampled_frames", "continuous_clip", "unavailable"}, "Visual review is unfinished or invalid")
        require(isinstance(visual.get("id"), str) and visual["id"] and visual["id"] not in visual_ids, "Invalid or duplicate visual ID")
        visual_ids.add(visual["id"])
        require(visual["status"] != "pending" or info["status"] == "in_progress", "Pending visual prevents completion")
        time_range(visual.get("start_s"), visual.get("end_s"), primary.get("duration_sec"))
        if visual["status"] == "unavailable":
            require(isinstance(visual.get("reason"), str) and visual["reason"].strip(), "Unavailable visual needs a reason")
            require(info["status"] != "complete", "Unavailable visual requires qualified_complete")
        for relative in sequence(visual.get("retained_files", []), "visual retained_files"):
            safe_path(root, relative)
            retained.add(relative)
    return status, claims


def validate_study(root):
    errors, retained, sources = [], set(), {}
    counts = {"selected": 0, "analyzed": 0, "pending": 0, "unavailable": 0, "failed": 0, "conclusions": 0}
    try:
        root, info = load_study(root)
        counts["selected"] = len(info["selected_video_ids"])
        retained.add("study.json")
        for relative in info["retained_files"]:
            safe_path(root, relative)
            retained.add(relative)
        for video_id in info["selected_video_ids"]:
            try:
                status, claims = validate_video(root, info, video_id, retained)
                counts[status] += 1
                sources[video_id] = claims
            except (StudyError, OSError, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{video_id}: {exc}")
        if info["status"] in COMPLETE:
            require(not info["active_jobs"], "Active jobs prevent completion")
            require(info["selected_video_ids"], "An empty scope cannot be complete")
            if info["status"] == "qualified_complete":
                require(sequence(info.get("qualification_notes"), "qualification_notes"), "Qualified completion needs limitation notes")
            final = document(root, "final.json")
            retained.add("final.json")
            conclusions = sequence(final.get("conclusions"), "conclusions")
            ids = set()
            for conclusion in conclusions:
                require(isinstance(conclusion, dict) and isinstance(conclusion.get("id"), str) and conclusion["id"] not in ids, "Invalid or duplicate final conclusion ID")
                ids.add(conclusion["id"])
                require(isinstance(conclusion.get("text"), str) and conclusion["text"].strip(), "Empty final conclusion")
                evidence = sequence(conclusion.get("evidence"), "final evidence")
                require(evidence, "Final conclusion lacks evidence")
                for ref in evidence:
                    require(isinstance(ref, dict), "Expected final evidence object")
                    claim = sources.get(ref.get("video_id"), {}).get(ref.get("claim_id"))
                    require(claim is not None and ref.get("quote") in claim["quotes"], "Final evidence does not match linked claim evidence")
            counts["conclusions"] = len(conclusions)
            review = final.get("review", {})
            require(isinstance(review, dict) and review.get("status") in {"passed", "qualified"} and isinstance(review.get("reviewer"), str) and review["reviewer"].strip(), "Missing final review attestation")
            require(review["status"] != "qualified" or info["status"] == "qualified_complete", "Qualified final review requires qualified_complete")
            checked = sequence(review.get("checked_conclusion_ids"), "checked_conclusion_ids")
            require(set(checked) == ids, "Every final conclusion needs independent review attestation")
    except (StudyError, OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "counts": counts, "retained_files": sorted(retained),
            "verification_limit": "Structural validation and recorded review attestations; not independent proof of source faithfulness or factual correctness."}


def media_path(root, info, video_id, relative, kind):
    require(info.get("managed_root") == str(root), "Cleanup authority requires the original exclusively initialized root")
    require(video_id in info["selected_video_ids"], "Media video is outside selected scope")
    require(kind in KINDS, "Unknown temporary-media kind")
    require(isinstance(relative, str) and relative.startswith(f"tmp/{video_id}/"), "Temporary media must be under tmp/VIDEO_ID/")
    path = safe_path(root, relative)
    require(path.suffix.lower() in MEDIA_SUFFIXES, "File is not an eligible temporary-media type")
    identity = fingerprint(path)
    require(identity["links"] == 1, "Hardlinked media cannot be registered or removed")
    return path, identity


def ledger_for(root, info):
    ledger = document(root, "media-ledger.json")
    require(ledger.get("study_id") == info["study_id"], "Media ledger study ownership mismatch")
    sequence(ledger.get("files"), "media files")
    require(all(isinstance(entry, dict) for entry in ledger["files"]), "Invalid media ledger entry")
    return ledger


def register_media(root, video_id, relative, kind):
    root, _ = load_study(root)
    with exclusive_owner(root):
        return _register_media(root, video_id, relative, kind)


def _register_media(root, video_id, relative, kind):
    root, info = load_study(root)
    _, identity = media_path(root, info, video_id, relative, kind)
    require(relative not in info["retained_files"], "Retained evidence cannot be temporary media")
    ledger = ledger_for(root, info)
    require(not any(item.get("path") == relative for item in ledger["files"]), "Media path is already registered")
    entry = {"study_id": info["study_id"], "video_id": video_id, "path": relative,
             "kind": kind, "status": "present", "registered_at": now(), **identity}
    ledger["files"].append(entry)
    atomic_json(root / "media-ledger.json", ledger)
    return entry


def cleanup(root, *, apply=False):
    root, _ = load_study(root)
    if apply:
        with exclusive_owner(root):
            return _cleanup(root, apply=True)
    return _cleanup(root, apply=False)


def _cleanup(root, *, apply):
    root, info = load_study(root)
    require(info.get("managed_root") == str(root), "Cleanup requires the original exclusively initialized root")
    require(info["status"] in COMPLETE and not info["active_jobs"], "Cleanup requires a completed study with no active jobs")
    report = validate_study(root)
    require(report["valid"], "Cleanup blocked by validation: " + "; ".join(report["errors"]))
    ledger = ledger_for(root, info)
    retained = set(report["retained_files"])
    retained_identities = set()
    for relative in retained:
        info_stat = safe_path(root, relative).stat()
        retained_identities.add((info_stat.st_dev, info_stat.st_ino))
    candidates, seen, seen_identities = [], set(), set()
    for entry in ledger["files"]:
        require(isinstance(entry, dict) and entry.get("study_id") == info["study_id"], "Media entry study ownership mismatch")
        require(entry.get("path") not in seen, "Duplicate media ledger path")
        seen.add(entry.get("path"))
        require(entry.get("status") in {"present", "removed"}, "Invalid media ledger status")
        if entry["status"] == "removed":
            continue
        relative = entry.get("path")
        require(relative not in retained, f"Retained evidence cannot be removed: {relative}")
        path, identity = media_path(root, info, entry.get("video_id"), relative, entry.get("kind"))
        file_identity = (identity["device"], identity["inode"])
        require(file_identity not in retained_identities, f"Retained evidence cannot be removed: {relative}")
        require(file_identity not in seen_identities, f"Duplicate media ledger file: {relative}")
        seen_identities.add(file_identity)
        require(all(entry.get(k) == v for k, v in identity.items()), f"Media changed since registration: {relative}")
        candidates.append((entry, path))
    result = {"apply": apply, "planned": [e["path"] for e, _ in candidates],
              "planned_bytes": sum(e["size"] for e, _ in candidates), "removed": [], "bytes_freed": 0}
    if not apply:
        return result
    for entry, _ in candidates:
        path, identity = media_path(root, info, entry["video_id"], entry["path"], entry["kind"])
        require(all(entry.get(k) == v for k, v in identity.items()), f"Media changed during cleanup: {entry['path']}")
    for entry, _ in candidates:
        path, identity = media_path(root, info, entry["video_id"], entry["path"], entry["kind"])
        require(all(entry.get(k) == v for k, v in identity.items()), f"Media changed during cleanup: {entry['path']}")
        path.unlink()
        entry.update(status="removed", removed_at=now())
        result["removed"].append(entry["path"])
        result["bytes_freed"] += entry["size"]
        atomic_json(root / "media-ledger.json", ledger)
    result["completed_at"] = now()
    atomic_json(root / "cleanup-report.json", result)
    after = validate_study(root)
    require(after["valid"], "Post-cleanup retained-reference validation failed")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new exclusively managed study root")
    init.add_argument("root", type=Path)
    init.add_argument("--channel-id", required=True)
    init.add_argument("--video-id", action="append", default=[])
    validate = commands.add_parser("validate", help="Read-only structural and evidence-reference checks")
    validate.add_argument("root", type=Path)
    register = commands.add_parser("register-media", help="Register a task-created temporary media file")
    register.add_argument("root", type=Path)
    register.add_argument("--video-id", required=True)
    register.add_argument("--path", required=True)
    register.add_argument("--kind", choices=sorted(KINDS), required=True)
    clean = commands.add_parser("cleanup", help="Preview eligible media removal; --apply removes registered files")
    clean.add_argument("root", type=Path)
    clean.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init_study(args.root, args.channel_id, args.video_id)
        elif args.command == "validate":
            result = validate_study(args.root)
        elif args.command == "register-media":
            result = register_media(args.root, args.video_id, args.path, args.kind)
        else:
            result = cleanup(args.root, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result.get("valid") is False else 0
    except (StudyError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
