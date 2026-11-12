"""Statistics in the public transcription outputs, using an offline videos.list."""
import json

import pytest
from click.testing import CliRunner

from skills.neurolearn import youtube_api
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.transcribe import cli
from skills.neurolearn.utils.output_writer import Segment
from skills.neurolearn.utils.resolver import ResolvedTarget


@pytest.fixture
def run_transcription(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('onboarding_complete = true\n', encoding="utf-8")
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", config)
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-test-key")
    result = TranscriptionResult(
        "Transcript.", [Segment(0, 1, "Transcript.")], "en", "subtitles", 1,
    )
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline", lambda *a, **kw: result)

    def run(command, targets, *flags):
        monkeypatch.setattr("skills.neurolearn.transcribe.resolve", lambda *a, **kw: (targets, []))
        out_dir = tmp_path / "out"
        result = CliRunner().invoke(cli, [
            command, targets[0].url, "--output-dir", str(out_dir), "--preset", "eco", *flags,
        ], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        manifest = next(out_dir.rglob("manifest.json"))
        videos = json.loads(manifest.read_text(encoding="utf-8"))["videos"]
        return videos, manifest.parent, result.output

    return run


def target(video_id, url=None):
    return ResolvedTarget(url or f"https://youtu.be/{video_id}", "Demo", None, 1, None, "inline", video_id)


def test_single_video_writes_statistics_to_manifest_and_json_and_displays_them(
    run_transcription, monkeypatch,
):
    video = target("abcdefghijk", "https://m.youtube.com/live/abcdefghijk")
    monkeypatch.setattr(youtube_api, "_http_get", lambda *a: (200, {"items": [{
        "id": video.video_id, "statistics": {"viewCount": "12", "likeCount": "0"},
    }]}))

    videos, folder, output = run_transcription("transcribe", [video], "--output-format", "json")

    expected = {"view_count": 12, "like_count": 0, "comment_count": None}
    assert videos[0]["statistics"] == expected
    artifact = json.loads((folder / videos[0]["files"]["json"]).read_text(encoding="utf-8"))
    assert artifact["statistics"] == expected
    assert "Views: 12" in output and "Likes: 0" in output and "Comments: —" in output


def test_batch_batches_only_youtube_videos_and_writes_their_statistics(
    run_transcription, monkeypatch,
):
    youtube_ids = [f"v{i:010d}" for i in range(51)]
    requests = []

    def transport(url, params, headers, timeout):
        ids = params["id"].split(",")
        requests.append(ids)
        return 200, {"items": [{"id": vid, "statistics": {
            "viewCount": str(100 + i), "likeCount": "0", "commentCount": "1",
        }} for i, vid in enumerate(ids)]}

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    foreign = target(youtube_ids[0], "https://example.org/video?url=https://youtu.be/v0000000000")
    targets = [target(vid) for vid in youtube_ids] + [foreign]
    videos, folder, _ = run_transcription("batch", targets)

    assert requests == [youtube_ids[:50], youtube_ids[50:]]
    assert videos[0]["statistics"]["view_count"] == 100
    assert videos[1]["statistics"]["view_count"] == 101
    assert videos[-2]["statistics"]["like_count"] == 0
    assert "statistics" not in videos[-1]
    combined = (folder / "combined.md").read_text(encoding="utf-8")
    assert combined.count("Views:") == 51
    assert "Views: 101" in combined


@pytest.mark.parametrize("command", ["transcribe", "batch"])
@pytest.mark.parametrize("failure", ["no-key", "quota", "malformed"])
def test_unavailable_statistics_preserve_transcription_silently(
    run_transcription, monkeypatch, command, failure,
):
    if failure == "no-key":
        monkeypatch.delenv("YOUTUBE_API_KEY")

    def transport(*args):
        if failure == "no-key":
            pytest.fail("unexpected HTTP request without a key")
        if failure == "quota":
            return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        return 200, {"items": [{"id": "abcdefghijk", "statistics": None}]}

    monkeypatch.setattr(youtube_api, "_http_get", transport)
    videos, folder, output = run_transcription(command, [target("abcdefghijk")])

    assert videos[0]["status"] == "ok"
    assert "statistics" not in videos[0]
    assert "Transcript." in (folder / videos[0]["files"]["txt"]).read_text(encoding="utf-8")
    assert "views:" not in output.lower()
    assert "youtube api" not in output.lower()
    assert "quota" not in output.lower()
