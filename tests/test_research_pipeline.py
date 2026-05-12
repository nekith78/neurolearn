"""Tests for research.pipeline — full orchestration with mocked dependencies."""
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock


def _candidate(vid="v1", title="T", url=None, lang="en"):
    from skills.youtube_transcribe.research.source import SearchCandidate
    return SearchCandidate(
        video_id=vid, url=url or f"https://www.youtube.com/watch?v={vid}",
        title=title, channel="ch", duration_sec=300,
        upload_date=date(2026, 5, 11), source_language=lang,
    )


def test_pipeline_happy_path_invokes_components(tmp_path: Path):
    """Pipeline: translate → search → date-filter → match → llm-screen → batch → analyze."""
    from skills.youtube_transcribe.research.pipeline import run_research

    # Create the batch dir so .exists() returns True naturally — avoids
    # global pathlib.Path.exists mock which would break load_config.
    batch_dir = tmp_path / "batch_dir"
    batch_dir.mkdir()

    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "Claude features"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate("v1"), _candidate("v2")],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=batch_dir,
    ) as mock_batch, patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ) as mock_analyze, patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        result = run_research(
            query="Claude features",
            queries_by_language=None,
            languages=["en"],
            days=30, since=None, until=None,
            limit=20,
            match=None, filter_text=None,
            in_subscribes=False, group=None,
            yes=True, no_analyze=False,
            prompt="summarize", prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b",
            ollama_host="http://localhost:11434",
            no_stdout=False,
            output_dir=str(tmp_path),
            batch_name="research_test",
            api_keys={"gemini": "fake", "anthropic": None, "openai": None},
            batch_opts={},
        )

    assert result == batch_dir
    mock_batch.assert_called_once()
    mock_analyze.assert_called_once()


def test_pipeline_no_analyze_skips_analyze(tmp_path: Path):
    from skills.youtube_transcribe.research.pipeline import run_research
    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate()],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=tmp_path,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ) as mock_analyze, patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=True,  # ← analyze off
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    mock_analyze.assert_not_called()


def test_pipeline_no_results_after_filter_returns_none(tmp_path: Path):
    """If filters reduce candidates to zero, pipeline reports and returns None."""
    from skills.youtube_transcribe.research.pipeline import run_research
    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[],  # nothing found
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ):
        result = run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    assert result is None


def test_pipeline_in_subscribes_uses_rss(tmp_path: Path):
    """--in-subscribes flips source from search → subscribes channels via RSS."""
    from skills.youtube_transcribe.research.pipeline import run_research
    from skills.youtube_transcribe.subscribes.rss import RssEntry

    fake_chan = MagicMock(handle="@A", channel_id="UC_a", group=None,
                          last_seen_video_id=None)
    fake_entries = [
        RssEntry(video_id="rss1", url="u", title="From RSS",
                 channel_id="UC_a",
                 published=datetime(2026, 5, 11, tzinfo=timezone.utc)),
    ]

    with patch(
        "skills.youtube_transcribe.research.pipeline.load_subscribes",
        return_value=[fake_chan],
    ), patch(
        "skills.youtube_transcribe.research.pipeline.fetch_rss",
        return_value=fake_entries,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
    ) as mock_search, patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=tmp_path,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline.append_run",
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None,
            in_subscribes=True, group=None,  # ← cross-pollination
            yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )
    # search_multi_language NOT called when in_subscribes=True
    mock_search.assert_not_called()


def test_pipeline_status_partial_when_analyze_produced_no_file(tmp_path: Path):
    """If _run_then_analyze runs but didn't create analysis-*.md →
    history status='partial'."""
    from skills.youtube_transcribe.research.pipeline import run_research

    batch_dir = tmp_path / "no_analysis_batch"
    batch_dir.mkdir()
    # NOTE: don't create analysis-*.md inside → simulates LLM failure

    captured = {}

    def fake_append(**kwargs):
        captured.update(kwargs)

    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate()],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=batch_dir,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ), patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._append_history",
        side_effect=fake_append,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=False,            # ← analyze ON
            prompt="please", prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )

    assert captured.get("status") == "partial"


def test_pipeline_status_failed_when_batch_returned_none(tmp_path: Path):
    """If _run_batch_pipeline returns None → status='failed'."""
    from skills.youtube_transcribe.research.pipeline import run_research

    captured = {}

    def fake_append(**kwargs):
        captured.update(kwargs)

    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate()],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=None,                          # ← transcribe failed
    ), patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._append_history",
        side_effect=fake_append,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=True,
            prompt=None, prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )

    assert captured.get("status") == "failed"


def test_pipeline_status_ok_on_happy_path(tmp_path: Path):
    """Successful analyze (analysis-*.md present) → status='ok'."""
    from skills.youtube_transcribe.research.pipeline import run_research

    batch_dir = tmp_path / "good_batch"
    batch_dir.mkdir()
    (batch_dir / "analysis-2026-05-12-1400.md").write_text("ok", encoding="utf-8")

    captured = {}

    def fake_append(**kwargs):
        captured.update(kwargs)

    with patch(
        "skills.youtube_transcribe.research.pipeline.build_queries_per_language",
        return_value={"en": "x"},
    ), patch(
        "skills.youtube_transcribe.research.pipeline.search_multi_language",
        return_value=[_candidate()],
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_batch_pipeline",
        return_value=batch_dir,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._run_then_analyze",
    ), patch(
        "skills.youtube_transcribe.research.pipeline._stdin_is_tty",
        return_value=False,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._append_history",
        side_effect=fake_append,
    ), patch(
        "skills.youtube_transcribe.research.pipeline._load_default_cfg",
    ):
        run_research(
            query="x", queries_by_language=None,
            languages=["en"], days=30, since=None, until=None, limit=10,
            match=None, filter_text=None, in_subscribes=False, group=None,
            yes=True, no_analyze=False,
            prompt="please", prompt_file=None,
            analyze_backend="gemini", filter_backend="gemini",
            translate_backend="gemini",
            ollama_model="llama3.2:3b", ollama_host="http://localhost:11434",
            no_stdout=False, output_dir=str(tmp_path),
            batch_name="x", api_keys={}, batch_opts={},
        )

    assert captured.get("status") == "ok"
