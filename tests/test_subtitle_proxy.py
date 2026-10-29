"""Direct-first subtitle recovery through an explicitly configured proxy."""
from unittest.mock import Mock

import pytest
from youtube_transcript_api import IpBlocked, NoTranscriptFound

from skills.neurolearn.backends import subtitles as S
from skills.neurolearn.utils import youtube_proxy as P


@pytest.fixture(autouse=True)
def configured_proxy(monkeypatch):
    monkeypatch.setenv(P.PROXY_ENV, "http://test-user:test-password@proxy.invalid:80")


def test_direct_success_never_uses_proxy(monkeypatch):
    adapter = S._ApiAdapter()
    call = Mock(return_value=[{"text": "direct"}])
    monkeypatch.setattr(adapter, "_call_once", call)
    assert adapter.get_transcript("video") == [{"text": "direct"}]
    assert call.call_count == 1
    assert call.call_args.kwargs.get("proxy_url") is None


def test_blocked_direct_recovers_with_proxy(monkeypatch, capsys):
    adapter = S._ApiAdapter()
    call = Mock(side_effect=[IpBlocked("video"), [{"text": "recovered"}]])
    monkeypatch.setattr(adapter, "_call_once", call)
    assert adapter.get_transcript("video") == [{"text": "recovered"}]
    assert call.call_count == 2
    assert call.call_args.kwargs["proxy_url"] == P.get_proxy_url()
    output = capsys.readouterr().err
    assert "proxy succeeded" in output
    assert "test-password" not in output


def test_missing_captions_do_not_spend_proxy_traffic(monkeypatch):
    adapter = S._ApiAdapter()
    error = NoTranscriptFound("video", ["en"], {})
    call = Mock(side_effect=error)
    monkeypatch.setattr(adapter, "_call_once", call)
    with pytest.raises(NoTranscriptFound):
        adapter.get_transcript("video")
    assert call.call_count == 1


def test_unconfigured_proxy_keeps_existing_failure(monkeypatch):
    monkeypatch.setenv(P.PROXY_ENV, "")
    adapter = S._ApiAdapter()
    call = Mock(side_effect=IpBlocked("video"))
    monkeypatch.setattr(adapter, "_call_once", call)
    with pytest.raises(IpBlocked):
        adapter.get_transcript("video")
    assert call.call_count == 1


def test_proxy_attempts_bounded_and_errors_redacted(monkeypatch, capsys):
    from requests.exceptions import ProxyError
    adapter = S._ApiAdapter()
    call = Mock(side_effect=[IpBlocked("video"), ProxyError(P.get_proxy_url()),
                             ProxyError(P.get_proxy_url())])
    monkeypatch.setattr(adapter, "_call_once", call)
    with pytest.raises(P.ProxyFallbackFailed) as caught:
        adapter.get_transcript("video")
    assert call.call_count == 3
    assert "test-password" not in str(caught.value) + capsys.readouterr().err
    assert caught.value.__suppress_context__


def test_language_discovery_uses_same_fallback(monkeypatch):
    adapter = S._ApiAdapter()
    call = Mock(side_effect=[IpBlocked("video"), ["ru", "en"]])
    monkeypatch.setattr(adapter, "_call_once", call)
    assert adapter.list_language_codes("video") == ["ru", "en"]
    assert call.call_args.args[0] == "list"


def test_empty_http_200_caption_response_can_recover(monkeypatch):
    from xml.etree.ElementTree import ParseError
    adapter = S._ApiAdapter()
    call = Mock(side_effect=[ParseError("no element found"), [{"text": "captions"}]])
    monkeypatch.setattr(adapter, "_call_once", call)
    assert adapter.get_transcript("video") == [{"text": "captions"}]
    assert call.call_count == 2


def test_proxy_session_excludes_user_cookies_and_environment(monkeypatch):
    captured = {}
    session = P.TranscriptSession()
    monkeypatch.setattr(P, "TranscriptSession", lambda: session)
    cookie_loader = Mock(side_effect=AssertionError("must not read user cookies"))
    monkeypatch.setattr(S, "_build_authenticated_session", cookie_loader)
    class Api:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def fetch(self, video_id, languages):
            return []
    monkeypatch.setattr("youtube_transcript_api.YouTubeTranscriptApi", Api)
    S._ApiAdapter(cookies_file="private-cookies.txt")._call_once(
        "fetch", "video", ["en"], proxy_url=P.get_proxy_url(),
    )
    assert not captured["http_client"].trust_env
    assert not captured["http_client"].cookies
    assert captured["http_client"].headers["Connection"] == "close"
    assert captured["proxy_config"].retries_when_blocked == 0
    assert not cookie_loader.called


def test_proxy_failure_continues_to_existing_ytdlp(monkeypatch):
    from skills.neurolearn.utils.output_writer import Segment
    api = Mock()
    api.get_transcript.side_effect = P.ProxyFallbackFailed("Recovery failed")
    monkeypatch.setattr(S, "_get_transcript_api", lambda **kw: api)
    fallback = Mock(return_value=[Segment(0, 1, "existing fallback")])
    monkeypatch.setattr(S.SubtitlesBackend, "_fetch_via_yt_dlp", fallback)
    result = S.SubtitlesBackend().transcribe("https://youtu.be/9GpWELm3_XI", language="en")
    assert result.text == "existing fallback"
    assert fallback.call_count == 1


def test_proxy_url_from_secret_file_and_empty_env_override(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"{P.PROXY_ENV}=http://user:password@proxy.invalid:80\n")
    monkeypatch.setattr(P, "ENV_PATH", path)
    monkeypatch.delenv(P.PROXY_ENV)
    assert P.get_proxy_url() == "http://user:password@proxy.invalid:80"
    monkeypatch.setenv(P.PROXY_ENV, "")
    assert P.get_proxy_url() is None


def test_invalid_proxy_is_not_exposed(monkeypatch):
    monkeypatch.setenv(P.PROXY_ENV, "http://secret@host:badport")
    assert P.get_proxy_url() is None


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_default_proxy_port_is_valid(monkeypatch, scheme):
    value = f"{scheme}://user:password@proxy.invalid"
    monkeypatch.setenv(P.PROXY_ENV, value)
    assert P.get_proxy_url() == value


def test_request_has_socket_timeout(monkeypatch):
    call = Mock(return_value=object())
    monkeypatch.setattr("requests.Session.request", call)
    with P.TranscriptSession() as session:
        session.get("https://www.youtube.com/")
    assert call.call_args.kwargs["timeout"] == (10, 15)


@pytest.mark.parametrize("arguments", [["doctor"], ["doctor", "--json"]])
def test_doctor_reports_proxy_without_credentials(monkeypatch, arguments):
    from click.testing import CliRunner
    from skills.neurolearn.transcribe import cli
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0
    assert "proxy" in result.output
    assert "test-user" not in result.output
    assert "test-password" not in result.output
    assert "proxy.invalid" not in result.output
