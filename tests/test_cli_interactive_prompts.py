"""Tests for interactive URL/query prompts on transcribe / batch /
subscribes add / research when positional arg is omitted.

Verifies that:
  • non-TTY + no arg → exit 2 (the existing behavior)
  • TTY + no arg → prompt is consulted, value flows to the rest of the pipeline
"""
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from skills.youtube_transcribe.transcribe import cli


def test_research_prompts_when_no_query_and_tty():
    """research with no query: in TTY, prompt is consulted; value flows to run_research."""
    with patch("skills.youtube_transcribe.shared.prompts._is_tty",
               return_value=True), \
         patch("skills.youtube_transcribe.shared.prompts.prompt_url_or_die",
               return_value="Claude updates") as mock_prompt, \
         patch("skills.youtube_transcribe.research.pipeline.run_research",
               return_value=Path("/tmp/fake_batch")) as mock_pipe:
        runner = CliRunner()
        res = runner.invoke(cli, [
            "research",
            "--days", "7", "--languages", "en", "--limit", "5",
            "--no-analyze", "--yes", "--backend", "subtitles",
            "--analyze-backend", "ollama",
        ], catch_exceptions=False)
    assert res.exit_code == 0
    mock_prompt.assert_called_once()
    assert mock_pipe.call_args.kwargs["query"] == "Claude updates"


def test_subscribes_add_prompts_when_no_url_and_tty():
    """subscribes add with no URL: prompt is consulted; channel resolution proceeds."""
    fake_resolved = MagicMock(
        platform="youtube",
        url="https://www.youtube.com/@anth",
        handle="anth",
        channel_id="UCabc",
    )
    with patch("skills.youtube_transcribe.shared.prompts._is_tty",
               return_value=True), \
         patch("skills.youtube_transcribe.shared.prompts.prompt_url_or_die",
               return_value="https://www.youtube.com/@anth") as mock_prompt, \
         patch("skills.youtube_transcribe.subscribes.cli.resolve_channel",
               return_value=fake_resolved), \
         patch("skills.youtube_transcribe.subscribes.cli.add_channel"):
        runner = CliRunner()
        runner.invoke(cli, ["subscribes", "add"])
    mock_prompt.assert_called_once()


def test_transcribe_prompts_when_no_url_and_tty():
    """transcribe with no URL: prompt is consulted; resolver receives prompted value."""
    cfg = MagicMock(fast_path_enabled=True)
    with patch("skills.youtube_transcribe.shared.prompts._is_tty",
               return_value=True), \
         patch("skills.youtube_transcribe.shared.prompts.prompt_url_or_die",
               return_value="https://youtu.be/PROMPTED") as mock_prompt, \
         patch("skills.youtube_transcribe.transcribe.run_wizard"), \
         patch("skills.youtube_transcribe.transcribe.load_config",
               return_value=cfg), \
         patch("skills.youtube_transcribe.transcribe._override_config",
               return_value=cfg), \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([], [])) as mock_resolve:
        runner = CliRunner()
        runner.invoke(cli, ["transcribe"])
    mock_prompt.assert_called_once()
    args, _kwargs = mock_resolve.call_args
    assert args[0] == ["https://youtu.be/PROMPTED"]


def test_batch_prompts_when_no_inputs_and_tty(tmp_path: Path):
    """batch with no inputs, no --from-file, no --search: prompts multi-line."""
    with patch("skills.youtube_transcribe.shared.prompts._is_tty",
               return_value=True), \
         patch("skills.youtube_transcribe.shared.prompts.prompt_urls_or_die",
               return_value=["https://youtu.be/A", "https://youtu.be/B"]) as mock_prompt, \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([], [])) as mock_resolve:
        runner = CliRunner()
        runner.invoke(cli, ["batch"])
    mock_prompt.assert_called_once()
    args, _kwargs = mock_resolve.call_args
    assert args[0] == ["https://youtu.be/A", "https://youtu.be/B"]


def test_batch_does_not_prompt_when_search_given():
    """batch --search "foo" must NOT trigger the URL prompt (search is an alternative source)."""
    with patch("skills.youtube_transcribe.shared.prompts._is_tty",
               return_value=True), \
         patch("skills.youtube_transcribe.shared.prompts.prompt_urls_or_die") as mock_prompt, \
         patch("skills.youtube_transcribe.transcribe.resolve",
               return_value=([], [])):
        runner = CliRunner()
        runner.invoke(cli, ["batch", "--search", "claude features",
                            "--limit", "1"])
    mock_prompt.assert_not_called()
