"""Update notifications and approval are observable through the CLI/pipeline."""
import json
from pathlib import Path
from unittest.mock import Mock

from click.testing import CliRunner


def test_check_updates_json_and_daily_attempt_cache(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    fetch = Mock(return_value={"yt-dlp": {"version": "2026.10.26", "requires_python": ">=3.11"}})
    monkeypatch.setattr(updates, "fetch_releases", fetch)
    first = updates.check_updates()
    second = updates.check_updates()
    assert first["packages"][0]["status"] == "update_available"
    assert second["packages"][0]["latest"] == "2026.10.26"
    assert fetch.call_count == 1
    from skills.neurolearn.transcribe import cli
    result = CliRunner().invoke(cli, ["check-updates", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["packages"][0]["installed"] == "2026.3.17"
    assert fetch.call_count == 2


def test_failed_attempt_is_cached_and_force_can_retry(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    fetch = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(updates, "fetch_releases", fetch)
    assert updates.check_updates()["packages"][0]["status"] == "unknown"
    assert updates.check_updates()["packages"][0]["status"] == "unknown"
    assert fetch.call_count == 1
    updates.check_updates(force=True)
    assert fetch.call_count == 2


def test_notice_only_once_then_weekly_and_stderr_only(tmp_path, monkeypatch, capsys):
    from skills.neurolearn import updates
    from skills.neurolearn.config import Config
    monkeypatch.delenv("NEUROLEARN_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    monkeypatch.setattr(updates, "fetch_releases", lambda _: {"yt-dlp": {"version": "2026.10.26"}})
    clock = [1_800_000_000.0]
    monkeypatch.setattr(updates.time, "time", lambda: clock[0])
    updates.maybe_notify_updates(Config())
    first = capsys.readouterr()
    assert first.out == ""
    assert "2026.10.26" in first.err
    updates.maybe_notify_updates(Config())
    assert capsys.readouterr().err == ""
    clock[0] += 86400
    updates.maybe_notify_updates(Config())
    assert capsys.readouterr().err == ""
    clock[0] += 6 * 86400
    updates.maybe_notify_updates(Config())
    assert "2026.10.26" in capsys.readouterr().err


def test_changed_update_notifies_and_environments_do_not_share_cache(tmp_path, monkeypatch, capsys):
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    fetch = Mock(return_value={"yt-dlp": {"version": "2026.10.26"}})
    monkeypatch.setattr(updates, "fetch_releases", fetch)
    updates.check_updates(notify=True)
    capsys.readouterr()
    fetch.return_value = {"yt-dlp": {"version": "2026.10.27"}}
    updates.check_updates(force=True, notify=True)
    assert "2026.10.27" in capsys.readouterr().err
    monkeypatch.setattr(updates.sys, "prefix", str(tmp_path / "another-env"))
    updates.check_updates()
    assert fetch.call_count == 3


def test_cache_damage_and_busy_lock_do_not_trigger_duplicate_checks(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    fetch = Mock(return_value={"yt-dlp": {"version": "2026.10.26"}})
    monkeypatch.setattr(updates, "fetch_releases", fetch)
    updates.check_updates()
    path = next((tmp_path / "updates").glob("*.json"))
    path.write_text('["bad state"]')
    updates.check_updates()
    assert fetch.call_count == 2
    path.with_suffix(".lock").touch()
    report = updates.check_updates(force=True)
    assert report["error"] == "Another update check is running"
    assert fetch.call_count == 2


def test_cache_permission_failure_still_allows_work(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.config import Config
    monkeypatch.delenv("NEUROLEARN_NO_UPDATE_CHECK", raising=False)
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    monkeypatch.setattr(updates, "CONFIG_DIR", blocked)
    fetch = Mock()
    monkeypatch.setattr(updates, "fetch_releases", fetch)
    updates.maybe_notify_updates(Config())
    fetch.assert_not_called()


def test_disabled_checks_and_config_roundtrip(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.config import Config, load_config, save_config
    monkeypatch.delenv("NEUROLEARN_NO_UPDATE_CHECK", raising=False)
    cfg = Config(update_check_enabled=False)
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    assert load_config(path).update_check_enabled is False
    check = Mock()
    monkeypatch.setattr(updates, "check_updates", check)
    updates.maybe_notify_updates(cfg)
    monkeypatch.setenv("NEUROLEARN_NO_UPDATE_CHECK", "1")
    updates.maybe_notify_updates(Config())
    check.assert_not_called()


def test_latest_rejects_prerelease_yanked_and_oversize(monkeypatch):
    import pytest
    from skills.neurolearn import updates
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(updates, "urlopen", Mock(return_value=response))
    for data in [
        {"info": {"version": "2.0rc1"}, "urls": [{"yanked": False}]},
        {"info": {"version": "2.0"}, "urls": [{"yanked": True}]},
    ]:
        response.read.return_value = json.dumps(data).encode()
        with pytest.raises(ValueError):
            updates.fetch_latest("yt-dlp")
    response.read.return_value = b"x" * (updates.MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        updates.fetch_latest("yt-dlp")


def test_python_incompatible_is_not_promised_as_installable(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "installed_versions", lambda: {"yt-dlp": "2026.3.17"})
    monkeypatch.setattr(updates, "fetch_releases", lambda _: {"yt-dlp": {
        "version": "2026.10.26", "requires_python": ">=99",
    }})
    assert updates.check_updates()["packages"][0]["status"] == "python_incompatible"


def _updater_setup(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    root = tmp_path / "project with spaces"
    root.mkdir()
    monkeypatch.setattr(updates, "update_project", lambda: root)
    monkeypatch.setattr(updates.shutil, "which", lambda _: "/tools/uv")
    monkeypatch.setattr(updates, "check_updates", lambda **_: {
        "environment": str(root / ".venv"), "packages": [], "error": None,
    })
    run = Mock()
    monkeypatch.setattr(updates.subprocess, "run", run)
    return root, run


def test_update_requires_approval_and_decline_installs_nothing(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.transcribe import cli
    _, run = _updater_setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["update-deps"])
    assert result.exit_code != 0
    assert "Approval required" in result.output
    run.assert_not_called()
    monkeypatch.setattr(updates, "_interactive", lambda: True)
    result = CliRunner().invoke(cli, ["update-deps"], input="n\n")
    assert result.exit_code == 0, result.output
    assert "Cancelled" in result.output
    run.assert_not_called()


def test_update_yes_targets_checkout_lock_then_preserves_extras(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.transcribe import cli
    root, run = _updater_setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["update-deps", "--yes"])
    assert result.exit_code == 0, result.output
    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0][:4] == ["/tools/uv", "lock", "--project", str(root)]
    assert commands[0][4:] == [part for name in updates.PACKAGES for part in ("--upgrade-package", name)]
    assert commands[1] == ["/tools/uv", "sync", "--project", str(root), "--inexact", "--locked"]
    assert all(call.kwargs["cwd"] == root for call in run.call_args_list)
    assert all(call.kwargs["env"]["UV_PROJECT_ENVIRONMENT"] == str(Path(updates.sys.prefix).resolve())
               for call in run.call_args_list)


def test_resolver_failure_never_runs_sync(tmp_path, monkeypatch):
    import subprocess
    from skills.neurolearn.transcribe import cli
    _, run = _updater_setup(tmp_path, monkeypatch)
    run.side_effect = subprocess.CalledProcessError(1, ["uv", "lock"])
    result = CliRunner().invoke(cli, ["update-deps", "--yes"])
    assert result.exit_code != 0
    assert "Dependency update failed" in result.output
    assert run.call_count == 1


def test_updater_refuses_other_environment(tmp_path, monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.transcribe import cli
    monkeypatch.setattr(updates.sys, "prefix", str(tmp_path / "unrelated-env"))
    run = Mock()
    monkeypatch.setattr(updates.subprocess, "run", run)
    result = CliRunner().invoke(cli, ["update-deps", "--yes"])
    assert result.exit_code != 0
    assert "requires NeuroLearn's uv checkout" in result.output
    run.assert_not_called()


def test_help_version_config_never_check_updates(monkeypatch):
    from skills.neurolearn import updates
    from skills.neurolearn.transcribe import cli
    check = Mock()
    monkeypatch.setattr(updates, "check_updates", check)
    for args in (["--help"], ["--version"], ["transcribe", "--help"], ["config", "--help"]):
        assert CliRunner().invoke(cli, args).exit_code == 0
    check.assert_not_called()


def test_pipeline_notifies_only_youtube_and_legacy_flag_cannot_install(tmp_path, monkeypatch):
    from skills.neurolearn import pipeline, updates
    from skills.neurolearn.config import Config
    from skills.neurolearn.utils.resolver import ResolvedTarget
    check = Mock()
    monkeypatch.setattr(updates, "maybe_notify_updates", check)
    monkeypatch.setattr(pipeline, "_transcribe_one", Mock())
    cfg = Config(yt_dlp_auto_update=True)
    local = tmp_path / "audio.mp3"
    local.write_bytes(b"audio")
    monkeypatch.setattr(pipeline, "download_audio", lambda *args, **kwargs: local)
    for url in [str(local), "https://example.org/audio.mp3", "https://youtu.be/abcdefghijk"]:
        target = ResolvedTarget(url=url, title="test", upload_date=None, duration_sec=1,
                                channel="", source="direct", video_id="abcdefghijk")
        pipeline.run_pipeline(target, cfg, backend_override="groq")
    assert check.call_count == 1


def test_cli_pipeline_event_notifies_once_without_http_or_install(tmp_path, monkeypatch):
    """Exercise CLI -> real pipeline -> real cached advisory -> transcript output."""
    import hashlib
    import os
    import time
    from skills.neurolearn import pipeline, transcribe, updates
    from skills.neurolearn.backends.base import TranscriptionResult
    from skills.neurolearn.config import Config, save_config
    from skills.neurolearn.utils.output_writer import Segment
    from skills.neurolearn.utils.resolver import ResolvedTarget

    monkeypatch.delenv("NEUROLEARN_NO_UPDATE_CHECK", raising=False)
    config_path = tmp_path / "config.toml"
    save_config(Config(onboarding_complete=True), config_path)
    monkeypatch.setattr(transcribe, "CONFIG_PATH", config_path)
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    key = hashlib.sha256(os.path.normcase(str(Path(updates.sys.prefix).resolve())).encode()).hexdigest()[:20]
    cache_dir = tmp_path / "updates"
    cache_dir.mkdir()
    (cache_dir / f"{key}.json").write_text(json.dumps({
        "attempted_at": time.time(),
        "results": {"yt-dlp": {"version": "2099.1.1", "requires_python": ">=3.11"}},
    }))
    network = Mock(side_effect=AssertionError("Cached advisory must not use HTTP"))
    install = Mock(side_effect=AssertionError("Advisory must never install"))
    monkeypatch.setattr(updates, "urlopen", network)
    monkeypatch.setattr(updates.subprocess, "run", install)

    # Metadata retrieval and transcription are the external IO boundaries.
    monkeypatch.setattr(transcribe, "resolve", lambda inputs, *_: ([ResolvedTarget(
        url=inputs[0], title="Hermes update-event fixture", upload_date=None,
        duration_sec=2, channel="fixture", source="single", video_id="abcdefghijk",
    )], []))
    result = TranscriptionResult(
        text="Hermes Agent fixture.", segments=[Segment(0, 2, "Hermes Agent fixture.")],
        language_detected="en", backend_name="subtitles_manual", duration_seconds=2,
    )
    backend = Mock()
    backend.transcribe.return_value = result
    monkeypatch.setattr(pipeline, "build_backend", lambda *_: backend)
    runner = CliRunner()
    args = ["transcribe", "https://youtu.be/abcdefghijk", "--backend", "subtitles",
            "--preset", "eco", "--vision-backend", "off", "--no-quality-check",
            "--output-dir", str(tmp_path / "transcripts")]
    first = runner.invoke(transcribe.cli, args)
    assert first.exit_code == 0, first.output
    assert "2099.1.1" in first.stderr
    assert "2099.1.1" not in first.stdout
    assert list((tmp_path / "transcripts").glob("*.srt"))
    second = runner.invoke(transcribe.cli, args)
    assert second.exit_code == 0, second.output
    assert "Dependency updates" not in second.stderr

    # A fresh pending notification still must not fire for local files/help.
    state_path = cache_dir / f"{key}.json"
    state = json.loads(state_path.read_text())
    state.pop("notification", None)
    state_path.write_text(json.dumps(state))
    local = tmp_path / "local.wav"
    local.write_bytes(b"fixture")
    local_args = list(args)
    local_args[1] = str(local)
    local_run = runner.invoke(transcribe.cli, local_args)
    assert local_run.exit_code == 0, local_run.output
    assert "Dependency updates" not in local_run.stderr
    help_run = runner.invoke(transcribe.cli, ["transcribe", "--help"])
    assert help_run.exit_code == 0
    assert "Dependency updates" not in help_run.stderr
    network.assert_not_called()
    install.assert_not_called()


def test_update_check_kills_slow_metadata_child(tmp_path, monkeypatch):
    import subprocess
    import sys
    import time
    from skills.neurolearn import updates
    monkeypatch.setattr(updates, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updates, "CHECK_TIMEOUT", 0.05)
    original_run = subprocess.run
    def slow_child(_command, **kwargs):
        return original_run([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
    monkeypatch.setattr(updates.subprocess, "run", slow_child)
    started = time.monotonic()
    report = updates.check_updates()
    assert time.monotonic() - started < 2
    assert all(row["status"] == "unknown" for row in report["packages"])
    # The timed-out attempt is cached, so another run never starts a child.
    monkeypatch.setattr(updates.subprocess, "run", Mock(side_effect=AssertionError("retried")))
    updates.check_updates()
