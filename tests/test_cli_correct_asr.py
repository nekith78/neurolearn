"""Tests for --correct-asr CLI flag wiring."""
from unittest.mock import MagicMock

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.CONFIG_PATH",
        tmp_path / "config.toml",
    )
    (tmp_path / "config.toml").write_text(
        'default_preset = "smart"\n', encoding="utf-8"
    )


def test_transcribe_help_shows_correct_asr_flags():
    runner = CliRunner()
    res = runner.invoke(cli, ["transcribe", "--help"])
    assert "--correct-asr" in res.output
    assert "--correct-asr-backend" in res.output


def test_batch_help_shows_correct_asr_flags():
    runner = CliRunner()
    res = runner.invoke(cli, ["batch", "--help"])
    assert "--correct-asr" in res.output
    assert "--correct-asr-backend" in res.output


def test_transcribe_correct_asr_flag_sets_overrides(tmp_path, monkeypatch):
    """--correct-asr should set correct_asr=True AND auto-enable quality_check."""
    captured = {}

    def fake_resolve_with_env_checks(preset, **kw):
        captured["cli_overrides"] = kw.get("cli_overrides")
        return ({"vision_backend": "off"}, [])

    monkeypatch.setattr(
        "skills.neurolearn.presets.loader.resolve_with_env_checks",
        fake_resolve_with_env_checks,
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.resolve",
        lambda i, f, fi: ([MagicMock(
            url="https://youtu.be/x", title="X", video_id="x",
            upload_date=None, duration_sec=60, channel="C", source="inline",
        )], []),
    )
    fake_result = MagicMock()
    fake_result.segments = [MagicMock(start=0, end=1, text="x")]
    fake_result.text = "x"
    fake_result.language_detected = "en"
    fake_result.backend_name = "subtitles"
    fake_result.duration_seconds = 1.0
    fake_result.quality = None
    fake_result.visual_segments = []
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.run_pipeline",
        lambda *a, **kw: fake_result,
    )
    monkeypatch.setattr(
        "skills.neurolearn.pipeline_v02.apply_v02_stages",
        lambda **kw: kw["result"],
    )
    _setup(tmp_path, monkeypatch)

    runner = CliRunner()
    runner.invoke(
        cli,
        ["transcribe", "https://youtu.be/x",
         "--correct-asr",
         "--correct-asr-backend", "groq",
         "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )

    overrides = captured.get("cli_overrides") or {}
    assert overrides.get("correct_asr") is True
    # v0.12.0: claude removed; groq is the cheap-LLM corrector now
    assert overrides.get("correct_asr_backend") == "groq"
    # quality_check must be auto-enabled (correct_asr depends on it)
    assert overrides.get("quality_check") is True


def test_correct_asr_does_not_force_quality_when_explicitly_off(tmp_path, monkeypatch):
    """--no-quality-check + --correct-asr → --no-quality-check wins (user intent).

    Implementation uses setdefault, so --no-quality-check setting False
    first will block --correct-asr's True. But our code orders:
      --check-quality → True
      --no-quality-check → False
      --correct-asr → setdefault True

    So --no-quality-check still wins. Test that.
    """
    captured = {}
    monkeypatch.setattr(
        "skills.neurolearn.presets.loader.resolve_with_env_checks",
        lambda p, **kw: (captured.setdefault("cli_overrides", kw.get("cli_overrides")),
                         ({"vision_backend": "off"}, []))[1],
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.resolve",
        lambda i, f, fi: ([MagicMock(
            url="https://youtu.be/x", title="X", video_id="x",
            upload_date=None, duration_sec=60, channel="C", source="inline",
        )], []),
    )
    fake_result = MagicMock()
    fake_result.segments = [MagicMock(start=0, end=1, text="x")]
    fake_result.text = "x"
    fake_result.language_detected = "en"
    fake_result.backend_name = "subtitles"
    fake_result.duration_seconds = 1.0
    fake_result.quality = None
    fake_result.visual_segments = []
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.run_pipeline",
        lambda *a, **kw: fake_result,
    )
    monkeypatch.setattr(
        "skills.neurolearn.pipeline_v02.apply_v02_stages",
        lambda **kw: kw["result"],
    )
    _setup(tmp_path, monkeypatch)

    runner = CliRunner()
    runner.invoke(
        cli,
        ["transcribe", "https://youtu.be/x",
         "--no-quality-check", "--correct-asr",
         "--output-dir", str(tmp_path / "out")],
        catch_exceptions=False,
    )

    overrides = captured.get("cli_overrides") or {}
    assert overrides.get("correct_asr") is True
    # --no-quality-check sets quality_check=False; setdefault by --correct-asr
    # won't override an existing key, so False wins.
    assert overrides.get("quality_check") is False
