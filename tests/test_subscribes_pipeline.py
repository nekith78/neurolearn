"""Tests for subscribes.pipeline — orchestration of update flow."""
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _channel(handle="@A", channel_id="UC_a", last_id=None, last_pub=None,
             group=None):
    from skills.youtube_transcribe.subscribes.store import Channel
    return Channel(
        url=f"https://www.youtube.com/{handle}", handle=handle,
        channel_id=channel_id, group=group, added="2026-05-12",
        last_seen_video_id=last_id, last_seen_published=last_pub,
    )


def _rss(vid, pub_iso="2026-05-11T14:00:00+00:00"):
    from skills.youtube_transcribe.subscribes.rss import RssEntry
    return RssEntry(
        video_id=vid, url=f"https://www.youtube.com/watch?v={vid}",
        title=f"Title {vid}", channel_id="UC_a",
        published=datetime.fromisoformat(pub_iso),
    )


def test_first_run_requires_window(tmp_path: Path):
    """If a channel has no state and no override window — exit 2 via raise."""
    from skills.youtube_transcribe.subscribes.pipeline import (
        run_subscribes_update, SubscribesError,
    )
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[_channel(last_id=None)],
    ):
        with pytest.raises(SubscribesError, match="initial"):
            run_subscribes_update(
                subscribes_path=sub_path,
                group=None,
                days=None, since=None, until=None,
                match=None, filter_text=None,
                no_rss=False, yes=True, no_analyze=True,
                prompt=None, prompt_file=None,
                analyze_backend="gemini", filter_backend="gemini",
                ollama_model="llama3.2:3b",
                ollama_host="http://localhost:11434",
                no_stdout=False, output_dir=str(tmp_path),
                api_keys={}, batch_opts={},
            )


def test_stateful_default_uses_last_seen(tmp_path: Path):
    """Channel with state: pipeline filters entries where published > last_seen."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    entries = [_rss("new1", "2026-05-12T00:00:00+00:00"),
               _rss("old1", "2026-05-09T00:00:00+00:00")]

    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=entries,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # State updated with newest video
    mock_state.assert_called_once()
    args, _ = mock_state.call_args
    # update_last_seen(path, channel_id, video_id, published)
    assert args[2] == "new1"


def test_override_days_skips_state_update(tmp_path: Path):
    """When --days override is used, state must NOT be updated."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    entries = [_rss("v1", "2026-05-12T00:00:00+00:00")]

    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=entries,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, days=7,
            since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    mock_state.assert_not_called()


def test_group_filters_channels(tmp_path: Path):
    """--group ai-research should only fetch RSS for matching channels."""
    from skills.youtube_transcribe.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@AI1", channel_id="UC_ai1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="ai-research"),
        _channel(handle="@PH1", channel_id="UC_ph1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="philosophy"),
    ]
    with patch(
        "skills.youtube_transcribe.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline.fetch_rss",
        return_value=[],
    ) as mock_rss, patch(
        "skills.youtube_transcribe.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group="ai-research",
            days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # Only UC_ai1 fetched
    mock_rss.assert_called_once_with("UC_ai1")
