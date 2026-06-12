"""Tests for subscribes.pipeline — orchestration of update flow."""
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _channel(handle="@A", channel_id="UC_a", last_id=None, last_pub=None,
             group=None, platform="youtube"):
    from skills.neurolearn.subscribes.store import Channel
    base_url = {
        "youtube": "https://www.youtube.com",
        "instagram": "https://www.instagram.com",
        "tiktok": "https://www.tiktok.com",
    }[platform]
    return Channel(
        url=f"{base_url}/{handle}", handle=handle,
        channel_id=channel_id, group=group, added="2026-05-12",
        last_seen_video_id=last_id, last_seen_published=last_pub,
        platform=platform,
    )


def _video_seam(*items):
    """Patch targets for the v0.20 `/videos` early-exit walk.

    `items`: (video_id, pub_iso[, duration]) tuples in newest-first order.
    Returns ``(ids, extract_fn)`` to feed
    ``patch("...pipeline._list_video_ids", return_value=ids)`` and
    ``patch("...pipeline._extract_video_metadata", side_effect=extract_fn)``.
    Mirrors the real fetcher: list IDs, then extract each id for its date,
    so the window/early-exit logic under test runs for real.
    """
    from skills.neurolearn.subscribes.pipeline import _ChannelVideo
    mapping: dict = {}
    ids: list[str] = []
    for it in items:
        vid, pub = it[0], it[1]
        dur = it[2] if len(it) > 2 else None
        ids.append(vid)
        mapping[vid] = _ChannelVideo(
            video_id=vid, url=f"https://www.youtube.com/watch?v={vid}",
            title=f"Title {vid}", duration_sec=dur,
            published=datetime.fromisoformat(pub),
        )

    def extract(video_id, *, cookies_file=None):
        return mapping.get(video_id)

    return ids, extract


def test_first_run_requires_window(tmp_path: Path):
    """If a channel has no state and no override window — exit 2 via raise."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, SubscribesError,
    )
    sub_path = tmp_path / "subscribes.toml"
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
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
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    ids, extract = _video_seam(
        ("new1", "2026-05-12T00:00:00+00:00"),
        ("old1", "2026-05-09T00:00:00+00:00"),
    )

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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


def test_bootstrap_first_run_initializes_state(tmp_path: Path):
    """Channel without state + --days 7: state IS initialized (bootstrap).

    Pre-fix v0.7 bug: --days marked the run as "override → don't update
    state", so first-run with --days produced an empty state, and the next
    incremental call kept asking for --days. Now bootstrap is recognized
    separately and the state is seeded.

    v0.10.7 note: the RSS entry timestamp was previously hardcoded to
    2026-05-12 which broke the test as soon as wall-clock drifted >7
    days past that. Now it's expressed relative to `datetime.now()` so
    the test keeps passing as the calendar advances.
    """
    from datetime import datetime, timezone, timedelta
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id=None, last_pub=None)  # ← no state yet
    # Entry one day ago — well inside the 7-day bootstrap window.
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ids, extract = _video_seam(("v1", recent))

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, days=7,  # ← bootstrap window
            since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # Bootstrap recognized → state initialized to the newest entry.
    mock_state.assert_called_once()
    assert mock_state.call_args.args[2] == "v1"


def test_state_advances_when_transcribe_batch_returns_none(tmp_path: Path):
    """Variant 2: state must advance even if _run_batch_pipeline returns None
    (e.g. catastrophic transcribe failure). Otherwise a temporary blip would
    pin the channel forever."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    ids, extract = _video_seam(("recent", "2026-05-12T00:00:00+00:00"))

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=None,  # ← simulate batch failure
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
    mock_state.assert_called_once()
    assert mock_state.call_args.args[2] == "recent"


