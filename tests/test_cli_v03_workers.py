"""Tests for --workers parallel batch processing."""
import time
from unittest.mock import MagicMock

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def _setup_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.CONFIG_PATH",
        tmp_path / "config.toml",
    )
    (tmp_path / "config.toml").write_text(
        'default_preset = "smart"\n', encoding="utf-8"
    )


def _make_target(vid: str, title: str = "T"):
    t = MagicMock()
    t.url = f"https://youtu.be/{vid}"
    t.video_id = vid
    t.title = title
    t.upload_date = None
    t.duration_sec = 60
    t.channel = "C"
    t.source = "inline"
    t.source_language = None
    return t


def _make_result():
    r = MagicMock()
    r.segments = [MagicMock(start=0, end=1, text="x")]
    r.text = "x"
    r.language_detected = "en"
    r.backend_name = "subtitles"
    r.duration_seconds = 1.0
    r.quality = None
    r.visual_segments = []
    return r


def test_help_shows_workers_flag():
    runner = CliRunner()
    res = runner.invoke(cli, ["batch", "--help"])
    assert "--workers" in res.output


def test_workers_eq_1_uses_serial_path(tmp_path, monkeypatch):
    """Default workers=1 → serial loop, fail-fast still works."""
    targets = [_make_target("aaa11111111"), _make_target("bbb22222222")]
    call_log = []

    def fake_run(target, cfg, **kw):
        call_log.append(target.video_id)
        return _make_result()

    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.resolve",
        lambda i, f, fi: (targets, []),
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.run_pipeline",
        fake_run,
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda b, env_path=None: None,
    )
    _setup_config(tmp_path, monkeypatch)

    runner = CliRunner()
    runner.invoke(
        cli,
        ["batch", "https://youtu.be/aaa", "https://youtu.be/bbb",
         "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )
    # Both processed (in order, since serial)
    assert call_log == ["aaa11111111", "bbb22222222"]


def test_workers_gt_1_processes_all(tmp_path, monkeypatch):
    """workers=4 still processes all targets, just possibly out-of-order."""
    targets = [_make_target(f"vid{i:08d}") for i in range(8)]
    call_log = []

    def fake_run(target, cfg, **kw):
        time.sleep(0.001)  # tiny delay to encourage thread interleaving
        call_log.append(target.video_id)
        return _make_result()

    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.resolve",
        lambda i, f, fi: (targets, []),
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.run_pipeline",
        fake_run,
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda b, env_path=None: None,
    )
    _setup_config(tmp_path, monkeypatch)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["batch", *[t.url for t in targets],
         "--workers", "4",
         "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    # All 8 processed
    assert sorted(call_log) == sorted(t.video_id for t in targets)


def test_workers_with_fail_fast_rejected(tmp_path, monkeypatch):
    """--workers > 1 + --fail-fast → exit 2 with error."""
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.resolve",
        lambda i, f, fi: ([_make_target("x")], []),
    )
    _setup_config(tmp_path, monkeypatch)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["batch", "https://youtu.be/x", "--workers", "4", "--fail-fast",
         "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )
    assert res.exit_code == 2
    assert "fail-fast" in res.output.lower() or "incompatible" in res.output.lower()
