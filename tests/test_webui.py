"""Tests for the Web UI module.

We don't launch the Gradio server in tests — just verify the UI Blocks
build cleanly, the _run_one wrapper handles error paths, and the CLI
sub-command exists.
"""
import pytest

# Skip the whole module if gradio isn't fully installed.
# `importorskip` alone misses the case where a leftover empty
# `gradio/` directory creates a Python namespace package — the import
# succeeds but `gradio.Blocks` doesn't exist. Check for a real attribute.
try:
    import gradio  # noqa: F401
    if not hasattr(gradio, "Blocks"):
        pytest.skip(
            "gradio package present but incomplete "
            "(install via `uv sync --extra webui`)",
            allow_module_level=True,
        )
except ImportError:
    pytest.skip(
        "gradio not installed (install via `uv sync --extra webui`)",
        allow_module_level=True,
    )


def test_build_ui_returns_blocks():
    from skills.youtube_transcribe.webui.app import build_ui
    demo = build_ui()
    # gradio.Blocks instance
    assert isinstance(demo, gradio.Blocks)


def test_run_one_empty_input_returns_hint():
    from skills.youtube_transcribe.webui.app import _run_one
    transcript, visual, quality, outdir = _run_one(
        url_or_path="",
        preset_name="smart",
        backend_override="(default)",
        with_visuals=False,
        detect_method="(preset default)",
        max_windows=0,
        correct_asr=False,
    )
    assert "URL" in transcript or "введи" in transcript.lower() or "введ" in transcript.lower()
    assert visual == ""
    assert outdir is None


def test_run_one_resolve_failure(monkeypatch, tmp_path):
    """Bad URL → caught and reported in transcript field, no crash."""
    monkeypatch.setattr(
        "skills.youtube_transcribe.webui.app.resolve_with_env_checks",
        lambda preset, cli_overrides=None: ({"vision_backend": "off"}, []),
        raising=False,
    )

    def fake_resolve(inputs, from_file, filters):
        return [], [type("F", (), {"error": "yt-dlp got 404"})()]

    monkeypatch.setattr(
        "skills.youtube_transcribe.utils.resolver.resolve",
        fake_resolve,
    )
    monkeypatch.setattr(
        "skills.youtube_transcribe.config.load_config",
        lambda: type("C", (), {"language": "auto"})(),
    )

    from skills.youtube_transcribe.webui.app import _run_one
    transcript, _v, _q, outdir = _run_one(
        url_or_path="https://invalid/x",
        preset_name="smart",
        backend_override="(default)",
        with_visuals=False,
        detect_method="(preset default)",
        max_windows=0,
        correct_asr=False,
    )
    assert "probe error" in transcript or "resolve error" in transcript or "404" in transcript


def test_webui_cli_present():
    """CLI sub-command 'webui' must be registered on the main cli group."""
    from skills.youtube_transcribe.transcribe import cli
    assert "webui" in cli.commands


def test_webui_cli_help_runs():
    """`youtube-transcribe webui --help` should succeed."""
    from click.testing import CliRunner
    from skills.youtube_transcribe.transcribe import cli
    runner = CliRunner()
    res = runner.invoke(cli, ["webui", "--help"])
    assert res.exit_code == 0
    assert "--host" in res.output
    assert "--port" in res.output
    assert "--share" in res.output