def test_override_days_skips_state_update(tmp_path: Path):
    """When --days override is used, state must NOT be updated."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    ids, extract = _video_seam(("v1", "2026-05-12T00:00:00+00:00"))

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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


def test_youtube_videos_come_from_videos_tab(tmp_path: Path):
    """v0.20: YouTube full-video fetch lists the channel's `/videos` tab
    (RSS retired — it leaked livestreams). The fetcher hits `_list_video_ids`
    with the channel URL, not RSS / the bare-channel yt-dlp scrape."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    ids, extract = _video_seam(("yt1", "2026-05-12T00:00:00+00:00", 900))

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ) as mock_list, patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=AssertionError("YouTube must use the /videos tab, not the bare-channel scrape"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
    mock_list.assert_called_once()
    # Called with the channel URL; _list_video_ids appends `/videos` itself.
    assert mock_list.call_args.args[0] == ch.url


def test_videos_tab_carries_duration(tmp_path: Path):
    """Candidates from the `/videos` walk carry duration_sec (from the
    per-id extract), so downstream length filters still work."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(last_id="oldvid", last_pub="2026-05-10T00:00:00+00:00")
    ids, extract = _video_seam(("yt1", "2026-05-12T00:00:00+00:00", 720))

    captured_targets = {}

    def capture_batch(*, targets, **kw):
        captured_targets["targets"] = list(targets)
        return tmp_path / "out"

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_batch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
    targets = captured_targets["targets"]
    assert len(targets) == 1
    assert targets[0].duration_sec == 720


def test_group_filters_channels(tmp_path: Path):
    """--group ai-research should only fetch videos for matching channels."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@AI1", channel_id="UC_ai1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="ai-research"),
        _channel(handle="@PH1", channel_id="UC_ph1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", group="philosophy"),
    ]
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=[],
    ) as mock_list, patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        return_value=[],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
    # Only the ai-research channel fetched.
    mock_list.assert_called_once()
    assert mock_list.call_args.args[0] == "https://www.youtube.com/@AI1"


# === v0.8: Instagram / TikTok flows ===


def test_instagram_channel_uses_yt_dlp_with_cookies(tmp_path: Path):
    """Instagram channels NEVER hit RSS — always go through yt-dlp with the
    user's configured cookies_browser."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(
        handle="@anthropic", channel_id="anthropic",
        last_id="oldvid", last_pub="2026-05-01T00:00:00+00:00",
        platform="instagram",
    )
    fake_videos = [_ChannelVideo(
        video_id="reel1", url="https://www.instagram.com/p/reel1/",
        title="A new reel", duration_sec=42,
        published=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )]

    captured: dict = {}

    def fake_fetch(url, *, cookies_file=None, limit=30, **kw):
        captured["url"] = url
        captured["cookies_file"] = cookies_file
        return fake_videos

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=fake_fetch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
            instagram_cookies_file="/tmp/ig.txt",
        )
    assert captured["cookies_file"] == "/tmp/ig.txt" or captured["cookies_file"] == "/tmp/tt.txt"


def test_username_change_surfaces_friendly_error(tmp_path: Path, capsys):
    """When yt-dlp reports 'user not found', the loop prints a hint and
    moves on without aborting the run."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, ChannelNotFoundError, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    ig_ch = _channel(
        handle="@ghost", channel_id="ghost",
        last_id="x", last_pub="2026-05-01T00:00:00+00:00",
        platform="instagram",
    )
    yt_ch = _channel(
        handle="@anthropic-ai", channel_id="UC_anth",
        last_id="x", last_pub="2026-05-01T00:00:00+00:00",
        platform="youtube",
    )
    yt_ids, yt_extract = _video_seam(("yt_new", "2026-05-11T00:00:00+00:00"))

    def fake_fetch(url, *, cookies_file=None, limit=30, **kw):
        raise ChannelNotFoundError("user does not exist")

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ig_ch, yt_ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=yt_ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=yt_extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=fake_fetch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch",
    ) as mock_batch, patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as mock_state, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
            instagram_cookies_file="/tmp/ig.txt",
        )
    # Batch ran with YT video only — IG was skipped, run continues.
    mock_batch.assert_called_once()
    # State advanced for the surviving YT channel, NOT for the broken IG one.
    # update_last_seen signature: (path, channel_id, video_id, published).
    state_targets = [call.args[1] for call in mock_state.call_args_list]
    assert "UC_anth" in state_targets
    assert "ghost" not in state_targets


