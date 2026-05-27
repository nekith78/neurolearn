from pathlib import Path
import os
from unittest.mock import patch

import pytest

import skills.neurolearn.config as config_module
from skills.neurolearn.config import (
    Config,
    load_config,
    save_config,
    get_api_key,
    set_api_key,
    mask_key,
    DEFAULT_CONFIG,
)


def test_default_config_v011_defaults_smart_and_groq():
    """v0.11.0: default_backend=smart, fallback_backend=groq.

    Rationale (v0.11.0): empirical testing (2026-05-20) showed
    Gemini 2.5-flash hallucinates timestamps by +63% on a 17-min
    video (claimed duration=1045s on a 640s real video). Groq
    Whisper-large-v3-turbo is 4-8x faster and gives accurate
    timestamps. Smart cascade is: subtitles -> groq -> whisper-local
    (auto-fallback if groq key missing).
    """
    assert DEFAULT_CONFIG.default_backend == "smart"
    assert DEFAULT_CONFIG.fallback_backend == "groq"


def test_save_and_load_roundtrip(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        default_backend="gemini",
        fallback_backend="whisper-local",
        whisper_model="large",
        gemini_model="gemini-2.5-pro",
        groq_model="whisper-large-v3-turbo",
        openai_model="whisper-1",
        deepgram_model="nova-3",
        assemblyai_model="best",
        custom_base_url="",
        custom_model="",
        whisper_device="auto",
        whisper_compute_type="auto",
        beam_size=5,
        vad=True,
        language="auto",
        timestamps=True,
        srt=True,
        output_dir="./transcripts",
        keep_audio=False,
        yt_dlp_auto_update=True,
        cookies_file="",
        fast_path_enabled=True,
    )
    save_config(cfg, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded == cfg


def test_load_missing_file_returns_default(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg == DEFAULT_CONFIG


def test_shorts_max_per_update_default():
    """v0.17: default 5 caps per-channel Shorts pulled in `subscribes update`."""
    assert DEFAULT_CONFIG.shorts_max_per_update == 5


def test_shorts_max_per_update_roundtrips(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(shorts_max_per_update=20)
    save_config(cfg, cfg_path)
    assert load_config(cfg_path).shorts_max_per_update == 20


def test_shorts_max_per_update_zero_means_no_cap(tmp_path: Path):
    """0 is a meaningful value (unbounded) — must round-trip without coercion."""
    cfg_path = tmp_path / "config.toml"
    cfg = Config(shorts_max_per_update=0)
    save_config(cfg, cfg_path)
    assert load_config(cfg_path).shorts_max_per_update == 0


def test_pre_v017_config_without_subscribes_section_defaults_to_5(tmp_path: Path):
    """A config.toml written before v0.17 has no [subscribes] table — loader
    must fall through to the default rather than crashing or zeroing the cap."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        "default_backend = \"smart\"\n"
        "fallback_backend = \"groq\"\n",
        encoding="utf-8",
    )
    assert load_config(cfg_path).shorts_max_per_update == 5


def test_get_api_key_from_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-value")
    assert get_api_key("gemini", env_path=tmp_path / ".env") == "env-value"


def test_get_api_key_from_env_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("GROQ_API_KEY=file-value\n")
    assert get_api_key("groq", env_path=env_path) == "file-value"


def test_set_api_key_writes_env(tmp_path: Path):
    env_path = tmp_path / ".env"
    set_api_key("openai", "sk-test", env_path=env_path)
    content = env_path.read_text()
    assert "OPENAI_API_KEY=sk-test" in content


def test_mask_key_short():
    assert mask_key("ab") == "***"


def test_mask_key_long():
    masked = mask_key("sk-1234567890abcdef")
    assert masked.startswith("sk-")
    assert masked.endswith("cdef")
    assert "*" in masked


def test_set_api_key_rejects_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "ENV_PATH", tmp_path / ".env")
    with pytest.raises(ValueError, match="newline"):
        config_module.set_api_key("openai", "abc\ndef")


def test_load_config_raises_on_malformed_toml(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text("not = valid = toml = [[[", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed TOML"):
        config_module.load_config(bad)
