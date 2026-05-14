"""Verify batch_cmd applies v0.2 stages per video."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def test_batch_with_visuals_applies_v02_stages_per_video(tmp_path, monkeypatch):
    """--with-visuals on batch should call apply_v02_stages per resolved target."""
    fake_seg = MagicMock(start=0.0, end=5.0, text="hello")
    fake_result = MagicMock()
    fake_result.segments = [fake_seg]
    fake_result.text = "hello"
    fake_result.language_detected = "en"
    fake_result.backend_name = "subtitles_auto"
    fake_result.duration_seconds = 5.0
    fake_result.quality = None
    fake_result.visual_segments = []

    apply_calls = []

    def fake_apply(**kwargs):
        apply_calls.append(kwargs)
        return kwargs["result"]

    # Mock resolver to return 2 fake targets
    fake_target_1 = MagicMock(
        url="https://youtu.be/aaa", title="Video A", video_id="aaa",
        upload_date=None, duration_sec=60, channel="C", source="inline", source_language=None,
    )
    fake_target_2 = MagicMock(
        url="https://youtu.be/bbb", title="Video B", video_id="bbb",
        upload_date=None, duration_sec=60, channel="C", source="inline", source_language=None,
    )

    monkeypatch.setattr(
        "skills.neurolearn.transcribe.resolve",
        lambda inputs, from_file, filters: ([fake_target_1, fake_target_2], []),
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.run_pipeline",
        lambda *a, **kw: fake_result,
    )
    monkeypatch.setattr(
        "skills.neurolearn.utils.downloader.download_video",
        lambda url, out_dir, **kw: (out_dir / "v.mp4").write_bytes(b"x") or (out_dir / "v.mp4"),
    )
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: "fake_key" if backend == "gemini" else None,
    )
    monkeypatch.setattr(
        "skills.neurolearn.pipeline_v02.apply_v02_stages",
        fake_apply,
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.CONFIG_PATH",
        tmp_path / "config.toml",
    )
    (tmp_path / "config.toml").write_text("default_preset = \"smart\"\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["batch", "https://youtu.be/aaa", "https://youtu.be/bbb",
         "--with-visuals", "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )

    # Should have called apply_v02_stages once per target
    assert len(apply_calls) == 2, (
        f"expected 2 calls, got {len(apply_calls)}. Output:\n{res.output}"
    )
    # Each call should have a non-None video_path (from download_video)
    for call in apply_calls:
        assert call.get("video_path") is not None, \
            f"video_path was None for call. Output:\n{res.output}"


def test_batch_without_visuals_still_runs_quality_check(tmp_path, monkeypatch):
    """Even without --with-visuals, batch should apply quality check (smart preset default)."""
    fake_seg = MagicMock(start=0.0, end=5.0, text="hello")
    fake_result = MagicMock()
    fake_result.segments = [fake_seg]
    fake_result.text = "hello"
    fake_result.language_detected = "en"
    fake_result.backend_name = "whisper-local"
    fake_result.duration_seconds = 5.0
    fake_result.quality = None
    fake_result.visual_segments = []

    apply_calls = []
    monkeypatch.setattr(
        "skills.neurolearn.pipeline_v02.apply_v02_stages",
        lambda **kw: apply_calls.append(kw) or kw["result"],
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.resolve",
        lambda inputs, from_file, filters: ([MagicMock(
            url="https://youtu.be/x", title="X", video_id="x",
            upload_date=None, duration_sec=60, channel="C", source="inline", source_language=None,
        )], []),
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.run_pipeline",
        lambda *a, **kw: fake_result,
    )
    # No GEMINI key — silent fallback to off
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: None,
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.CONFIG_PATH",
        tmp_path / "config.toml",
    )
    (tmp_path / "config.toml").write_text("default_preset = \"smart\"\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["batch", "https://youtu.be/x", "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )
    assert len(apply_calls) == 1
    # cfg_v02 should have quality_check=True (smart default)
    assert apply_calls[0]["cfg"].get("quality_check") is True, \
        f"quality_check missing. cfg: {apply_calls[0]['cfg']}"
