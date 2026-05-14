"""Tests for shared.progress — spinner / verbose-print stage helper."""
from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from skills.neurolearn.shared.progress import stage_progress


def _make_capturing_console() -> tuple[Console, StringIO]:
    """Console writing to a StringIO so we can assert on rendered output.

    `force_terminal=False` keeps Rich from emitting ANSI escapes — easier
    substring matching in tests.
    """
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=200), buf


def test_verbose_mode_prints_each_update_no_spinner():
    """With verbose=True the helper degrades to plain print lines; no
    rich.status.Status object is involved."""
    console, buf = _make_capturing_console()
    with stage_progress(console, verbose=True,
                        initial="Preparing...") as stage:
        stage.update("Downloading audio...")
        stage.update("Transcribing via gemini...")
    out = buf.getvalue()
    # Initial label printed on entry, plus each subsequent update.
    assert "Preparing..." in out
    assert "Downloading audio..." in out
    assert "Transcribing via gemini..." in out


def test_non_verbose_uses_rich_status_object():
    """Without verbose: the yielded handle is rich's Status (has start/stop
    plus update). We don't assert on terminal output (the spinner is
    transient and doesn't render to non-TTY buffers); we assert on type."""
    console, _ = _make_capturing_console()
    with stage_progress(console, verbose=False,
                        initial="Working...") as stage:
        # rich.status.Status has these attributes
        assert hasattr(stage, "update")
        assert hasattr(stage, "start")
        assert hasattr(stage, "stop")
        stage.update("Stage 2")  # must not raise


def test_verbose_no_exception_on_empty_block():
    """The helper must not require any .update() calls — caller can
    enter and exit without doing anything (e.g. fast local-file path)."""
    console, _ = _make_capturing_console()
    with stage_progress(console, verbose=True) as stage:
        assert stage is not None
    # No assertion needed — just verifying the block completes cleanly.


def test_pipeline_invokes_on_stage_callback(monkeypatch, tmp_path):
    """run_pipeline must call on_stage at phase boundaries.

    Covers the local-file branch (no download/yt-dlp involved, fastest
    path to assert callback ordering without mocking the network).
    """
    from skills.neurolearn.pipeline import run_pipeline
    from skills.neurolearn.config import Config
    from skills.neurolearn.utils.resolver import ResolvedTarget

    # Create a fake local file so the local-file branch is taken.
    fake_audio = tmp_path / "x.mp3"
    fake_audio.write_bytes(b"\x00")

    fake_backend = MagicMock()
    fake_backend.transcribe.return_value = MagicMock(segments=[])
    monkeypatch.setattr(
        "skills.neurolearn.pipeline.build_backend",
        lambda *a, **k: fake_backend,
    )

    cfg = Config()
    cfg.language = "en"
    cfg.default_backend = "gemini"

    target = ResolvedTarget(
        url=str(fake_audio), source="file", video_id=None, title=None,
        duration_sec=None, upload_date=None, channel=None,
    )

    calls: list[str] = []
    run_pipeline(target, cfg, on_stage=calls.append)
    # On the local-file path we expect exactly one transition.
    assert any("Transcribing" in c for c in calls)


def test_pipeline_no_callback_is_safe(monkeypatch, tmp_path):
    """on_stage=None must work as before — no progress, no errors."""
    from skills.neurolearn.pipeline import run_pipeline
    from skills.neurolearn.config import Config
    from skills.neurolearn.utils.resolver import ResolvedTarget

    fake_audio = tmp_path / "x.mp3"
    fake_audio.write_bytes(b"\x00")
    fake_backend = MagicMock()
    fake_backend.transcribe.return_value = MagicMock(segments=[])
    monkeypatch.setattr(
        "skills.neurolearn.pipeline.build_backend",
        lambda *a, **k: fake_backend,
    )

    cfg = Config()
    cfg.language = "en"
    cfg.default_backend = "gemini"
    target = ResolvedTarget(
        url=str(fake_audio), source="file", video_id=None, title=None,
        duration_sec=None, upload_date=None, channel=None,
    )

    # Must not raise even when no callback is provided.
    run_pipeline(target, cfg)
