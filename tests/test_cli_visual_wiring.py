"""Test that --with-visuals actually triggers visual mode wiring (with mocks)."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from skills.neurolearn.transcribe import cli


def test_with_visuals_triggers_download_video(tmp_path, monkeypatch):
    """Verify that --with-visuals on a URL kicks off download_video."""
    # Mock the entire pipeline to avoid real transcription
    fake_segment = MagicMock(start=0.0, end=5.0, text="hello")
    fake_result = MagicMock()
    fake_result.segments = [fake_segment]
    fake_result.text = "hello"
    fake_result.language_detected = "en"
    fake_result.backend_name = "subtitles_auto"
    fake_result.duration_seconds = 5.0
    fake_result.quality = None
    fake_result.visual_segments = []

    fake_video_path = tmp_path / "video_abc.mp4"
    fake_video_path.write_bytes(b"fake mp4")

    download_called = {"v": False}

    def fake_download_video(url, out_dir, **kw):
        download_called["v"] = True
        # Mimic real path return
        f = out_dir / "video_abc.mp4"
        f.write_bytes(b"fake")
        return f

    runner = CliRunner()
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.run_pipeline",
        lambda *a, **kw: fake_result,
    )
    monkeypatch.setattr(
        "skills.neurolearn.utils.downloader.download_video",
        fake_download_video,
    )
    # v0.21: --with-visuals is key-aware (Gemini preferred). Provide both
    # keys so the visual pipeline kicks in regardless of which is picked.
    monkeypatch.setattr(
        "skills.neurolearn.config.get_api_key",
        lambda backend, env_path=None: "fake_key" if backend in ("groq", "gemini") else None,
    )
    # apply_v02_stages should be called with non-None video_path.
    # It's imported locally inside transcribe_cmd, so patch at the source module.
    apply_call_args = {}

    def fake_apply(**kwargs):
        apply_call_args.update(kwargs)
        return kwargs["result"]

    monkeypatch.setattr(
        "skills.neurolearn.pipeline_v02.apply_v02_stages",
        fake_apply,
    )

    # Avoid wizard (config exists check)
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.CONFIG_PATH",
        tmp_path / "config.toml",
    )
    (tmp_path / "config.toml").write_text("default_preset = \"smart\"\n", encoding="utf-8")

    # v0.10.9: mock the URL resolver too, otherwise the test hits real
    # YouTube and intermittently gets 429s on the CI runner IP. Returning
    # a synthetic ResolvedTarget lets us exercise the with-visuals
    # download path without leaving the test environment.
    from skills.neurolearn.utils.resolver import ResolvedTarget
    fake_target = ResolvedTarget(
        url="https://youtu.be/test123", title="Test", upload_date=None,
        duration_sec=60, channel=None, source="inline", video_id="test123",
    )
    monkeypatch.setattr(
        "skills.neurolearn.transcribe.resolve",
        lambda *a, **kw: ([fake_target], []),
    )

    res = runner.invoke(
        cli,
        ["transcribe", "https://youtu.be/test123", "--with-visuals",
         "--output-dir", str(tmp_path)],
        catch_exceptions=False,
    )

    # download_video should have been called for URL + visual mode
    assert download_called["v"], f"download_video NOT called. Output:\n{res.output}"
    # apply_v02_stages should have video_path set (non-None)
    assert apply_call_args.get("video_path") is not None, \
        f"video_path was None. Output:\n{res.output}"


def test_default_vision_backend_is_key_aware(monkeypatch):
    """v0.21: --with-visuals picks Gemini when its key exists, else Groq,
    else Gemini (so the unconfigured path gives a clear setup hint)."""
    from skills.neurolearn import transcribe as tr
    monkeypatch.setattr(tr, "get_api_key",
                        lambda b, env_path=None: "k" if b == "gemini" else None)
    assert tr._default_vision_backend() == "gemini"
    monkeypatch.setattr(tr, "get_api_key",
                        lambda b, env_path=None: "k" if b == "groq" else None)
    assert tr._default_vision_backend() == "groq"
    monkeypatch.setattr(tr, "get_api_key", lambda b, env_path=None: None)
    assert tr._default_vision_backend() == "gemini"


def test_autonomous_llm_first_gating(monkeypatch):
    """v0.21 Mode-2: --with-visuals auto-selects llm_first only when Gemini is
    configured, no explicit --detect-method was given, and we're not in
    extract-only mode (where an in-editor agent picks the moments)."""
    from skills.neurolearn import transcribe as tr
    monkeypatch.setattr(tr, "get_api_key",
                        lambda b, env_path=None: "k" if b == "gemini" else None)

    # Happy path: with-visuals, no explicit method, full pipeline, key present.
    assert tr._autonomous_llm_first(
        {"with_visuals": True, "detect_method_opt": None}, {}) is True

    # Explicit --detect-method wins → no auto-select.
    assert tr._autonomous_llm_first(
        {"with_visuals": True, "detect_method_opt": "hybrid"}, {}) is False

    # Extract-only (in-editor agent picks moments) → no auto-select.
    assert tr._autonomous_llm_first(
        {"with_visuals": True, "detect_method_opt": None},
        {"vision_extract_only": True}) is False

    # No --with-visuals → no auto-select.
    assert tr._autonomous_llm_first(
        {"with_visuals": False, "detect_method_opt": None}, {}) is False

    # No Gemini key → no auto-select (trigger path used instead).
    monkeypatch.setattr(tr, "get_api_key", lambda b, env_path=None: None)
    assert tr._autonomous_llm_first(
        {"with_visuals": True, "detect_method_opt": None}, {}) is False