def test_looks_like_channel_not_found_matches_common_signatures():
    from skills.neurolearn.subscribes.pipeline import (
        _looks_like_channel_not_found,
    )
    assert _looks_like_channel_not_found("ERROR: user not found")
    assert _looks_like_channel_not_found("HTTP Error 404: Not Found")
    assert _looks_like_channel_not_found("This account does not exist")
    assert _looks_like_channel_not_found("Private account, login required")
    # Real-world false-positive guard:
    assert not _looks_like_channel_not_found(
        "RuntimeError: ffmpeg crashed"
    )
    assert not _looks_like_channel_not_found("Quota exceeded")


def test_tiktok_channel_uses_yt_dlp_with_tiktok_cookies(tmp_path: Path):
    """TikTok routes the same as Instagram, but with its own cookies setting.
    Verifies the per-platform cookies plumbing doesn't cross-contaminate."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(
        handle="@duolingo", channel_id="@duolingo",
        last_id="x", last_pub="2026-05-01T00:00:00+00:00",
        platform="tiktok",
    )
    fake_videos = [_ChannelVideo(
        video_id="v1", url="https://www.tiktok.com/@duolingo/video/v1",
        title="A new short", duration_sec=30,
        published=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )]

    captured: dict = {}

    def fake_fetch(url, *, cookies_file=None, limit=30, **kw):
        captured["cookies_file"] = cookies_file
        return fake_videos

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=fake_fetch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
            instagram_cookies_file="/tmp/ig.txt",  # MUST NOT be used here
            tiktok_cookies_file="/tmp/tt.txt",
        )
    assert captured["cookies_file"] == "/tmp/ig.txt" or captured["cookies_file"] == "/tmp/tt.txt"


def test_tiktok_dedup_via_last_seen_video_id(tmp_path: Path):
    """For IG/TikTok the date window is bypassed — dedup is by
    last_seen_video_id. yt-dlp returns entries newest-first; we walk
    until we hit the previously-seen id and stop."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    ch = _channel(
        handle="@duolingo", channel_id="@duolingo",
        last_id="OLD_SEEN", last_pub=None,  # date doesn't exist for TT
        platform="tiktok",
    )
    # Newest first; OLD_SEEN was previously seen → only NEW1, NEW2 are fresh.
    fake_videos = [
        _ChannelVideo(video_id="NEW1", url="...", title="t1",
                      duration_sec=10, published=datetime.now(timezone.utc)),
        _ChannelVideo(video_id="NEW2", url="...", title="t2",
                      duration_sec=10, published=datetime.now(timezone.utc)),
        _ChannelVideo(video_id="OLD_SEEN", url="...", title="t3",
                      duration_sec=10, published=datetime.now(timezone.utc)),
        _ChannelVideo(video_id="OLDER", url="...", title="t4",
                      duration_sec=10, published=datetime.now(timezone.utc)),
    ]
    captured: dict = {}

    def capture_batch(*, targets, **kw):
        captured["targets"] = list(targets)
        return tmp_path / "batch"

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        return_value=fake_videos,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_batch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
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
    seen_ids = [t.video_id for t in captured["targets"]]
    assert seen_ids == ["NEW1", "NEW2"]  # OLD_SEEN stopped the scan


