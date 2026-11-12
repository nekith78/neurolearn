"""Tests for the YouTube Data API client.

The only thing replaced is the module's single HTTP transport function
(`_http_get`). No network, no real key.
"""
from __future__ import annotations

import pytest

from skills.neurolearn import youtube_api
from skills.neurolearn.youtube_api import (
    CommentsDisabled,
    InvalidKey,
    NotConfigured,
    NotFound,
    QuotaExhausted,
    TransientFailure,
    YouTubeApiError,
)

FAKE_KEY = "AIzaFAKE-not-a-real-key-0123456789"


def _google_error(code: int, reason: str, message: str = "boom") -> dict:
    """Error body in the shape the Data API returns."""
    return {
        "error": {
            "code": code,
            "message": message,
            "errors": [{"message": message, "domain": "youtube", "reason": reason}],
        }
    }


class FakeTransport:
    """Stands in for `_http_get`: records calls, replays one response."""

    def __init__(self, status: int = 200, body=None, raises: Exception | None = None):
        self.status = status
        self.body = {"items": []} if body is None else body
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, url, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        if self.raises is not None:
            raise self.raises
        return self.status, self.body


@pytest.fixture
def no_stored_key(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("skills.neurolearn.config.ENV_PATH", tmp_path / ".env")


def _install(monkeypatch, **kwargs) -> FakeTransport:
    fake = FakeTransport(**kwargs)
    monkeypatch.setattr(youtube_api, "_http_get", fake)
    return fake


class TestApiGet:
    def test_returns_the_response_body(self, monkeypatch):
        _install(monkeypatch, body={"items": [{"id": "abc"}]})
        assert youtube_api.api_get("videos", {"part": "id", "id": "abc"}, api_key=FAKE_KEY) == {
            "items": [{"id": "abc"}]
        }

    def test_key_travels_only_in_the_header(self, monkeypatch):
        fake = _install(monkeypatch)
        youtube_api.api_get("videos", {"part": "id", "id": "abc"}, api_key=FAKE_KEY)
        call = fake.calls[0]
        assert call["headers"]["X-goog-api-key"] == FAKE_KEY
        assert FAKE_KEY not in call["url"]
        assert FAKE_KEY not in str(call["params"])
        assert call["url"] == "https://www.googleapis.com/youtube/v3/videos"

    def test_uses_the_stored_key_when_none_is_passed(self, monkeypatch, no_stored_key):
        monkeypatch.setenv("YOUTUBE_API_KEY", FAKE_KEY)
        fake = _install(monkeypatch)
        youtube_api.api_get("videos", {"part": "id", "id": "abc"})
        assert fake.calls[0]["headers"]["X-goog-api-key"] == FAKE_KEY

    def test_no_key_is_not_configured_and_makes_no_request(self, monkeypatch, no_stored_key):
        fake = _install(monkeypatch)
        with pytest.raises(NotConfigured):
            youtube_api.api_get("videos", {"part": "id", "id": "abc"})
        assert fake.calls == []


class TestErrorMapping:
    @pytest.mark.parametrize(
        "status, reason, expected",
        [
            (400, "keyInvalid", InvalidKey),
            (400, "badRequest", YouTubeApiError),
            (401, "unauthorized", InvalidKey),
            (403, "accessNotConfigured", InvalidKey),
            (403, "forbidden", InvalidKey),
            (403, "quotaExceeded", QuotaExhausted),
            (403, "dailyLimitExceeded", QuotaExhausted),
            (403, "commentsDisabled", CommentsDisabled),
            (403, "rateLimitExceeded", TransientFailure),
            (404, "videoNotFound", NotFound),
            (404, "playlistNotFound", NotFound),
            (429, "rateLimitExceeded", TransientFailure),
            (500, "backendError", TransientFailure),
            (503, "backendError", TransientFailure),
        ],
    )
    def test_http_error_maps_to_typed_outcome(self, monkeypatch, status, reason, expected):
        _install(monkeypatch, status=status, body=_google_error(status, reason))
        with pytest.raises(expected) as exc:
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)
        assert type(exc.value) is expected
        assert exc.value.reason == reason

    def test_invalid_key_in_the_live_error_format(self, monkeypatch):
        """Body recorded from the live API: `errors` says badRequest, the
        real cause is only in `details`."""
        msg = "API key not valid. Please pass a valid API key."
        body = {
            "error": {
                "code": 400,
                "message": msg,
                "errors": [{"message": msg, "domain": "global", "reason": "badRequest"}],
                "status": "INVALID_ARGUMENT",
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                     "reason": "API_KEY_INVALID", "domain": "googleapis.com"},
                    {"@type": "type.googleapis.com/google.rpc.LocalizedMessage",
                     "locale": "en-US", "message": msg},
                ],
            }
        }
        _install(monkeypatch, status=400, body=body)
        with pytest.raises(InvalidKey):
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)

    def test_invalid_key_in_the_new_error_format(self, monkeypatch):
        """Google's current 400 body carries the reason only in `details`."""
        body = {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
                "details": [{"reason": "API_KEY_INVALID", "domain": "googleapis.com"}],
            }
        }
        _install(monkeypatch, status=400, body=body)
        with pytest.raises(InvalidKey):
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)

    def test_network_failure_is_transient(self, monkeypatch):
        _install(monkeypatch, raises=TransientFailure("connection refused"))
        with pytest.raises(TransientFailure):
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)

    def test_non_json_body_is_transient(self, monkeypatch):
        _install(monkeypatch, status=502, body="<html>Bad Gateway</html>")
        with pytest.raises(TransientFailure):
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)

    def test_every_error_is_a_youtube_api_error(self):
        for cls in (NotConfigured, InvalidKey, QuotaExhausted, NotFound,
                    CommentsDisabled, TransientFailure):
            assert issubclass(cls, YouTubeApiError)


