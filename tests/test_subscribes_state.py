"""Tests for subscribes.state — last-seen tracking per channel."""
from pathlib import Path

from skills.youtube_transcribe.subscribes.store import (
    Channel, add_channel, load_subscribes,
)
from skills.youtube_transcribe.subscribes.state import (
    needs_initial_run,
    update_last_seen,
    channels_without_state,
)


def _c(handle="@A", channel_id="UC_a", last_id=None, last_pub=None):
    return Channel(
        url=f"https://www.youtube.com/{handle}",
        handle=handle, channel_id=channel_id,
        group=None, added="2026-05-12",
        last_seen_video_id=last_id, last_seen_published=last_pub,
    )


def test_needs_initial_run_true_when_empty():
    assert needs_initial_run(_c(last_id=None)) is True


def test_needs_initial_run_false_when_state_present():
    assert needs_initial_run(_c(last_id="vid1", last_pub="2026-05-10T14:00:00Z")) is False


def test_channels_without_state_filters():
    chans = [
        _c(handle="@A", last_id="v"),
        _c(handle="@B", last_id=None),
        _c(handle="@C", last_id="v2"),
    ]
    missing = channels_without_state(chans)
    assert len(missing) == 1
    assert missing[0].handle == "@B"


def test_update_last_seen_writes_to_toml(tmp_path: Path):
    p = tmp_path / "sub.toml"
    add_channel(p, _c(handle="@A", channel_id="UC_a"))
    update_last_seen(p, "UC_a", "newvid", "2026-05-12T14:00:00Z")
    loaded = load_subscribes(p)
    assert loaded[0].last_seen_video_id == "newvid"
    assert loaded[0].last_seen_published == "2026-05-12T14:00:00Z"


def test_update_last_seen_missing_channel_silent(tmp_path: Path):
    """Updating state for an unknown channel is a no-op (no crash)."""
    p = tmp_path / "sub.toml"
    add_channel(p, _c(handle="@A", channel_id="UC_a"))
    # No exception:
    update_last_seen(p, "UC_NOTEXIST", "v", "2026-05-12T14:00:00Z")
    loaded = load_subscribes(p)
    assert loaded[0].last_seen_video_id is None
