"""Tests for --skip-existing flag in batch_cmd."""
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


def test_help_shows_skip_existing():
    runner = CliRunner()
    res = runner.invoke(cli, ["batch", "--help"])
    assert "--skip-existing" in res.output


def test_skip_existing_skips_video_with_existing_transcript(tmp_path, monkeypatch):
    """If output_root contains <something>_<video_id>.txt, that target is skipped."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    # Pre-create a transcript file matching video_id "aaa11111111"
    (out_root / "01_TestVid_aaa11111111.txt").write_text("existing\n", encoding="utf-8")

    fake_target_a = MagicMock(
        url="https://youtu.be/aaa11111111", title="Test A", video_id="aaa11111111",
        upload_date=None, duration_sec=60, channel="C", source="inline",
        source_language=None,
    )
    fake_target_b = MagicMock(
        url="https://youtu.be/bbb22222222", title="Test B", video_id="bbb22222222",
        upload_date=None, duration_sec=60, channel="C", source="inline",
        source_language=None,
    )

    pipeline_calls = []

    def fake_run_pipeline(target, cfg, **kw):
        pipeline_calls.append(target.video_id)
        # Return minimal valid result
        from unittest.mock import MagicMock
        result = MagicMock()
        result.segments = [MagicMock(start=0, end=1, text="x")]
        result.text = "x"
        result.language_detected = "en"
        result.backend_name = "subtitles"
        result.duration_seconds = 1.0
        result.quality = None
        result.visual_segments = []
        return result

    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.resolve",
        lambda inputs, from_file, filters: ([fake_target_a, fake_target_b], []),
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.run_pipeline",
        fake_run_pipeline,
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    _setup_config(tmp_path, monkeypatch)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["batch",
         "https://youtu.be/aaa11111111", "https://youtu.be/bbb22222222",
         "--skip-existing",
         "--output-dir", str(out_root)],
        catch_exceptions=False,
    )

    # Only target B should have been transcribed (A skipped)
    assert "aaa11111111" not in pipeline_calls
    assert "bbb22222222" in pipeline_calls
    # Output mentions skip
    assert "skip" in res.output.lower() or "1 skipped" in res.output


def test_no_skip_existing_processes_everything(tmp_path, monkeypatch):
    """Without --skip-existing, all targets go through pipeline."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "01_TestVid_aaa11111111.txt").write_text("existing\n", encoding="utf-8")

    fake_target = MagicMock(
        url="https://youtu.be/aaa11111111", title="A", video_id="aaa11111111",
        upload_date=None, duration_sec=60, channel="C", source="inline",
        source_language=None,
    )

    pipeline_calls = []

    def fake_run(target, cfg, **kw):
        pipeline_calls.append(target.video_id)
        result = MagicMock()
        result.segments = [MagicMock(start=0, end=1, text="x")]
        result.text = "x"
        result.language_detected = "en"
        result.backend_name = "subtitles"
        result.duration_seconds = 1.0
        result.quality = None
        result.visual_segments = []
        return result

    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.resolve",
        lambda i, f, fi: ([fake_target], []),
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.transcribe.run_pipeline",
        fake_run,
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    _setup_config(tmp_path, monkeypatch)

    runner = CliRunner()
    runner.invoke(
        cli,
        ["batch", "https://youtu.be/aaa11111111", "--output-dir", str(out_root)],
        catch_exceptions=False,
    )

    assert pipeline_calls == ["aaa11111111"]
