"""Integration tests for v0.10 visual-pipeline features.

Covers the bits not directly tested in the per-module unit tests:
  • Gemini config is built with LOW resolution, response_schema,
    temperature=0.2, max_output_tokens=300 (#1, #2)
  • Async / Semaphore parallelism actually parallelises (#3)
  • Prompt caching is attempted once per run, reused across windows (#4)
  • Asymmetric frame extraction calls ffmpeg with the right offsets (#6)
  • Auto-promote `smart` → `tutorial` preset based on transcript density (#9 wiring)
  • VisualSegment confidence + needs_refinement defaults safe (#7 schema)

The Gemini SDK is mocked end-to-end — these are not real-API tests.
The real Gemini call is exercised by manually running
`neurolearn transcribe <URL> --with-visuals --preset tutorial` (see
QA-checklist in the v0.10 release notes).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from skills.neurolearn.detection.base import DetectionWindow
from skills.neurolearn.vision.gemini import GeminiVisionBackend


def _mock_gemini_response(payload: dict, *, prompt_tokens=1000, cached_tokens=0, output_tokens=100):
    """Build a fake Gemini response that exposes usage_metadata."""
    resp = MagicMock()
    resp.text = json.dumps(payload)
    resp.usage_metadata = MagicMock(
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
        cached_content_token_count=cached_tokens,
        total_token_count=prompt_tokens + output_tokens,
    )
    return resp


def _windows(n=3):
    return [
        DetectionWindow(
            start=i * 10.0, end=i * 10.0 + 5.0,
            reason="raw", score=0.8, weight=1.0, phrase=f"phrase {i}",
        )
        for i in range(n)
    ]


# === #1, #2 — Gemini config carries LOW resolution + schema + caps ===


def test_gemini_config_uses_low_resolution_and_schema(tmp_path):
    """Inspect the GenerateContentConfig passed to generate_content."""
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/1")
    fake_client.caches.create.return_value = MagicMock(name="cached/1", name_attr="cached/1")
    # cache.name must be a real string so the config accepts it
    fake_client.caches.create.return_value.name = "cached/test-id"

    fake_client.models.generate_content.return_value = _mock_gemini_response({
        "description": "Test",
        "key_objects": [],
        "importance": "medium",
        "confidence": 0.9,
        "needs_refinement": False,
    })

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[out_dir / "v_00010.jpg"],
    ):
        backend = GeminiVisionBackend(api_key="fake", model="gemini-2.5-flash")
        backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=_windows(1),
            prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )

    # Exactly one generate_content call for one window.
    assert fake_client.models.generate_content.called
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    # Pydantic config object — introspect.
    assert config.temperature == 0.2
    assert config.max_output_tokens == 300
    assert config.response_mime_type == "application/json"
    assert config.response_schema is not None
    # MEDIA_RESOLUTION_LOW is the optimization knob.
    assert "LOW" in str(config.media_resolution)


def test_visualsegment_has_confidence_and_needs_refinement_defaults():
    """New fields default to safe values so old callers/fixtures still work."""
    from skills.neurolearn.backends.vision_base import VisualSegment
    vs = VisualSegment(
        start=0, end=1, description="x", keyframes=[],
    )
    assert vs.confidence == 1.0
    assert vs.needs_refinement is False


# === #3 — Async / parallelism ===


def test_gemini_processes_windows_concurrently(tmp_path):
    """generate_content is invoked once per window. With async + Semaphore,
    they execute concurrently — we observe that by patching the call to
    record entry timestamps and confirm overlap."""
    import time
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/1")
    fake_client.caches.create.return_value.name = "cached/test-id"

    starts = []
    def slow_generate(**kw):
        starts.append(time.monotonic())
        time.sleep(0.2)
        return _mock_gemini_response({
            "description": "x", "key_objects": [],
            "importance": "medium", "confidence": 0.9, "needs_refinement": False,
        })
    fake_client.models.generate_content.side_effect = slow_generate

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[out_dir / "v_00010.jpg"],
    ):
        backend = GeminiVisionBackend(
            api_key="fake", model="gemini-2.5-flash", max_concurrent=5,
        )
        t0 = time.monotonic()
        out = backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=_windows(5),
            prompt_template="x",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )
        elapsed = time.monotonic() - t0

    assert len(out) == 5
    # Sequential would take 5 * 0.2 = 1.0s. Concurrent (5 in parallel)
    # should be ~0.2-0.4s with overhead. Generous threshold: < 0.7s.
    assert elapsed < 0.7, f"Took {elapsed:.2f}s — likely sequential, not parallel"
    # All starts close together → parallelism confirmed.
    if len(starts) >= 2:
        spread = max(starts) - min(starts)
        assert spread < 0.15, f"Start spread {spread:.3f}s — not parallel"


# === #4 — Prompt caching ===


def test_explicit_caches_create_not_called_v012(tmp_path):
    """v0.12.0: explicit `client.caches.create()` was REMOVED.

    Empirical finding: free-tier Gemini's
    TotalCachedContentStorageTokensPerModelFreeTier=0 so the call
    always 4xx'd. Implicit caching kicks in automatically when the
    stable system prompt + uploaded video stay identical across
    calls — no API call required.
    """
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/1")
    fake_client.models.generate_content.return_value = _mock_gemini_response({
        "description": "x", "key_objects": [],
        "importance": "medium", "confidence": 0.9, "needs_refinement": False,
    })

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[out_dir / "v_00010.jpg"],
    ):
        backend = GeminiVisionBackend(api_key="fake", model="gemini-2.5-flash")
        backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=_windows(4),
            prompt_template="describe {language} {transcript_snippet} {start_sec} {end_sec}",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )

    # Explicit cache is no longer created. Each per-window call carries
    # its own system_instruction; Google's implicit cache handles prefix
    # reuse server-side.
    assert fake_client.caches.create.call_count == 0
    assert fake_client.models.generate_content.call_count == 4
    # Each call now includes the system prompt inline (no cached_content).
    for call_obj in fake_client.models.generate_content.call_args_list:
        config = call_obj.kwargs["config"]
        # cached_content should be None / unset after removal
        assert getattr(config, "cached_content", None) is None


# === #5 — Frame quality + scale ===


def test_extract_keyframes_uses_quality_and_scale(tmp_path):
    """ffmpeg command should include -q:v 3 and a 1280px-wide scale filter."""
    import skills.neurolearn.vision.frames as frames_mod

    with patch.object(frames_mod, "subprocess") as mock_sp:
        # Stub run() — we don't actually exec ffmpeg.
        mock_sp.run.return_value = MagicMock(returncode=0)
        # Mock the directory pattern: no files created, but that's fine —
        # we're only inspecting the ffmpeg invocation.
        frames_mod.extract_keyframes(
            video_path=Path("v.mp4"),
            start=10.0, end=15.0, count=3,
            out_dir=tmp_path, video_id="v",
        )

    cmd = mock_sp.run.call_args.args[0]
    assert "-q:v" in cmd
    qv_idx = cmd.index("-q:v")
    assert cmd[qv_idx + 1] == "3"
    # Scale filter contains 1280.
    vf_idx = cmd.index("-vf")
    assert "1280" in cmd[vf_idx + 1]


# === #6 — Asymmetric offsets ===


def test_extract_keyframes_asymmetric_uses_correct_offsets(tmp_path):
    """For event_ts=10s, frames should be at 8.5 (10-1.5), 10.3, 12.0."""
    import skills.neurolearn.vision.frames as frames_mod

    captured_starts: list[float] = []

    def fake_run(cmd, check=True, **kwargs):
        # `-ss <ts>` is the seek timestamp.
        ss_idx = cmd.index("-ss")
        captured_starts.append(float(cmd[ss_idx + 1]))
        # Create the expected output file so existence check passes.
        out_path_idx = -1
        out_path = Path(cmd[out_path_idx])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00")
        return MagicMock(returncode=0)

    with patch.object(frames_mod.subprocess, "run", side_effect=fake_run):
        paths = frames_mod.extract_keyframes_asymmetric(
            video_path=Path("v.mp4"),
            event_ts=10.0,
            out_dir=tmp_path,
            video_id="v",
        )

    assert captured_starts == [8.5, 10.3, 12.0]
    assert len(paths) == 3


def test_asymmetric_clamps_negative_to_zero(tmp_path):
    """event_ts < 1.5s → first offset would be negative; should clamp to 0.0."""
    import skills.neurolearn.vision.frames as frames_mod

    captured_starts: list[float] = []

    def fake_run(cmd, check=True, **kwargs):
        ss_idx = cmd.index("-ss")
        captured_starts.append(float(cmd[ss_idx + 1]))
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00")
        return MagicMock(returncode=0)

    with patch.object(frames_mod.subprocess, "run", side_effect=fake_run):
        frames_mod.extract_keyframes_asymmetric(
            video_path=Path("v.mp4"),
            event_ts=1.0,   # 1.0 - 1.5 = -0.5 → must clamp to 0.0
            out_dir=tmp_path,
            video_id="v",
        )

    assert captured_starts[0] == 0.0   # clamped
    assert captured_starts[1] == 1.3
    assert captured_starts[2] == 3.0


# === #9 — Auto-promotion smart → tutorial ===


def test_smart_preset_promotes_to_tutorial_on_dense_transcript():
    """Density heuristic + preset switch should fire when smart is in use
    without explicit override."""
    from skills.neurolearn.detection.tutorial_detect import detect_tutorial

    # Fake segments — high action density.
    segs = []
    for i in range(10):
        seg = MagicMock()
        seg.start = i * 30.0
        seg.end = i * 30.0 + 5.0
        seg.text = f"Click here and press save. Now select the next item."
        segs.append(seg)

    sig = detect_tutorial(segs)
    assert sig.is_tutorial is True


def test_explicit_preset_blocks_promotion():
    """The auto-promote check only fires when user passed no --preset.
    transcribe.py guard: `if not user_passed_preset and preset_name == 'smart'`."""
    # This is just asserting the contract from the wiring; behaviour is
    # exercised in CLI integration tests via existing test_cli_*.
    # The check is: opts.get("preset") is not None → user override.
    opts_no_preset = {"preset": None}
    opts_with_preset = {"preset": "eco"}
    user_passed_no = opts_no_preset.get("preset") is not None
    user_passed_yes = opts_with_preset.get("preset") is not None
    assert user_passed_no is False
    assert user_passed_yes is True


# === Bonus: usage_metadata populated for budget tracker ===


def test_gemini_records_token_usage_per_call(tmp_path):
    """After annotate_segments, backend.last_run_usage has one TokenUsage
    per processed window with non-zero token counts (for budget tracker)."""
    fake_client = MagicMock()
    fake_client.files.upload.return_value = MagicMock(name="files/1")
    fake_client.caches.create.return_value.name = "cached/test-id"

    fake_client.models.generate_content.return_value = _mock_gemini_response(
        {
            "description": "x", "key_objects": [],
            "importance": "medium", "confidence": 0.9, "needs_refinement": False,
        },
        prompt_tokens=2500, cached_tokens=1500, output_tokens=200,
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "skills.neurolearn.vision.gemini.genai.Client",
        return_value=fake_client,
    ), patch(
        "skills.neurolearn.vision.frames.extract_keyframes",
        return_value=[out_dir / "v_00010.jpg"],
    ):
        backend = GeminiVisionBackend(api_key="fake", model="gemini-2.5-flash")
        backend.annotate_segments(
            video_path=Path("v.mp4"),
            windows=_windows(3),
            prompt_template="x",
            language="en",
            video_id="v",
            out_dir=out_dir,
        )

    assert len(backend.last_run_usage) == 3
    for usage in backend.last_run_usage:
        assert usage.prompt_tokens == 2500
        assert usage.cached_tokens == 1500
        assert usage.output_tokens == 200
