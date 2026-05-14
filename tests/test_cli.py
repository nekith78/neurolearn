from click.testing import CliRunner
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from skills.youtube_transcribe.transcribe import cli
from skills.youtube_transcribe.utils.resolver import ResolvedTarget


def _result(text: str = "hi", backend: str = "whisper-local"):
    return MagicMock(text=text, segments=[], language_detected="en",
                     backend_name=backend, duration_seconds=1.0)


def _target_local(path: Path) -> ResolvedTarget:
    return ResolvedTarget(url=str(path), title=None, upload_date=None,
                          duration_sec=None, channel=None,
                          source="single", video_id=None)


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    out = result.output.lower()
    assert "transcribe" in out
    assert "batch" in out  # batch sub-command exposed (Task 20B)


def _fake_cfg(tmp_path):
    from skills.youtube_transcribe.config import Config
    return Config(output_dir=str(tmp_path), timestamps=True, srt=True)


def test_cli_transcribe_subcommand_local_file(tmp_path):
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"f")
    runner = CliRunner()
    with patch("skills.youtube_transcribe.transcribe.run_wizard"), \
         patch("skills.youtube_transcribe.transcribe.CONFIG_PATH") as cp, \
         patch("skills.youtube_transcribe.transcribe.load_config",
               return_value=_fake_cfg(tmp_path)), \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([_target_local(audio)], [])), \
         patch("skills.youtube_transcribe.transcribe.run_pipeline",
               return_value=_result()), \
         patch("skills.youtube_transcribe.transcribe.write_txt_with_timestamps"), \
         patch("skills.youtube_transcribe.transcribe.write_srt"):
        cp.exists.return_value = True
        result = runner.invoke(cli, ["transcribe", str(audio),
                                     "--backend", "whisper-local",
                                     "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_cli_bare_url_routes_to_transcribe(tmp_path):
    """`youtube-transcribe https://youtu.be/X` (no sub-command)
    must be equivalent to `youtube-transcribe transcribe https://youtu.be/X`."""
    runner = CliRunner()
    with patch("skills.youtube_transcribe.transcribe.run_wizard"), \
         patch("skills.youtube_transcribe.transcribe.CONFIG_PATH") as cp, \
         patch("skills.youtube_transcribe.transcribe.load_config",
               return_value=_fake_cfg(tmp_path)), \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([_target_local(tmp_path / "x.mp3")], [])) as r, \
         patch("skills.youtube_transcribe.transcribe.run_pipeline",
               return_value=_result()), \
         patch("skills.youtube_transcribe.transcribe.write_txt_with_timestamps"), \
         patch("skills.youtube_transcribe.transcribe.write_srt"):
        cp.exists.return_value = True
        # bare URL — no "transcribe" sub-command
        result = runner.invoke(cli, ["https://youtu.be/jNQXAC9IVRw",
                                     "--backend", "subtitles",
                                     "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    r.assert_called_once()


def test_cli_transcribe_propagates_backend_not_configured(tmp_path):
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"f")
    from skills.youtube_transcribe.backends.base import BackendNotConfigured
    runner = CliRunner()
    with patch("skills.youtube_transcribe.transcribe.run_wizard"), \
         patch("skills.youtube_transcribe.transcribe.CONFIG_PATH") as cp, \
         patch("skills.youtube_transcribe.transcribe.load_config",
               return_value=_fake_cfg(tmp_path)), \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([_target_local(audio)], [])), \
         patch("skills.youtube_transcribe.transcribe.run_pipeline",
               side_effect=BackendNotConfigured("GEMINI_API_KEY missing")):
        cp.exists.return_value = True
        result = runner.invoke(cli, ["transcribe", str(audio),
                                     "--backend", "gemini",
                                     "--output-dir", str(tmp_path)])
    assert result.exit_code == 3
    assert "not configured" in result.output.lower() or "no api key" in result.output.lower()
