"""Daily quota observed at the HTTP boundary and in doctor."""
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from skills.neurolearn import config, transcribe, youtube_api, youtube_quota


@pytest.fixture
def quota_home(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.setattr(transcribe, "CONFIG_PATH", path)
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    return path


@pytest.fixture
def requests(monkeypatch):
    calls = []

    def transport(url, params, headers, timeout):
        calls.append(url.rsplit("/", 1)[-1])
        return 200, {"items": []}

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    return calls


def doctor(*args):
    result = CliRunner().invoke(transcribe.cli, ["doctor", *args])
    assert result.exit_code == 0, result.exception
    return result.output


def test_doctor_shows_local_spend_for_each_bucket(quota_home, requests):
    youtube_api.check_key()
    youtube_api.api_get("videos", {})
    youtube_api.api_get("search", {})
    quota = json.loads(doctor("--json"))["youtube"]["quota"]
    assert quota["general"] == {"used": 2, "limit": 10_000, "exhausted": False}
    assert quota["search"] == {"used": 1, "limit": 100, "exhausted": False}
    output = doctor()
    assert "General units: 2/10000" in output
    assert "Search calls: 1/100" in output


def test_configured_limits_block_only_the_exhausted_bucket(quota_home, requests):
    runner = CliRunner()
    for key, value in [("youtube-daily-units", "2"), ("youtube-daily-searches", "1")]:
        result = runner.invoke(transcribe.cli, ["config", "set", key, value])
        assert result.exit_code == 0, result.output
    youtube_api.api_get("search", {})
    with pytest.raises(youtube_api.QuotaExhausted):
        youtube_api.api_get("search", {})
    youtube_api.api_get("videos", {})
    youtube_api.api_get("channels", {})
    with pytest.raises(youtube_api.QuotaExhausted):
        youtube_api.api_get("videos", {})
    assert requests == ["search", "videos", "channels"]
    quota = json.loads(doctor("--json"))["youtube"]["quota"]
    assert quota["general"] == {"used": 2, "limit": 2, "exhausted": True}
    assert quota["search"] == {"used": 1, "limit": 1, "exhausted": True}


def test_google_exhausts_only_its_bucket_without_inflating_spend(quota_home, monkeypatch):
    calls = []

    def transport(url, params, headers, timeout):
        calls.append(url.rsplit("/", 1)[-1])
        if calls == ["search"]:
            return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        return 200, {"items": []}

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    for _ in range(2):
        with pytest.raises(youtube_api.QuotaExhausted):
            youtube_api.api_get("search", {})
    youtube_api.check_key()
    assert calls == ["search", "i18nLanguages"]
    quota = json.loads(doctor("--json"))["youtube"]["quota"]
    assert quota["search"] == {"used": 1, "limit": 100, "exhausted": True}


def test_key_test_reports_unverified_when_local_limit_prevents_request(quota_home, requests):
    quota_home.write_text("[youtube]\ndaily_units = 0\n", encoding="utf-8")
    result = CliRunner().invoke(transcribe.cli, ["config", "test", "youtube"])
    assert result.exit_code == 5
    assert "key not verified" in result.output
    assert "key is valid" not in result.output
    assert requests == []


@pytest.mark.parametrize("midnight", ["2026-07-02T07:00:00+00:00", "2026-11-12T08:00:00+00:00"])
def test_buckets_reset_at_pacific_midnight(quota_home, requests, monkeypatch, midnight):
    boundary = datetime.fromisoformat(midnight)
    instant = boundary - timedelta(seconds=1)

    class Clock:
        @staticmethod
        def now(tz):
            return instant.astimezone(tz)

    monkeypatch.setattr(youtube_quota, "datetime", Clock)
    quota_home.write_text("[youtube]\ndaily_searches = 1\n", encoding="utf-8")
    youtube_api.api_get("search", {})
    with pytest.raises(youtube_api.QuotaExhausted):
        youtube_api.api_get("search", {})
    instant = boundary
    youtube_api.api_get("search", {})
    quota = json.loads(doctor("--json"))["youtube"]["quota"]
    assert quota["day"] == midnight[:10]
    assert quota["search"]["used"] == 1
    assert requests == ["search", "search"]


def _worker_call(path):
    # Spawn independent CLI-like processes sharing only the config directory.
    config.CONFIG_PATH = path
    youtube_api._http_get = lambda *args: (200, {"items": []})
    try:
        youtube_api.api_get("videos", {}, api_key="worker-key")
    except youtube_api.QuotaExhausted:
        return False
    return True


def test_concurrent_workers_share_the_same_limit(quota_home):
    quota_home.write_text("[youtube]\ndaily_units = 7\n", encoding="utf-8")
    with ProcessPoolExecutor(4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_worker_call, [quota_home] * 28))
    assert sum(results) == 7
    assert json.loads(doctor("--json"))["youtube"]["quota"]["general"]["used"] == 7


def test_unusable_counter_falls_back_without_sending_requests(quota_home, requests):
    (quota_home.parent / "youtube-quota.sqlite3").write_bytes(b"damaged")
    with pytest.raises(youtube_api.TransientFailure, match="quota"):
        youtube_api.check_key()
    assert requests == []
    assert "error" in json.loads(doctor("--json"))["youtube"]["quota"]
    assert "quota unavailable" in doctor().lower()


def test_invalid_quota_setting_cannot_silently_disable_the_cap(quota_home, requests):
    quota_home.write_text('[youtube]\ndaily_units = "none"\n', encoding="utf-8")
    with pytest.raises(youtube_api.TransientFailure, match="daily_units"):
        youtube_api.check_key()
    assert requests == []


def test_delayed_quota_error_does_not_block_the_new_day(quota_home, monkeypatch):
    before = datetime.fromisoformat("2026-07-02T06:59:59+00:00")
    after = before + timedelta(seconds=2)
    instant = before

    class Clock:
        @staticmethod
        def now(tz):
            return instant.astimezone(tz)

    def transport(url, params, headers, timeout):
        nonlocal instant
        if instant == before:
            instant = after
            return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        return 200, {"items": []}

    monkeypatch.setattr(youtube_quota, "datetime", Clock)
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    with pytest.raises(youtube_api.QuotaExhausted):
        youtube_api.check_key()
    youtube_api.check_key()
    assert json.loads(doctor("--json"))["youtube"]["quota"]["general"]["used"] == 1
