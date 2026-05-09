import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch, MagicMock

from skills.youtube_transcribe.backends.whisper_local import WhisperLocalBackend


def _make_fake_faster_whisper_module() -> ModuleType:
    """Return a stub module that satisfies `import faster_whisper`."""
    mod = ModuleType("faster_whisper")
    mod.WhisperModel = MagicMock()  # type: ignore[attr-defined]
    return mod


def test_is_configured_when_faster_whisper_importable():
    fake_fw = _make_fake_faster_whisper_module()
    with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
        b = WhisperLocalBackend(model="turbo", device="auto", compute_type="auto", impl="faster")
        ok, reason = b.is_configured()
    assert ok is True
    assert reason is None


def test_resolve_model_name_faster_turbo():
    b = WhisperLocalBackend(model="turbo", device="auto", compute_type="auto", impl="faster")
    assert b._resolve_model_name() == "large-v3-turbo"


def test_resolve_model_name_distil_on_mlx_raises():
    b = WhisperLocalBackend(model="distil", device="mps", compute_type="auto", impl="mlx")
    import pytest
    with pytest.raises(ValueError, match="distil"):
        b._resolve_model_name()


def test_transcribe_calls_faster_whisper(tmp_path: Path):
    fake_segment = MagicMock(start=0.0, end=1.5, text="hello", words=None)
    fake_info = MagicMock(language="en", duration=1.5)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], fake_info)

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake")

    fake_fw = _make_fake_faster_whisper_module()
    with patch.dict(sys.modules, {"faster_whisper": fake_fw}), patch(
        "skills.youtube_transcribe.backends.whisper_local._load_faster_whisper_model",
        return_value=fake_model,
    ):
        b = WhisperLocalBackend(model="turbo", device="cuda", compute_type="float16", impl="faster")
        result = b.transcribe(audio, language="en")

    assert result.text.strip() == "hello"
    assert result.language_detected == "en"
    assert result.backend_name == "whisper-local"
    assert len(result.segments) == 1
    assert result.segments[0].start == 0.0
    fake_model.transcribe.assert_called_once()
