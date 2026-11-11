from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "plugins/neurolearn/skills/studying-yt-channels/scripts/study.py"
SPEC = importlib.util.spec_from_file_location("channel_study", SCRIPT)
assert SPEC and SPEC.loader
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)
VIDEO = "abcdefghijk"


class ChannelStudyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "study"
        study.init_study(self.root, "UCexample", [VIDEO])

    def write(self, rel, value):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return {"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def read(self, rel):
        return json.loads((self.root / rel).read_text())

    def complete(self):
        transcript = self.write(f"videos/{VIDEO}/transcripts/01.json", {
            "backend": "subtitles", "duration_sec": 5,
            "segments": [{"start": 0, "end": 2, "text": "Read the source."},
                         {"start": 2, "end": 5, "text": "Keep the exception."}],
        })
        frame = self.root / f"videos/{VIDEO}/evidence/frame.jpg"
        frame.parent.mkdir(parents=True)
        frame.write_bytes(b"retained evidence")
        analysis = self.write(f"videos/{VIDEO}/analysis.json", {
            "video_id": VIDEO, "transcript_path": transcript["path"],
            "transcript_sha256": transcript["sha256"],
            "coverage": [{"first_segment": 0, "last_segment": 1}],
            "claims": [{"id": "C1", "text": "Read sources with exceptions.",
                        "requires_review": True,
                        "evidence": [{"first_segment": 0, "last_segment": 1,
                                      "quote": "Read the source."}]}],
            "visuals": [{"id": "V1", "start_s": 1, "end_s": 2,
                         "status": "sampled_frames", "retained_files": [frame.relative_to(self.root).as_posix()]}],
            "uncertainties": [],
            "review": {"status": "passed", "reviewer": "independent-reviewer",
                       "checked_claim_ids": ["C1"],
                       "sample_transcript_ranges": [{"first_segment": 0, "last_segment": 1}]},
        })
        self.write(f"videos/{VIDEO}/record.json", {
            "video_id": VIDEO, "url": f"https://www.youtube.com/watch?v={VIDEO}",
            "title": "Example", "kind": "video", "status": "analyzed",
            "transcripts": [{**transcript, "backend": "subtitles"}],
            "primary_transcript": transcript["path"], "analysis": analysis,
        })
        self.write("final.json", {
            "conclusions": [{"id": "F1", "text": "Read sources.",
                             "evidence": [{"video_id": VIDEO, "claim_id": "C1", "quote": "Read the source."}]}],
            "review": {"status": "passed", "reviewer": "final-reviewer", "checked_conclusion_ids": ["F1"]},
        })
        info = self.read("study.json")
        info["status"] = "complete"
        self.write("study.json", info)

    def update_analysis(self, change):
        record = self.read(f"videos/{VIDEO}/record.json")
        analysis = self.read(record["analysis"]["path"])
        change(analysis)
        record["analysis"] = self.write(record["analysis"]["path"], analysis)
        self.write(f"videos/{VIDEO}/record.json", record)

    def media(self, name="source.mp4"):
        path = self.root / f"tmp/{VIDEO}/{name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"temporary media")
        study.register_media(self.root, VIDEO, path.relative_to(self.root).as_posix(), "video")
        return path

    def test_init_refuses_preexisting_root(self):
        with self.assertRaises(study.StudyError):
            study.init_study(self.root, "UCexample", [VIDEO])

    def test_complete_valid_study_and_safe_cleanup(self):
        self.complete()
        media = self.media()
        unknown = media.with_name("unregistered.mp4")
        unknown.write_bytes(b"unregistered")
        self.assertTrue(study.validate_study(self.root)["valid"])
        preview = study.cleanup(self.root)
        self.assertEqual(preview["bytes_freed"], 0)
        self.assertTrue(media.exists())
        removed = study.cleanup(self.root, apply=True)
        self.assertEqual(removed["bytes_freed"], len(b"temporary media"))
        self.assertFalse(media.exists())
        self.assertTrue(unknown.exists())
        self.assertTrue((self.root / f"videos/{VIDEO}/evidence/frame.jpg").exists())
        self.assertTrue(study.validate_study(self.root)["valid"])
        self.assertEqual(study.cleanup(self.root, apply=True)["bytes_freed"], 0)

    def test_quote_must_be_inside_claimed_segments(self):
        self.complete()
        self.update_analysis(lambda a: a["claims"][0]["evidence"].__setitem__(0,
            {"first_segment": 1, "last_segment": 1, "quote": "Read the source."}))
        self.assertFalse(study.validate_study(self.root)["valid"])

    def test_final_quote_must_match_linked_claim_evidence(self):
        self.complete()
        final = self.read("final.json")
        final["conclusions"][0]["evidence"][0]["quote"] = "Keep the exception."
        self.write("final.json", final)
        self.assertFalse(study.validate_study(self.root)["valid"])

    def test_invalid_final_gate_deletes_nothing(self):
        self.complete()
        first = self.media()
        second = self.media("other.mp4")
        final = self.read("final.json")
        final["conclusions"][0]["evidence"][0]["claim_id"] = "missing"
        self.write("final.json", final)
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_incomplete_or_active_study_cannot_cleanup(self):
        self.complete()
        media = self.media()
        for patch in [{"status": "in_progress"}, {"active_jobs": ["visual-review"]}]:
            info = self.read("study.json")
            info.update({"status": "complete", "active_jobs": []})
            info.update(patch)
            self.write("study.json", info)
            with self.assertRaises(study.StudyError):
                study.cleanup(self.root, apply=True)
            self.assertTrue(media.exists())

    def test_changed_media_refused_without_deleting_other_files(self):
        self.complete()
        first = self.media()
        second = self.media("changed.mp4")
        second.write_bytes(b"replacement")
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_outside_path_symlink_and_hardlink_refused(self):
        self.complete()
        outside = Path(self.temp.name) / "outside.mp4"
        outside.write_bytes(b"user file")
        for path in ["../outside.mp4", str(outside), f"tmp/{VIDEO}/../../outside.mp4"]:
            with self.assertRaises(study.StudyError):
                study.register_media(self.root, VIDEO, path, "video")
        target = self.root / f"tmp/{VIDEO}/linked.mp4"
        target.parent.mkdir(parents=True)
        target.symlink_to(outside)
        with self.assertRaises(study.StudyError):
            study.register_media(self.root, VIDEO, target.relative_to(self.root).as_posix(), "video")
        target.unlink()
        os.link(outside, target)
        with self.assertRaises(study.StudyError):
            study.register_media(self.root, VIDEO, target.relative_to(self.root).as_posix(), "video")
        self.assertTrue(outside.exists())

    def test_retained_file_and_nonmedia_refused(self):
        self.complete()
        media = self.media()
        info = self.read("study.json")
        info["retained_files"].append(media.relative_to(self.root).as_posix())
        self.write("study.json", info)
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        path = media.with_name("transcript.json")
        path.write_text("{}")
        with self.assertRaises(study.StudyError):
            study.register_media(self.root, VIDEO, path.relative_to(self.root).as_posix(), "download")
        self.assertTrue(media.exists())

    def test_retained_case_alias_blocks_cleanup_before_any_deletion(self):
        self.complete()
        first = self.media("first.mp4")
        media = self.media()
        alias = media.with_name(media.name.upper())
        if not alias.exists():
            self.skipTest("Filesystem is case-sensitive")
        info = self.read("study.json")
        info["retained_files"].append(alias.relative_to(self.root).as_posix())
        self.write("study.json", info)
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        self.assertTrue(first.exists())
        self.assertTrue(media.exists())

    def test_duplicate_case_alias_blocks_cleanup_before_any_deletion(self):
        self.complete()
        media = self.media()
        alias = media.with_name(media.name.upper())
        if not alias.exists():
            self.skipTest("Filesystem is case-sensitive")
        ledger = self.read("media-ledger.json")
        entry = dict(ledger["files"][0], path=alias.relative_to(self.root).as_posix())
        ledger["files"].append(entry)
        self.write("media-ledger.json", ledger)
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        self.assertTrue(media.exists())

    def test_mismatched_video_or_study_ownership_refused(self):
        self.complete()
        media = self.media()
        with self.assertRaises(study.StudyError):
            study.register_media(self.root, "other123456", media.relative_to(self.root).as_posix(), "video")
        ledger = self.read("media-ledger.json")
        ledger["study_id"] = "another-study"
        self.write("media-ledger.json", ledger)
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        self.assertTrue(media.exists())

    def test_empty_transcript_coverage_and_nonfinite_visual_are_invalid(self):
        self.complete()
        self.update_analysis(lambda a: a["coverage"].__setitem__(0, {"first_segment": 0, "last_segment": 0}))
        self.assertFalse(study.validate_study(self.root)["valid"])
        self.complete_reset()
        self.update_analysis(lambda a: a["visuals"][0].__setitem__("end_s", float("nan")))
        self.assertFalse(study.validate_study(self.root)["valid"])

    def complete_reset(self):
        # Rebuild source fixtures after a deliberately invalid analysis.
        frame = self.root / f"videos/{VIDEO}/evidence/frame.jpg"
        frame.unlink()
        frame.parent.rmdir()
        self.complete()

    def test_empty_analyzed_transcript_and_unreviewed_final_are_invalid(self):
        self.complete()
        record = self.read(f"videos/{VIDEO}/record.json")
        record["transcripts"][0].update(self.write(record["primary_transcript"], {"segments": []}))
        self.write(f"videos/{VIDEO}/record.json", record)
        self.assertFalse(study.validate_study(self.root)["valid"])
        self.complete_reset()
        final = self.read("final.json")
        final["review"]["checked_conclusion_ids"] = []
        self.write("final.json", final)
        self.assertFalse(study.validate_study(self.root)["valid"])

    def test_native_backend_and_declared_backend_must_agree(self):
        self.complete()
        record = self.read(f"videos/{VIDEO}/record.json")
        record["transcripts"][0]["backend"] = "groq"
        self.write(f"videos/{VIDEO}/record.json", record)
        self.assertFalse(study.validate_study(self.root)["valid"])

    def test_qualified_completion_preserves_explicit_limitations(self):
        self.complete()
        self.update_analysis(lambda a: a["uncertainties"].append("One term remains unclear."))
        self.assertFalse(study.validate_study(self.root)["valid"])
        info = self.read("study.json")
        info.update(status="qualified_complete", qualification_notes=["Uncertain term is not used as a definite conclusion."])
        self.write("study.json", info)
        self.assertTrue(study.validate_study(self.root)["valid"])

    def test_concurrent_cleanup_or_registration_refuses_existing_lock(self):
        self.complete()
        media = self.media()
        (self.root / ".study.lock").write_text("another owner")
        with self.assertRaises(study.StudyError):
            study.cleanup(self.root, apply=True)
        another = media.with_name("another.mp4")
        another.write_bytes(b"another")
        with self.assertRaises(study.StudyError):
            study.register_media(self.root, VIDEO, another.relative_to(self.root).as_posix(), "video")
        self.assertTrue(media.exists())
        self.assertEqual((self.root / ".study.lock").read_text(), "another owner")

    def test_visual_queue_can_be_pending_only_during_work(self):
        self.complete()
        self.update_analysis(lambda a: a["visuals"][0].__setitem__("status", "pending"))
        self.assertFalse(study.validate_study(self.root)["valid"])
        info = self.read("study.json")
        info["status"] = "in_progress"
        self.write("study.json", info)
        self.assertTrue(study.validate_study(self.root)["valid"])

    def test_cli_end_to_end_preserves_evidence(self):
        self.root = Path(self.temp.name) / "cli-study"

        def command(*args):
            completed = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)

        command("init", str(self.root), "--channel-id", "UCexample", "--video-id", VIDEO)
        self.complete()
        media = self.root / f"tmp/{VIDEO}/source.mp4"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"CLI temporary media")
        command("register-media", str(self.root), "--video-id", VIDEO,
                "--path", media.relative_to(self.root).as_posix(), "--kind", "video")
        self.assertTrue(command("validate", str(self.root))["valid"])
        self.assertFalse(command("cleanup", str(self.root))["apply"])
        self.assertTrue(media.exists())
        self.assertEqual(command("cleanup", str(self.root), "--apply")["bytes_freed"], len(b"CLI temporary media"))
        self.assertFalse(media.exists())
        self.assertTrue((self.root / f"videos/{VIDEO}/evidence/frame.jpg").exists())
        self.assertTrue(command("validate", str(self.root))["valid"])


if __name__ == "__main__":
    unittest.main()
