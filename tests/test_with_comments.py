"""Comment attachments and analysis through the public CLI."""
import json

import pytest
from click.testing import CliRunner

from skills.neurolearn import comments
from skills.neurolearn.backends.base import TranscriptionResult
from skills.neurolearn.transcribe import cli
from skills.neurolearn.utils.output_writer import Segment


VIDEO_ID = "abc_defghij"
URL = f"https://youtu.be/{VIDEO_ID}"


@pytest.fixture
def invoke(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("onboarding_complete = true\n", encoding="utf-8")
    monkeypatch.setattr("skills.neurolearn.transcribe.CONFIG_PATH", config)
    monkeypatch.setattr("skills.neurolearn.utils.downloader._extract_flat",
                        lambda url: {"id": url.rsplit("/", 1)[-1], "title": "A talk"})
    transcript = TranscriptionResult("A talk", [Segment(0, 1, "A talk")], "en", "subtitles", 1)
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline", lambda *a, **kw: transcript)

    def run(*args):
        result = CliRunner().invoke(cli, list(map(str, args)), catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return result.output

    return run


def sample(video_id, **kwargs):
    comment = comments.Comment("c1", "Viewer", "Great tutorial!", 13, None, False)
    return comments.CommentSample(video_id, [comment])


def test_transcribe_writes_comment_files_next_to_the_transcript(invoke, tmp_path, monkeypatch):
    monkeypatch.setattr(comments, "fetch_comments", sample)
    invoke("transcribe", URL, "--output-dir", tmp_path, "--preset", "eco", "--with-comments")
    video = json.loads((tmp_path / "manifest.json").read_text())["videos"][0]
    transcript = tmp_path / video["files"]["txt"]
    compact = tmp_path / video["files"]["comments"]
    assert compact == transcript.with_suffix(".comments.txt")
    assert "Great tutorial!" in compact.read_text()
    structured = tmp_path / video["files"]["comments_json"]
    assert json.loads(structured.read_text())["video_id"] == VIDEO_ID


def test_updating_a_sample_replaces_each_sidecar(tmp_path):
    import os

    paths = comments.write_comments(sample(VIDEO_ID), tmp_path, "talk")
    previous = [path.stat() for path in paths]
    assert comments.write_comments(sample(VIDEO_ID), tmp_path, "talk") == paths
    assert all(not os.path.samestat(old, path.stat()) for old, path in zip(previous, paths))


def test_batch_saves_comments_and_continues_after_disabled_and_non_youtube_sources(
    invoke, tmp_path, monkeypatch,
):
    from skills.neurolearn import youtube_api

    def get_comments(video_id, **kwargs):
        if video_id == VIDEO_ID:
            raise youtube_api.CommentsDisabled("disabled")
        return sample(video_id, **kwargs)

    monkeypatch.setattr(comments, "fetch_comments", get_comments)
    output = invoke("batch", URL, "https://youtu.be/12345678901", "https://example.org/a",
                    "https://example.org/b", "--output-dir", tmp_path, "--batch-name", "study",
                    "--preset", "eco", "--workers", "2", "--with-comments")
    videos = json.loads((tmp_path / "study/manifest.json").read_text())["videos"]
    assert [v["status"] for v in videos] == ["ok"] * 4
    saved = [v["files"]["comments"] for v in videos if "comments" in v["files"]]
    assert len(saved) == 1
    assert "Great tutorial!" in (tmp_path / "study" / saved[0]).read_text()
    assert output.count("Skipping comments") == 1
    assert f"Comments are disabled for {VIDEO_ID}" in output


def test_batch_skip_existing_backfills_comments_without_retranscribing(invoke, tmp_path, monkeypatch):
    monkeypatch.setattr(comments, "fetch_comments", sample)
    run_flags = ["--output-dir", tmp_path, "--preset", "eco"]
    invoke("batch", URL, "--batch-name", "original", *run_flags)
    original_dir = tmp_path / "original/videos"
    transcript, = original_dir.glob("*.txt")
    assert not list(original_dir.glob("*.comments.*"))
    monkeypatch.setattr("skills.neurolearn.transcribe.run_pipeline",
                        lambda *a, **kw: pytest.fail("transcribed an existing video"))
    invoke("batch", URL, "--batch-name", "retry", "--skip-existing", "--with-comments", *run_flags)
    assert "Great tutorial!" in transcript.with_suffix(".comments.txt").read_text()
    monkeypatch.setattr(comments, "fetch_comments", lambda *a, **kw: pytest.fail("refetched sample"))
    invoke("batch", URL, "--batch-name", "retry", "--skip-existing", "--with-comments", *run_flags)


@pytest.mark.parametrize("source_type", ["batch", "single_file"])
def test_analyze_fetches_missing_sample_for_selected_source_and_reuses_it(
    source_type, invoke, tmp_path, monkeypatch,
):
    batch_dir = tmp_path / "study"
    invoke("batch", URL, "https://youtu.be/12345678901", "--batch-name", "study",
           "--output-dir", tmp_path, "--preset", "eco")
    transcript = next((batch_dir / "videos").glob(f"*_{VIDEO_ID}.txt"))
    selection = [batch_dir, "--select", "1"] if source_type == "batch" else [transcript]
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    fetched = []

    def get_comments(video_id, **kwargs):
        fetched.append(video_id)
        return sample(video_id, **kwargs)

    monkeypatch.setattr(comments, "fetch_comments", get_comments)
    analyze_args = ["analyze", *selection, "--prompt", "What did the audience say?", "--backend", "ollama"]
    invoke(*analyze_args, "--with-comments")
    invoke(*analyze_args, "--with-comments")
    invoke(*analyze_args)
    assert fetched == [VIDEO_ID]
    assert all("Audience comments" in prompt and "Great tutorial!" in prompt for prompt in prompts[:2])
    assert "Great tutorial!" not in prompts[2]
    assert "Great tutorial!" in transcript.with_suffix(".comments.txt").read_text()


def test_batch_then_analyze_includes_collected_comments(invoke, tmp_path, monkeypatch):
    monkeypatch.setattr(comments, "fetch_comments", sample)
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    invoke("batch", URL, "--batch-name", "study", "--output-dir", tmp_path, "--preset", "eco",
           "--with-comments", "--then-analyze", "--analyze-backend", "ollama", "--prompt", "Review")
    assert len(prompts) == 1
    assert "Audience comments" in prompts[0] and "Great tutorial!" in prompts[0]


def test_analysis_repairs_a_mixed_comment_pair_before_using_it(invoke, tmp_path, monkeypatch):
    old = sample(VIDEO_ID)
    requests = []

    def fetch(video_id, options, **kwargs):
        requests.append(options.cap)
        current = sample(video_id)
        current.comments[0].text = "Current sample."
        current.requested_options = options
        return current

    monkeypatch.setattr(comments, "fetch_comments", fetch)
    invoke("transcribe", URL, "--output-dir", tmp_path, "--preset", "eco",
           "--with-comments", "--comment-count", "5")
    transcript, = tmp_path.glob(f"*{VIDEO_ID}.txt")
    old_compact, _ = comments.write_comments(old, tmp_path / "archive", "talk")
    transcript.with_suffix(".comments.txt").write_bytes(old_compact.read_bytes())
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    invoke("analyze", transcript, "--with-comments", "--comment-count", "5",
           "--prompt", "Review", "--backend", "ollama")
    assert requests == [5, 5]
    assert "Current sample." in prompts[0] and "Great tutorial!" not in prompts[0]


def test_loose_folder_never_selects_comment_sidecars_as_transcripts(invoke, tmp_path, monkeypatch):
    (tmp_path / "talk.txt").write_text("Transcript body.", encoding="utf-8")
    (tmp_path / "talk.comments.txt").write_text("From a viewer.", encoding="utf-8")
    (tmp_path / "talk.comments.json").write_text('{"comments":[]}', encoding="utf-8")
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    args = ["analyze", tmp_path, "--all", "--prompt", "Review", "--backend", "ollama"]
    invoke(*args)
    invoke(*args, "--with-comments")
    assert all(prompt.count("### [") == 1 for prompt in prompts)
    assert "From a viewer." not in prompts[0]
    assert prompts[1].count("From a viewer.") == 1


def test_analyze_reads_only_regular_sibling_comment_files(invoke, tmp_path, monkeypatch):
    (tmp_path / "talk.txt").write_text("Transcript body.", encoding="utf-8")
    (tmp_path / "original.comments.txt").write_text("Sample from another talk.", encoding="utf-8")
    link = tmp_path / "talk.comments.txt"
    try:
        link.symlink_to("original.comments.txt")
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    invoke("analyze", tmp_path / "talk.txt", "--with-comments", "--prompt", "Review", "--backend", "ollama")
    assert len(prompts) == 1
    assert "Sample from another talk." not in prompts[0]


def test_custom_comment_options_apply_on_all_attachment_commands_and_reuse_matching_samples(invoke, tmp_path, monkeypatch):
    from skills.neurolearn import youtube_api

    requests = []
    def transport(url, params, *_):
        if url.endswith("/videos"):
            return 200, {"items": []}
        assert url.endswith("/commentThreads")
        requests.append((params["maxResults"], params["order"]))
        return 200, {"items": []}

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", transport)
    selection = ["--with-comments", "--comment-count", "5", "--comment-order", "newest",
                 "--comment-full-replies", "--comment-markers"]
    invoke("transcribe", URL, "--output-dir", tmp_path / "single", "--preset", "eco", *selection)
    run = ["batch", URL, "--batch-name", "study", "--output-dir", tmp_path / "batches", "--preset", "eco"]
    invoke(*run, *selection)
    transcript, = (tmp_path / "batches/study/videos").glob(f"*_{VIDEO_ID}.txt")
    for path in (next((tmp_path / "single").glob("*.comments.json")), transcript.with_suffix(".comments.json")):
        data = json.loads(path.read_text())
        assert (data["order"], data["cap"], data["replies_mode"]) == ("newest", 5, "full")

    analyze = ["analyze", transcript, "--with-comments", "--comment-count", "8", "--comment-order", "likes",
               "--prompt", "Review", "--backend", "ollama"]
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    invoke(*analyze)
    invoke(*analyze)
    assert "order=likes cap=8" in prompts[-1]
    invoke(*run, "--skip-existing", *selection)
    invoke(*run, "--skip-existing", *selection)
    assert requests == [(5, "time"), (5, "time"), (8, "relevance"), (5, "time")]


def test_batch_refreshes_linked_sample_metadata(invoke, tmp_path, monkeypatch):
    from skills.neurolearn import youtube_api

    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_api, "_http_get", lambda *args: (200, {"items": []}))
    run = ["batch", URL, "--batch-name", "study", "--output-dir", tmp_path, "--preset", "eco",
           "--with-comments", "--comment-count", "5"]
    invoke(*run)
    structured, = (tmp_path / "study/videos").glob("*.comments.json")
    backup = structured.rename(structured.with_suffix(".backup"))
    try:
        structured.symlink_to(backup.name)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    invoke(*run, "--skip-existing")
    assert structured.is_file() and not structured.is_symlink()


@pytest.mark.parametrize("command", ["transcribe", "batch"])
def test_comment_write_failure_preserves_successful_transcript(command, invoke, tmp_path, monkeypatch):
    monkeypatch.setattr(comments, "fetch_comments", sample)

    def read_only_directory(*args):
        raise OSError("read-only destination")

    monkeypatch.setattr(comments, "write_comments", read_only_directory)
    output = invoke(command, URL, "--output-dir", tmp_path, "--preset", "eco", "--with-comments")
    assert "read-only destination" in output
    manifest, = tmp_path.rglob("manifest.json")
    video, = json.loads(manifest.read_text())["videos"]
    assert video["status"] == "ok" and "comments" not in video["files"]
    assert "A talk" in (manifest.parent / video["files"]["txt"]).read_text()


def test_parallel_batch_shares_fallback_notice(invoke, tmp_path, monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock

    ydl = Mock()
    ydl.extract_info.side_effect = lambda *a, **kw: {"comments": [], "comment_count": 0}
    monkeypatch.setattr(comments, "create_ytdlp", lambda options: nullcontext(ydl))
    output = invoke("batch", URL, "https://youtu.be/12345678901", "--output-dir", tmp_path,
                    "--preset", "eco", "--workers", "2", "--with-comments")
    assert output.count("Falling back to yt-dlp") == 1
    compact = list(tmp_path.rglob("*.comments.txt"))
    assert len(compact) == 2 and all("source=yt-dlp" in path.read_text() for path in compact)


def test_analyze_skips_foreign_source_even_when_a_same_named_sidecar_exists(
    invoke, tmp_path, monkeypatch,
):
    invoke("transcribe", "https://example.org/video", "--output-dir", tmp_path, "--preset", "eco")
    transcript, = tmp_path.glob("*.txt")
    transcript.with_suffix(".comments.txt").write_text("Unrelated old sample.", encoding="utf-8")
    prompts = []
    monkeypatch.setattr("skills.neurolearn.analyze.runner.run_analysis",
                        lambda prompt, **kw: prompts.append(prompt) or "Done.")
    output = invoke("analyze", transcript, "--with-comments", "--prompt", "Review", "--backend", "ollama")
    assert "Unrelated old sample." not in prompts[0]
    assert "Skipping comments" in output
