"""Tests for subscribes.channel_resolver — url → channel_id via yt-dlp."""
from unittest.mock import patch

import pytest

from skills.neurolearn.subscribes.channel_resolver import (
    resolve_channel,
    ResolvedChannel,
)


@pytest.fixture(autouse=True)
def isolated_youtube_key(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")


def test_add_handle_resolves_and_stores_api_channel(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from skills.neurolearn.subscribes.cli import subscribes_group
    from skills.neurolearn.subscribes.store import load_subscribes

    def transport(url, params, headers, timeout):
        assert url.endswith("/channels")
        assert params["forHandle"] == "@creator"
        return 200, {"items": [{"id": "UC_creator", "snippet": {"title": "Creator"}}]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("skills.neurolearn.youtube_api._http_get", transport)
    path = tmp_path / "subscribes.toml"
    monkeypatch.setattr("skills.neurolearn.subscribes.cli.SUBSCRIBES_PATH", path)
    result = CliRunner().invoke(subscribes_group, ["add", "@creator"])

    assert result.exit_code == 0, result.output
    channel, = load_subscribes(path)
    assert channel.channel_id == "UC_creator"
    assert channel.handle == "@creator"
    assert channel.url == "https://www.youtube.com/@creator"


@pytest.mark.parametrize(("source", "lookup"), [
    ("youtube.com/@creator/videos?view=0", {"forHandle": "@creator"}),
    ("https://m.youtube.com/@%ED%95%9C%EA%B8%80/shorts", {"forHandle": "@한글"}),
    ("https://www.youtube.com/channel/UC_creator", {"id": "UC_creator"}),
    ("https://youtube.com/user/OldName", {"forUsername": "OldName"}),
])
def test_channel_urls_resolve_via_api(monkeypatch, source, lookup):
    def transport(url, params, headers, timeout):
        assert url.endswith("/channels")
        assert lookup.items() <= params.items()
        return 200, {"items": [{"id": "UC_creator", "snippet": {
            "title": "Creator", "customUrl": "@official",
        }}]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("skills.neurolearn.youtube_api._http_get", transport)
    with patch("skills.neurolearn.subscribes.channel_resolver._extract_flat",
               side_effect=AssertionError("unexpected yt-dlp fallback")):
        channel = resolve_channel(source)
    assert channel == ResolvedChannel("https://www.youtube.com/@official", "@official",
                                      "UC_creator", "Creator")


@pytest.mark.parametrize("source", [
    "https://youtu.be/dQw4w9WgXcQ?t=20",
    "https://www.youtube.com/watch?list=PL_xyz&v=dQw4w9WgXcQ",
    "https://m.youtube.com/shorts/dQw4w9WgXcQ",
    "youtube.com/live/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_video_resolves_to_its_owning_channel(monkeypatch, source):
    def transport(url, params, headers, timeout):
        assert url.endswith("/videos") and params["id"] == "dQw4w9WgXcQ"
        return 200, {"items": [{"id": "dQw4w9WgXcQ", "snippet": {
            "title": "Video title", "channelId": "UC_creator", "channelTitle": "Creator",
        }}]}

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("skills.neurolearn.youtube_api._http_get", transport)
    with patch("skills.neurolearn.subscribes.channel_resolver._extract_flat",
               side_effect=AssertionError("unexpected yt-dlp fallback")):
        channel = resolve_channel(source)
    assert channel == ResolvedChannel("https://www.youtube.com/channel/UC_creator", None,
                                      "UC_creator", "Creator")


def test_unknown_api_handle_is_channel_not_found(monkeypatch):
    from skills.neurolearn.subscribes.pipeline import ChannelNotFoundError

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("skills.neurolearn.youtube_api._http_get",
                        lambda *args: (200, {"items": []}))
    with patch("skills.neurolearn.subscribes.channel_resolver._extract_flat",
               side_effect=AssertionError("a confirmed miss must not fall back")):
        with pytest.raises(ChannelNotFoundError, match="Channel not found"):
            resolve_channel("https://www.youtube.com/@unknown")


def test_new_bare_handle_input_can_use_keyless_fallback():
    with patch("skills.neurolearn.subscribes.channel_resolver._extract_flat",
               return_value={"channel_id": "UC_legacy", "channel": "Legacy"}):
        channel = resolve_channel("@legacy")
    assert channel == ResolvedChannel("https://www.youtube.com/@legacy", "@legacy",
                                      "UC_legacy", "Legacy")


@pytest.mark.parametrize(("status", "body"), [
    (403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}),
    (503, {"error": {"message": "unavailable"}}),
    (200, {}),
    (200, {"items": [{"snippet": {"channelTitle": "Creator"}}]}),
])
def test_failed_video_lookup_uses_the_original_video_and_channel_fallback(
    monkeypatch, capsys, status, body,
):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("skills.neurolearn.youtube_api._http_get",
                        lambda *args: (status, body))
    channel_url = "https://www.youtube.com/@from_video"
    with patch("skills.neurolearn.subscribes.channel_resolver._extract_flat", side_effect=[
        {"channel_url": channel_url}, {"channel_id": "UC_fallback", "channel": "Fallback"},
    ]):
        channel = resolve_channel("https://youtu.be/dQw4w9WgXcQ")
    assert channel == ResolvedChannel(channel_url, "@from_video", "UC_fallback", "Fallback")
    assert capsys.readouterr().err.count("Falling back to yt-dlp") == 1


def test_resolve_handle_url():
    fake = {
        "channel_id": "UC_abc123",
        "channel": "Anthropic AI",
        "uploader": "Anthropic AI",
    }
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
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
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/channel/UC_xyz")
    assert out.channel_id == "UC_xyz"


def test_resolve_strips_trailing_slash():
    fake = {"channel_id": "UC_a", "channel": "A"}
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@A/")
    assert out.url == "https://www.youtube.com/@A"


def test_resolve_extracts_handle_from_url():
    """If yt-dlp doesn't give us a handle, parse it from the URL."""
    fake = {"channel_id": "UC_a", "channel": "TestChannel"}
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel("https://www.youtube.com/@SomeHandle")
    assert out.handle == "@SomeHandle"


def test_resolve_no_channel_id_raises():
    fake = {"channel": "weird"}  # no channel_id
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        with pytest.raises(ValueError, match="channel_id"):
            resolve_channel("https://www.youtube.com/@X")


def test_resolve_channel_id_falls_back_to_id_field():
    """Some channel pages leave `channel_id` null but expose the UC... id in
    the top-level `id` field — resolve must use it instead of failing."""
    fake = {
        "channel_id": None,
        "id": "UC2FrPwNcXZof5PCZRzAQGVw",
        "channel": "Path of Exile 2 | PoE News",
    }
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        out = resolve_channel(
            "https://www.youtube.com/channel/UC2FrPwNcXZof5PCZRzAQGVw"
        )
    assert out.channel_id == "UC2FrPwNcXZof5PCZRzAQGVw"


def test_resolve_id_fallback_ignores_non_uc_id():
    """A non-channel `id` (e.g. a video id) must NOT be mistaken for a
    channel id — only UC...-shaped ids qualify for the fallback."""
    fake = {"channel_id": None, "id": "dQw4w9WgXcQ", "channel": "x"}
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        return_value=fake,
    ):
        with pytest.raises(ValueError, match="channel_id"):
            resolve_channel("https://www.youtube.com/@X")


# === v0.8: platform detection + IG / TikTok resolvers ===


def test_detect_platform_youtube():
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert detect_platform("https://www.youtube.com/@anthropic-ai") == "youtube"
    assert detect_platform("https://www.youtube.com/channel/UC_abc") == "youtube"
    assert detect_platform("https://www.youtube.com/c/Anthropic") == "youtube"
    assert detect_platform("https://www.youtube.com/user/oldname") == "youtube"


def test_detect_platform_instagram():
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert detect_platform("https://www.instagram.com/anthropic/") == "instagram"
    assert detect_platform("https://instagram.com/example") == "instagram"


def test_detect_platform_rejects_instagram_post_urls():
    """Profile detector must not match /p/, /reel/, /tv/."""
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert detect_platform("https://www.instagram.com/p/ABC123/") is None
    assert detect_platform("https://www.instagram.com/reel/XYZ/") is None
    assert detect_platform("https://www.instagram.com/tv/abc/") is None
    assert detect_platform("https://www.instagram.com/reels/abc/") is None


def test_detect_platform_tiktok():
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert detect_platform("https://www.tiktok.com/@duolingo") == "tiktok"
    assert detect_platform("https://www.tiktok.com/@example/") == "tiktok"


def test_detect_platform_rejects_tiktok_video_urls():
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert (
        detect_platform("https://www.tiktok.com/@user/video/12345") is None
    )


def test_detect_platform_unknown_returns_none():
    from skills.neurolearn.subscribes.channel_resolver import detect_platform
    assert detect_platform("https://vimeo.com/user12345") is None
    assert detect_platform("https://twitter.com/anthropic") is None
    assert detect_platform("not even a url") is None


def test_resolve_instagram_profile():
    """Instagram resolution must NOT hit yt-dlp — we use the username as id."""
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        side_effect=AssertionError("yt-dlp must not be called for IG"),
    ):
        out = resolve_channel("https://www.instagram.com/anthropic/")
    assert out.platform == "instagram"
    assert out.channel_id == "anthropic"
    assert out.handle == "@anthropic"
    assert out.url == "https://www.instagram.com/anthropic"


def test_resolve_tiktok_profile():
    with patch(
        "skills.neurolearn.subscribes.channel_resolver._extract_flat",
        side_effect=AssertionError("yt-dlp must not be called for TikTok"),
    ):
        out = resolve_channel("https://www.tiktok.com/@duolingo")
    assert out.platform == "tiktok"
    assert out.channel_id == "@duolingo"
    assert out.handle == "@duolingo"
    assert out.url == "https://www.tiktok.com/@duolingo"


def test_resolve_unrecognized_url_raises():
    with pytest.raises(ValueError, match="doesn't look like"):
        resolve_channel("https://vimeo.com/user12345")
