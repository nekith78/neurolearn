"""v0.10.9 Fix K: when `_run_batch_pipeline` blows up mid-batch, the
finalize block must still write `manifest.json`, `combined.md`, and
`errors.log` before the exception propagates.

Pre-v0.10.9, a `RuntimeError` from the whisper-local loader (cuBLAS
missing — Bug I) on video #1 left the output dir empty: no manifest,
no errors.log, no combined.md. The user had only stderr noise and an
empty `videos/` dir to debug from.

Now the finalize block runs unconditionally, plus the crash itself is
recorded as a synthetic `BatchFailure` so it shows up in
`errors.log[].error_text`.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skills.neurolearn.utils.resolver import ResolvedTarget


def _target(idx: int = 1) -> ResolvedTarget:
    return ResolvedTarget(
        url=f"https://youtu.be/v{idx:02d}",
        title=f"Video {idx}",
        upload_date=date(2026, 5, 20),
        duration_sec=60,
        channel="@x",
        source="channel",
        video_id=f"v{idx:02d}",
    )


def _cfg(tmp_path: Path) -> MagicMock:
    return MagicMock(
        default_backend="whisper-local", language="auto",
        output_dir=str(tmp_path), keep_audio=False,
        timestamps=True, srt=True, fast_path_enabled=True,
        cookies_file=None,
    )


def test_batch_writes_artifacts_when_run_pipeline_raises(tmp_path: Path):
    """The canonical case from the bug report: WhisperModel crashes on
    cuBLAS-missing during the very first video. Pre-v0.10.9 the loop
    propagated the exception before manifest.json could be written.
    Now the finally block runs first and the manifest is on disk by the
    time the caller sees the traceback."""
    from skills.neurolearn.transcribe import _run_batch_pipeline

    target = _target()
    cfg = _cfg(tmp_path)

    with patch(
        "skills.neurolearn.transcribe.run_pipeline",
        side_effect=RuntimeError(
            "Library cublas64_12.dll is not found or cannot be loaded"
        ),
    ), patch(
        "skills.neurolearn.transcribe.write_combined_md"
    ) as wcm, patch(
        "skills.neurolearn.transcribe.write_manifest_json"
    ) as wmj, patch(
        "skills.neurolearn.transcribe.write_errors_log"
    ) as wel:
        with pytest.raises(RuntimeError, match="cublas"):
            _run_batch_pipeline(
                targets=[target], cfg=cfg,
                opts={"output_dir": str(tmp_path)},
            )

    # All three writers fired before the re-raise — that's the whole
    # point of the v0.10.9 finalize block.
    wcm.assert_called_once()
    wmj.assert_called_once()
    wel.assert_called_once()


def test_batch_records_crash_in_failures_list(tmp_path: Path):
    """The crash is added to the `failures` list as a batch-level entry
    so it surfaces in errors.log with a meaningful message. The
    failures list passed to write_errors_log must contain the crash."""
    from skills.neurolearn.transcribe import _run_batch_pipeline

    target = _target()
    cfg = _cfg(tmp_path)

    with patch(
        "skills.neurolearn.transcribe.run_pipeline",
        side_effect=RuntimeError("Library cublas64_12.dll is not found"),
    ), patch(
        "skills.neurolearn.transcribe.write_combined_md"
    ), patch(
        "skills.neurolearn.transcribe.write_manifest_json"
    ) as wmj, patch(
        "skills.neurolearn.transcribe.write_errors_log"
    ):
        with pytest.raises(RuntimeError):
            _run_batch_pipeline(
                targets=[target], cfg=cfg,
                opts={"output_dir": str(tmp_path)},
            )

    # Manifest receives the failures argument — verify the crash entry
    # is there with the right stage and a meaningful error text.
    failures_arg = wmj.call_args.args[1]
    crash_entries = [f for f in failures_arg if f.stage == "batch"]
    assert len(crash_entries) == 1
    assert "cublas" in crash_entries[0].error_text.lower()


def test_batch_re_raises_after_finalize(tmp_path: Path):
    """The original exception must propagate to the caller AFTER
    artifacts are written. Caller behavior is unchanged from the user's
    perspective — they still see the traceback — but now there's a
    manifest on disk too."""
    from skills.neurolearn.transcribe import _run_batch_pipeline

    target = _target()
    cfg = _cfg(tmp_path)

    custom_error = RuntimeError("custom marker xyz123")
    with patch(
        "skills.neurolearn.transcribe.run_pipeline",
        side_effect=custom_error,
    ), patch(
        "skills.neurolearn.transcribe.write_combined_md"
    ), patch(
        "skills.neurolearn.transcribe.write_manifest_json"
    ), patch(
        "skills.neurolearn.transcribe.write_errors_log"
    ):
        with pytest.raises(RuntimeError, match="custom marker xyz123"):
            _run_batch_pipeline(
                targets=[target], cfg=cfg,
                opts={"output_dir": str(tmp_path)},
            )


def test_batch_keyboard_interrupt_still_writes_artifacts(tmp_path: Path):
    """User-initiated Ctrl+C is a special case — we still finalize
    so partial progress isn't lost, but we re-raise so the shell
    sees the interrupt exit code."""
    from skills.neurolearn.transcribe import _run_batch_pipeline

    target = _target()
    cfg = _cfg(tmp_path)

    with patch(
        "skills.neurolearn.transcribe.run_pipeline",
        side_effect=KeyboardInterrupt(),
    ), patch(
        "skills.neurolearn.transcribe.write_combined_md"
    ) as wcm, patch(
        "skills.neurolearn.transcribe.write_manifest_json"
    ) as wmj, patch(
        "skills.neurolearn.transcribe.write_errors_log"
    ) as wel:
        with pytest.raises(KeyboardInterrupt):
            _run_batch_pipeline(
                targets=[target], cfg=cfg,
                opts={"output_dir": str(tmp_path)},
            )

    # All three writers still fired despite the interrupt.
    wcm.assert_called_once()
    wmj.assert_called_once()
    wel.assert_called_once()
