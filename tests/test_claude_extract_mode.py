"""Tests for the keyframe-extraction manifest (Mode-1 visual reports).

Visual reports are agent-driven: --with-visuals extracts keyframes via ffmpeg
and writes `keyframes/manifest.json` mapping frames → moments. Claude reads the
manifest in chat. There is no vision-LLM describe call.

Verifies the manifest writer produces the expected structure.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.pipeline_v02 import _write_keyframes_manifest


def _window(start: float, end: float, phrase: str = "") -> DetectionWindow:
    return DetectionWindow(
        start=start, end=end, reason="trigger", score=1.0, phrase=phrase,
    )


class TestWriteKeyframesManifest:
    def test_writes_manifest_with_expected_schema(self, tmp_path):
        """Manifest must contain video_id, mode, extracted_at, and a windows
        list with the expected per-window keys."""
        out_dir = tmp_path / "batch"
        out_dir.mkdir()

        def fake_extract(*, video_path, start, end, count, out_dir, video_id, **kw):
            f = out_dir / f"{video_id}_{int(start)}.jpg"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"frame")
            return [f]

        with patch(
            "skills.neurolearn.vision.frames.extract_keyframes",
            side_effect=fake_extract,
        ):
            manifest = _write_keyframes_manifest(
                windows=[_window(10.0, 14.0, phrase="hello")],
                video_path=Path("v.mp4"),
                out_dir=out_dir,
                video_id="abc",
                fpw=1,
                use_asymmetric=False,
            )

        assert manifest["video_id"] == "abc"
        assert manifest["mode"] == "claude_code_extract_only"
        assert "extracted_at" in manifest
        assert len(manifest["windows"]) == 1
        w = manifest["windows"][0]
        assert w["start"] == 10.0
        assert w["end"] == 14.0
        assert w["transcript_window"] == "hello"
        assert len(w["keyframes"]) == 1

        # manifest.json physically written under <out_dir>/keyframes/.
        manifest_path = out_dir / "keyframes" / "manifest.json"
        assert manifest_path.exists()
        on_disk = json.loads(manifest_path.read_text())
        assert on_disk["video_id"] == "abc"

    def test_relative_paths_in_manifest(self, tmp_path):
        """Manifest keyframe paths must be RELATIVE to out_dir so the
        directory is portable (user can move/copy without rewriting)."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        def fake_extract(*, video_path, start, end, count, out_dir, video_id, **kw):
            f = out_dir / f"{video_id}_{int(start)}.jpg"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"frame")
            return [f]

        with patch(
            "skills.neurolearn.vision.frames.extract_keyframes",
            side_effect=fake_extract,
        ):
            manifest = _write_keyframes_manifest(
                windows=[_window(5.0, 9.0)],
                video_path=Path("v.mp4"),
                out_dir=out_dir,
                video_id="v",
                fpw=1,
                use_asymmetric=False,
            )

        # Should be e.g. "frames/v_5.jpg", not absolute.
        for w in manifest["windows"]:
            for fp in w["keyframes"]:
                assert not Path(fp).is_absolute(), f"absolute path leaked: {fp}"

    def test_extraction_failure_skips_window(self, tmp_path):
        """A failing ffmpeg call for one window must not crash; window
        is dropped from manifest."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        def crash(*args, **kwargs):
            raise RuntimeError("ffmpeg unavailable")

        with patch(
            "skills.neurolearn.vision.frames.extract_keyframes",
            side_effect=crash,
        ):
            manifest = _write_keyframes_manifest(
                windows=[_window(0.0, 4.0)],
                video_path=Path("v.mp4"),
                out_dir=out_dir, video_id="v",
                fpw=1, use_asymmetric=False,
            )

        assert manifest["windows"] == []


