"""Tests for --vision-prompt custom template loading."""
from skills.neurolearn.pipeline_v02 import _load_vision_prompt
from skills.neurolearn.vision.prompts import DEFAULT_PROMPT


def test_no_path_returns_default():
    assert _load_vision_prompt({}) == DEFAULT_PROMPT
    assert _load_vision_prompt({"vision_prompt_path": ""}) == DEFAULT_PROMPT
    assert _load_vision_prompt({"vision_prompt_path": "   "}) == DEFAULT_PROMPT


def test_valid_path_returns_file_content(tmp_path):
    p = tmp_path / "prompt.txt"
    p.write_text(
        "Describe in {language}: {transcript_snippet} {start_sec} {end_sec}",
        encoding="utf-8",
    )
    cfg = {"vision_prompt_path": str(p)}
    assert "Describe in {language}" in _load_vision_prompt(cfg)


def test_missing_file_falls_back_to_default(tmp_path):
    cfg = {"vision_prompt_path": str(tmp_path / "nonexistent.txt")}
    assert _load_vision_prompt(cfg) == DEFAULT_PROMPT


def test_tilde_path_expanded(tmp_path, monkeypatch):
    """`~/...` paths should expand on all OSes.

    On Windows `Path.expanduser()` reads USERPROFILE / HOMEDRIVE+HOMEPATH
    first, not HOME — so we set both for cross-OS portability.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = tmp_path / "p.txt"
    p.write_text("custom prompt", encoding="utf-8")
    cfg = {"vision_prompt_path": "~/p.txt"}
    assert _load_vision_prompt(cfg) == "custom prompt"
