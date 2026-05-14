"""Tests for v0.7 webui tabs (Research + Subscribes).

These tests are pytest.skip'd when gradio isn't installed (it's an
opt-in extra: `uv sync --extra webui`).
"""
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import gradio  # noqa: F401
    _GRADIO = True
except ImportError:
    _GRADIO = False


def test_research_tab_builder_callable():
    if not _GRADIO:
        pytest.skip("gradio not installed (webui extra)")
    from skills.neurolearn.webui.app import build_research_tab
    assert callable(build_research_tab)


def test_subscribes_tab_builder_callable():
    if not _GRADIO:
        pytest.skip("gradio not installed (webui extra)")
    from skills.neurolearn.webui.app import build_subscribes_tab
    assert callable(build_subscribes_tab)


def test_research_handler_delegates_to_pipeline():
    from skills.neurolearn.webui.app import _handle_research_submit
    with patch(
        "skills.neurolearn.research.pipeline.run_research",
        return_value=Path("/tmp/fake"),
    ) as mock_pipe:
        out = _handle_research_submit(
            query="Claude features",
            languages_csv="ru,en",
            days=30,
            limit=20,
            match_text="",
            filter_text="",
            no_analyze=True,
            yes=True,
            prompt="",
            analyze_backend="gemini",
            filter_backend="gemini",
            backend="subtitles",
        )
    mock_pipe.assert_called_once()
    assert "fake" in str(out)


def test_subscribes_add_handler():
    from skills.neurolearn.subscribes.channel_resolver import (
        ResolvedChannel,
    )
    from skills.neurolearn.webui.app import _handle_subscribes_add
    with patch(
        "skills.neurolearn.subscribes.cli.resolve_channel",
        return_value=ResolvedChannel(
            url="https://www.youtube.com/@A", handle="@A",
            channel_id="UC_a", title="A",
        ),
    ), patch(
        "skills.neurolearn.subscribes.cli.add_channel",
    ) as mock_add, patch(
        "skills.neurolearn.webui.app._handle_subscribes_list",
        return_value="@A  [—]  last_seen=—",
    ):
        msg = _handle_subscribes_add(
            "https://www.youtube.com/@A", group="ai",
        )
    mock_add.assert_called_once()
    assert "@A" in msg


def test_subscribes_update_handler_delegates():
    from skills.neurolearn.webui.app import _handle_subscribes_update
    with patch(
        "skills.neurolearn.subscribes.pipeline.run_subscribes_update",
        return_value=Path("/tmp/fake"),
    ) as mock_pipe:
        out = _handle_subscribes_update(
            group="", days=7, no_analyze=True, yes=True,
            prompt="", analyze_backend="gemini", backend="subtitles",
        )
    mock_pipe.assert_called_once()
    assert "fake" in str(out)