def test_platform_filter_restricts_to_one_platform(tmp_path: Path):
    """--platform tiktok updates ONLY TikTok channels, skipping YT and IG."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@yt", channel_id="UC_yt", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", platform="youtube"),
        _channel(handle="@ig", channel_id="ig", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", platform="instagram"),
        _channel(handle="@tt", channel_id="@tt", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", platform="tiktok"),
    ]
    fake_videos = [_ChannelVideo(
        video_id="v1", url="u", title="t", duration_sec=10,
        published=datetime.now(timezone.utc),
    )]

    fetch_calls: list[str] = []

    def fake_fetch(url, *, cookies_file=None, limit=30, **kw):
        fetch_calls.append(url)
        return fake_videos

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        side_effect=AssertionError("YouTube fetch must NOT fire: only TT in scope"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=fake_fetch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group=None, platform="tiktok",
            days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # Exactly one fetch call — for the TikTok channel.
    assert len(fetch_calls) == 1
    assert "tiktok" in fetch_calls[0].lower()


def test_platform_filter_combined_with_group(tmp_path: Path):
    """--platform tiktok --group ai → only TikTok channels in group 'ai'."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@tt1", channel_id="@tt1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00",
                 group="ai", platform="tiktok"),
        _channel(handle="@tt2", channel_id="@tt2", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00",
                 group="memes", platform="tiktok"),
        _channel(handle="@ig1", channel_id="ig1", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00",
                 group="ai", platform="instagram"),
    ]

    fetch_calls: list[str] = []

    def fake_fetch(url, *, cookies_file=None, limit=30, **kw):
        fetch_calls.append(url)
        return [_ChannelVideo(
            video_id="v1", url="u", title="t", duration_sec=10,
            published=datetime.now(timezone.utc),
        )]

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_via_yt_dlp",
        side_effect=fake_fetch,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "batch",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(
            subscribes_path=sub_path,
            group="ai", platform="tiktok",
            days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    # Only @tt1 matches: platform=tiktok AND group=ai. @tt2 wrong group,
    # @ig1 wrong platform.
    assert len(fetch_calls) == 1


def test_platform_filter_empty_intersection_returns_none(tmp_path: Path):
    """--platform tiktok with no TikTok channels in subscribes → no-op."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update,
    )
    sub_path = tmp_path / "subscribes.toml"
    channels = [
        _channel(handle="@yt", channel_id="UC_yt", last_id="x",
                 last_pub="2026-01-01T00:00:00+00:00", platform="youtube"),
    ]
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=channels,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=AssertionError("batch must NOT run when filter empty"),
    ):
        result = run_subscribes_update(
            subscribes_path=sub_path,
            group=None, platform="tiktok",
            days=None, since=None, until=None,
            match=None, filter_text=None,
            no_rss=False, yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            api_keys={}, batch_opts={},
        )
    assert result is None


# =============================================================================
# v0.17: shorts-aware routing — modes, cap, dedup, CLI override
# =============================================================================

def _short(vid: str, pub_iso: str = "2026-05-15T12:00:00+00:00",
           duration: int = 30):
    """Construct a _ChannelVideo as a Shorts entry would look post-fetch."""
    from skills.neurolearn.subscribes.pipeline import _ChannelVideo
    return _ChannelVideo(
        video_id=vid,
        url=f"https://www.youtube.com/shorts/{vid}",
        title=f"Short {vid}",
        duration_sec=duration,
        published=datetime.fromisoformat(pub_iso),
    )


def _channel_with_mode(mode: str = "auto", **kwargs):
    ch = _channel(**kwargs)
    ch.mode = mode
    return ch


def _common_pipeline_kwargs(tmp_path: Path) -> dict:
    """Boilerplate for run_subscribes_update calls in the v0.17 tests."""
    return dict(
        subscribes_path=tmp_path / "subscribes.toml",
        group=None, days=None, since=None, until=None,
        match=None, filter_text=None,
        no_rss=False, yes=True, no_analyze=True,
        prompt=None, prompt_file=None,
        analyze_backend="gemini", filter_backend="gemini",
        ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
        no_stdout=False, output_dir=str(tmp_path),
        api_keys={}, batch_opts={},
    )


def test_auto_mode_with_videos_does_not_fetch_shorts(tmp_path: Path):
    """auto + the /videos tab has entries in window → /shorts must NOT fire."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="auto", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    ids, extract = _video_seam(("v_new", "2026-05-12T00:00:00+00:00"))
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=AssertionError("shorts must NOT be fetched on auto when /videos has entries"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(**_common_pipeline_kwargs(tmp_path))


def test_auto_mode_falls_back_to_shorts_when_videos_empty(tmp_path: Path):
    """Headline v0.17 scenario: channel hasn't uploaded any full videos in
    the window — auto-mode pulls Shorts so the user doesn't miss what's
    actually new on the channel."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="auto", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=[],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        return_value=[_short("s1", "2026-05-12T00:00:00+00:00")],
    ) as shorts_mock, patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ) as state_mock, patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(**_common_pipeline_kwargs(tmp_path))
    shorts_mock.assert_called_once()
    state_mock.assert_called_once()
    assert state_mock.call_args.args[2] == "s1"


def test_videos_only_mode_never_fetches_shorts(tmp_path: Path):
    """videos-only must NOT fall back to /shorts even when RSS is empty —
    regression of pre-v0.17 behavior for users who opt out."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="videos-only", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=[],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=AssertionError("videos-only must never call /shorts"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        result = run_subscribes_update(**_common_pipeline_kwargs(tmp_path))
    assert result is None


def test_shorts_only_mode_skips_videos(tmp_path: Path):
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-only", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        side_effect=AssertionError("shorts-only must never fetch the /videos tab"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        return_value=[_short("s1", "2026-05-12T00:00:00+00:00")],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(**_common_pipeline_kwargs(tmp_path))


def test_shorts_and_videos_mode_merges_and_sorts_by_date(tmp_path: Path):
    """Mixed stream: both fetchers called, output sorted newest-first."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-and-videos", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    # Newest-first (the /videos walk relies on order); both inside window.
    video_ids, video_extract = _video_seam(
        ("v_new", "2026-05-14T00:00:00+00:00"),
        ("v_old", "2026-05-11T00:00:00+00:00"),
    )
    short_entries = [
        _short("s_mid", "2026-05-13T00:00:00+00:00"),
    ]
    captured: dict = {}

    def capture_targets(*, targets, **kw):
        captured["video_ids"] = [t.video_id for t in targets]
        return tmp_path / "out"

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=video_ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=video_extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        return_value=short_entries,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_targets,
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(**_common_pipeline_kwargs(tmp_path))
    # Newest-first across the merged stream: v_new (14) → s_mid (13) → v_old (11)
    assert captured["video_ids"] == ["v_new", "s_mid", "v_old"]


def test_shorts_and_videos_mode_dedups_shared_id(tmp_path: Path):
    """If the same id appears in both streams (defensive — YouTube rarely
    surfaces a video on both tabs), keep one entry, not two."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-and-videos", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    captured: dict = {}

    def capture_targets(*, targets, **kw):
        captured["video_ids"] = [t.video_id for t in targets]
        return tmp_path / "out"

    dup_ids, dup_extract = _video_seam(("dup", "2026-05-12T00:00:00+00:00"))
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=dup_ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=dup_extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        return_value=[_short("dup", "2026-05-12T00:00:00+00:00")],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_targets,
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        run_subscribes_update(**_common_pipeline_kwargs(tmp_path))
    assert captured["video_ids"] == ["dup"]


def test_cli_override_mode_beats_stored_mode(tmp_path: Path):
    """Channel stored as shorts-only; cli_override_mode='videos-only' on
    this call should suppress /shorts and fetch the /videos tab only."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-only", last_id="oldvid",
        last_pub="2026-05-10T00:00:00+00:00",
    )
    ov_ids, ov_extract = _video_seam(("v_new", "2026-05-12T00:00:00+00:00"))
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._list_video_ids",
        return_value=ov_ids,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._extract_video_metadata",
        side_effect=ov_extract,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=AssertionError("CLI override videos-only must skip /shorts"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        kw = _common_pipeline_kwargs(tmp_path)
        kw["cli_override_mode"] = "videos-only"
        run_subscribes_update(**kw)


def test_pipeline_passes_cap_to_fetch_shorts(tmp_path: Path):
    """v0.17.1: cap enforcement moved INTO _fetch_shorts. The pipeline
    just forwards the cap and an in-window predicate and preserves the
    fetcher's already-newest-first, already-capped output verbatim."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-only", last_id="oldvid",
        last_pub="2026-05-09T00:00:00+00:00",
    )
    returned_shorts = [
        _short("s7", "2026-05-17T00:00:00+00:00"),
        _short("s6", "2026-05-16T00:00:00+00:00"),
        _short("s5", "2026-05-15T00:00:00+00:00"),
    ]
    captured: dict = {}
    fetch_calls: list[dict] = []

    def capture_targets(*, targets, **kw):
        captured["video_ids"] = [t.video_id for t in targets]
        return tmp_path / "out"

    def fake_fetch_shorts(channel_url, **kwargs):
        fetch_calls.append(kwargs)
        return returned_shorts

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=fake_fetch_shorts,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_targets,
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        kw = _common_pipeline_kwargs(tmp_path)
        kw["cli_override_mode"] = "shorts-only"
        kw["shorts_cap"] = 3
        run_subscribes_update(**kw)
    assert captured["video_ids"] == ["s7", "s6", "s5"]
    assert fetch_calls[0]["cap"] == 3
    assert callable(fetch_calls[0]["in_window_fn"])


def test_pipeline_passes_cap_zero_to_fetch_shorts(tmp_path: Path):
    """cap=0 forwarded as-is; downstream applies no second cap."""
    from skills.neurolearn.subscribes.pipeline import run_subscribes_update
    ch = _channel_with_mode(
        mode="shorts-only", last_id="oldvid",
        last_pub="2026-05-09T00:00:00+00:00",
    )
    returned = [_short(f"s{i}", f"2026-05-{10 + i:02d}T00:00:00+00:00")
                for i in range(7, 0, -1)]  # newest-first, 7 entries
    captured: dict = {}
    fetch_calls: list[dict] = []

    def capture_targets(*, targets, **kw):
        captured["count"] = len(targets)
        return tmp_path / "out"

    def fake_fetch_shorts(channel_url, **kwargs):
        fetch_calls.append(kwargs)
        return returned

    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=fake_fetch_shorts,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        side_effect=capture_targets,
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        kw = _common_pipeline_kwargs(tmp_path)
        kw["cli_override_mode"] = "shorts-only"
        kw["shorts_cap"] = 0
        run_subscribes_update(**kw)
    assert captured["count"] == 7
    assert fetch_calls[0]["cap"] == 0


# --- _fetch_shorts internals: early-exit walk (v0.17.1) ---

def test_fetch_shorts_stops_at_first_out_of_window():
    """Newest-first walk: the first short out of window stops the walk —
    subsequent IDs (older) must NOT be extracted. This is the headline
    speedup of v0.17.1."""
    from skills.neurolearn.subscribes import pipeline as pl
    extracted: list[str] = []

    def fake_extract(vid, *, cookies_file=None):
        extracted.append(vid)
        if vid == "s1":
            return _short("s1", "2026-05-20T00:00:00+00:00")
        return _short(vid, "2026-04-10T00:00:00+00:00")

    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with patch.object(pl, "_list_short_ids", return_value=["s1", "s2", "s3"]), \
         patch.object(pl, "_extract_short_metadata", side_effect=fake_extract):
        result = pl._fetch_shorts(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: dt >= cutoff,
            cap=5,
        )
    assert extracted == ["s1", "s2"]  # s3 was never touched
    assert [e.video_id for e in result] == ["s1"]


def test_fetch_shorts_stops_at_cap_hit():
    """Walk stops once cap entries collected — saves N-cap extracts on
    an active shorts channel."""
    from skills.neurolearn.subscribes import pipeline as pl
    extracted: list[str] = []

    def fake_extract(vid, *, cookies_file=None):
        extracted.append(vid)
        return _short(vid, "2026-05-20T00:00:00+00:00")

    with patch.object(pl, "_list_short_ids",
                      return_value=["a", "b", "c", "d", "e"]), \
         patch.object(pl, "_extract_short_metadata", side_effect=fake_extract):
        result = pl._fetch_shorts(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: True,
            cap=3,
        )
    assert extracted == ["a", "b", "c"]  # never touched d, e
    assert [e.video_id for e in result] == ["a", "b", "c"]


def test_fetch_shorts_cap_zero_walks_until_window_miss():
    """cap=0 means 'take everything in window'; walk only stops on the
    first out-of-window entry."""
    from skills.neurolearn.subscribes import pipeline as pl
    sequence = {
        "s1": "2026-05-20T00:00:00+00:00",
        "s2": "2026-05-19T00:00:00+00:00",
        "s3": "2026-05-18T00:00:00+00:00",
        "s_old": "2025-01-01T00:00:00+00:00",
        "never": "2026-05-20T00:00:00+00:00",
    }
    extracted: list[str] = []

    def fake_extract(vid, *, cookies_file=None):
        extracted.append(vid)
        return _short(vid, sequence[vid])

    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with patch.object(pl, "_list_short_ids",
                      return_value=list(sequence.keys())), \
         patch.object(pl, "_extract_short_metadata", side_effect=fake_extract):
        result = pl._fetch_shorts(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: dt >= cutoff,
            cap=0,
        )
    assert extracted == ["s1", "s2", "s3", "s_old"]  # "never" not touched
    assert [e.video_id for e in result] == ["s1", "s2", "s3"]


def test_fetch_shorts_empty_id_list_returns_empty():
    """No /shorts tab at all → no extract calls."""
    from skills.neurolearn.subscribes import pipeline as pl
    with patch.object(pl, "_list_short_ids", return_value=[]), \
         patch.object(
             pl, "_extract_short_metadata",
             side_effect=AssertionError("must not be called with empty ids"),
         ):
        result = pl._fetch_shorts(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: True,
            cap=5,
        )
    assert result == []


def test_fetch_shorts_skips_per_id_download_errors():
    """A dead short (deleted / age-gated) must not abort the walk — skip
    and continue. Early-exit only fires on window-miss, not on errors."""
    from skills.neurolearn.subscribes import pipeline as pl
    from yt_dlp.utils import DownloadError

    def fake_extract(vid, *, cookies_file=None):
        if vid == "dead":
            raise DownloadError("video unavailable")
        return _short(vid, "2026-05-20T00:00:00+00:00")

    with patch.object(pl, "_list_short_ids",
                      return_value=["a", "dead", "c"]), \
         patch.object(pl, "_extract_short_metadata", side_effect=fake_extract):
        result = pl._fetch_shorts(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: True,
            cap=5,
        )
    assert [e.video_id for e in result] == ["a", "c"]


def test_ig_channel_ignores_mode_field(tmp_path: Path):
    """mode is YouTube-only — IG channels stay on the existing yt-dlp+
    instaloader path regardless of `mode`. Stored 'shorts-only' must not
    accidentally route an IG entry through the YouTube _fetch_shorts."""
    from skills.neurolearn.subscribes.pipeline import (
        run_subscribes_update, _ChannelVideo,
    )
    ch = _channel_with_mode(
        mode="shorts-only", handle="@ig", channel_id="ig_user",
        platform="instagram",
    )
    fake_entry = _ChannelVideo(
        video_id="igvid", url="https://www.instagram.com/p/igvid/",
        title="IG post", duration_sec=15,
        published=datetime(2026, 5, 14, tzinfo=timezone.utc),
    )
    with patch(
        "skills.neurolearn.subscribes.pipeline.load_subscribes",
        return_value=[ch],
    ), patch(
        "skills.neurolearn.subscribes.pipeline._fetch_instagram",
        return_value=[fake_entry],
    ) as ig_mock, patch(
        "skills.neurolearn.subscribes.pipeline._fetch_shorts",
        side_effect=AssertionError("IG channel must NOT hit _fetch_shorts"),
    ), patch(
        "skills.neurolearn.subscribes.pipeline._run_batch_pipeline",
        return_value=tmp_path / "out",
    ), patch(
        "skills.neurolearn.subscribes.pipeline.update_last_seen",
    ), patch(
        "skills.neurolearn.subscribes.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.neurolearn.subscribes.pipeline._append_history",
    ):
        kw = _common_pipeline_kwargs(tmp_path)
        kw["days"] = 30  # explicit window so IG date filter passes
        run_subscribes_update(**kw)
    ig_mock.assert_called_once()


# --- _fetch_videos internals: /videos tab early-exit walk (v0.20) ---

def _vid(vid, pub_iso="2026-05-15T12:00:00+00:00", duration=600):
    """Construct a _ChannelVideo as a /videos entry would look post-fetch."""
    from skills.neurolearn.subscribes.pipeline import _ChannelVideo
    return _ChannelVideo(
        video_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        title=f"Video {vid}",
        duration_sec=duration,
        published=datetime.fromisoformat(pub_iso),
    )


def test_list_video_ids_targets_the_videos_tab():
    """_list_video_ids must list the /videos tab (not /streams, not the
    bare channel) — that is the whole fix: regular uploads, no livestreams."""
    from skills.neurolearn.subscribes import pipeline as pl
    seen: dict = {}

    def fake_tab(channel_url, *, tab, limit=50, cookies_file=None):
        seen["tab"] = tab
        seen["url"] = channel_url
        return ["v1"]

    with patch.object(pl, "_list_tab_ids", side_effect=fake_tab):
        ids = pl._list_video_ids("https://www.youtube.com/@chan")
    assert ids == ["v1"]
    assert seen["tab"] == "videos"
    assert seen["url"] == "https://www.youtube.com/@chan"


def test_fetch_videos_stops_at_first_out_of_window():
    """Newest-first walk on /videos: the first out-of-window upload stops
    the walk — older IDs are never extracted (same early-exit as shorts)."""
    from skills.neurolearn.subscribes import pipeline as pl
    extracted: list[str] = []

    def fake_extract(vid, *, cookies_file=None):
        extracted.append(vid)
        if vid == "v1":
            return _vid("v1", "2026-05-20T00:00:00+00:00")
        return _vid(vid, "2026-04-10T00:00:00+00:00")

    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with patch.object(pl, "_list_video_ids", return_value=["v1", "v2", "v3"]), \
         patch.object(pl, "_extract_video_metadata", side_effect=fake_extract):
        result = pl._fetch_videos(
            "https://www.youtube.com/@chan",
            in_window_fn=lambda dt: dt >= cutoff,
        )
    assert extracted == ["v1", "v2"]  # v3 never touched
    assert [e.video_id for e in result] == ["v1"]


def test_fetch_videos_empty_id_list_returns_empty():
    """No /videos tab at all → no per-id extract calls."""
    from skills.neurolearn.subscribes import pipeline as pl
    with patch.object(pl, "_list_video_ids", return_value=[]), \
         patch.object(
             pl, "_extract_video_metadata",
             side_effect=AssertionError("must not extract with empty ids"),
         ):
        result = pl._fetch_videos(
            "https://www.youtube.com/@chan", in_window_fn=lambda dt: True,
        )
    assert result == []


def test_extract_video_vs_short_metadata_url_shape():
    """Same id, different recorded URL: /watch?v= for videos, /shorts/ for
    shorts. Both extract via watch?v= but record the canonical tab URL."""
    from skills.neurolearn.subscribes import pipeline as pl
    info = {"timestamp": 1747699200, "duration": 612, "title": "T"}
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = info
    with patch("yt_dlp.YoutubeDL", return_value=fake_ydl):
        v = pl._extract_video_metadata("abc")
        s = pl._extract_short_metadata("abc")
    assert v.url == "https://www.youtube.com/watch?v=abc"
    assert s.url == "https://www.youtube.com/shorts/abc"
    assert v.duration_sec == 612 and v.title == "T"


def test_backend_to_key_maps_valid_filter_backends_not_claude():
    """Regression: --filter-backend used to offer 'claude' → mapped to the
    never-wired 'anthropic' key and crashed run_analysis. The valid set is
    gemini/groq/openai/ollama (all identity); 'claude' is gone."""
    from skills.neurolearn.subscribes.pipeline import _backend_to_key
    for backend in ("gemini", "groq", "openai", "ollama"):
        assert _backend_to_key(backend) == backend
    with pytest.raises(KeyError):
        _backend_to_key("claude")
