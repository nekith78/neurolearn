"""Tests for subscribes.channel_resolver — url → channel_id via yt-dlp."""
from unittest.mock import patch

import pytest

from skills.youtube_transcribe.subscribes.channel_resolver import (
    resolve_channel,
    ResolvedChannel,
)


def test_resolve_handle_url():
    fake = {
        "channel_id": "UC_abc123",
        "channel": "Anthropic AI",
        "uploader": "Anthropic AI",
    }
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@AnthropicAI")
    assert out.channel_id == "UC_abc123"
    assert out.handle == "@AnthropicAI"
    assert out.url == "https://www.youtube.com/@AnthropicAI"


def test_resolve_canonical_url():
    fake = {
        "channel_id": "UC_xyz",
        "channel": "OpenAI",
    }
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/channel/UC_xyz")
    assert out.channel_id == "UC_xyz"


def test_resolve_strips_trailing_slash():
    fake = {"channel_id": "UC_a", "channel": "A"}
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@A/")
    assert out.url == "https://www.youtube.com/@A"


def test_resolve_extracts_handle_from_url():
    """If yt-dlp doesn't give us a handle, parse it from the URL."""
    fake = {"channel_id": "UC_a", "channel": "TestChannel"}
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@SomeHandle")
    assert out.handle == "@SomeHandle"


def test_resolve_no_channel_id_raises():
    fake = {"channel": "weird"}  # no channel_id
    with patch(
        "skills.youtube_transcribe.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        with pytest.raises(ValueError, match="channel_id"):
            resolve_channel("https://www.youtube.com/@X")