class TestKeyNeverLeaks:
    def test_key_echoed_in_an_error_body_is_scrubbed(self, monkeypatch):
        body = _google_error(400, "keyInvalid", f"API key {FAKE_KEY} not valid")
        _install(monkeypatch, status=400, body=body)
        with pytest.raises(InvalidKey) as exc:
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)
        assert FAKE_KEY not in str(exc.value)
        assert FAKE_KEY not in repr(exc.value)

    def test_key_in_a_transport_failure_is_scrubbed(self, monkeypatch):
        _install(monkeypatch, raises=TransientFailure(f"timeout sending {FAKE_KEY}"))
        with pytest.raises(TransientFailure) as exc:
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)
        assert FAKE_KEY not in str(exc.value)
        assert FAKE_KEY not in repr(exc.value.__cause__)
        assert exc.value.__context__ is None or FAKE_KEY not in repr(exc.value.__context__)

    def test_key_in_a_non_json_body_is_scrubbed(self, monkeypatch):
        _install(monkeypatch, status=500, body=f"proxy error for {FAKE_KEY}")
        with pytest.raises(TransientFailure) as exc:
            youtube_api.api_get("videos", {"part": "id"}, api_key=FAKE_KEY)
        assert FAKE_KEY not in str(exc.value)


class TestCheckKey:
    def test_valid_key_passes_with_one_request(self, monkeypatch):
        fake = _install(monkeypatch)
        assert youtube_api.check_key(FAKE_KEY) is None
        assert len(fake.calls) == 1

    def test_invalid_key_raises_invalid_key(self, monkeypatch):
        _install(monkeypatch, status=400, body=_google_error(400, "keyInvalid"))
        with pytest.raises(InvalidKey):
            youtube_api.check_key(FAKE_KEY)

    def test_missing_key_raises_not_configured(self, monkeypatch, no_stored_key):
        _install(monkeypatch)
        with pytest.raises(NotConfigured):
            youtube_api.check_key()
