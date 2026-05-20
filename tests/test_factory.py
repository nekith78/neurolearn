"""Tests for backends/factory.py — backend factory + smart-mode composition."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from skills.neurolearn.config import Config
from skills.neurolearn.backends.factory import build_backend, run_smart


# ---------------------------------------------------------------------------
# build_backend: individual backends
# ---------------------------------------------------------------------------


def test_build_backend_subtitles():
    cfg = Config()
    with patch("skills.neurolearn.backends.factory.SubtitlesBackend") as MockCls:
        instance = MagicMock()
        instance.name = "subtitles"
        MockCls.return_value = instance
        b = build_backend("subtitles", cfg)
    MockCls.assert_called_once_with()
    assert b.name == "subtitles"


def test_build_backend_whisper_local():
    cfg = Config(
        whisper_model="medium",
        whisper_device="cpu",
        whisper_compute_type="int8",
        beam_size=3,
        vad=False,
    )
    with (
        patch("skills.neurolearn.backends.factory.WhisperLocalBackend") as MockCls,
        patch("skills.neurolearn.backends.factory.detect_platform") as mock_detect,
    ):
        platform_info = MagicMock()
        platform_info.backend_impl = "faster"
        platform_info.device = "cpu"
        platform_info.recommended_compute_type = "int8"
        mock_detect.return_value = platform_info

        instance = MagicMock()
        instance.name = "whisper-local"
        MockCls.return_value = instance

        b = build_backend("whisper-local", cfg)

    # device and compute_type come from cfg when not "auto"
    MockCls.assert_called_once_with(
        model="medium",
        device="cpu",
        compute_type="int8",
        impl="faster",
        beam_size=3,
        vad=False,
    )
    assert b.name == "whisper-local"


def test_build_backend_whisper_local_user_device_override_rederives_compute():
    """v0.10.9 Fix J: when user passes `--device cpu` on an NVIDIA-detected
    machine without specifying compute_type, the factory must not blindly
    forward `info.recommended_compute_type == float16` — CPU doesn't
    support float16 and faster-whisper would crash. The factory should
    notice the device mismatch and pick int8 instead."""
    cfg = Config(
        whisper_model="turbo",
        whisper_device="cpu",         # user override
        whisper_compute_type="auto",  # user did NOT override
        beam_size=5,
        vad=True,
    )
    with (
        patch("skills.neurolearn.backends.factory.WhisperLocalBackend") as MockCls,
        patch("skills.neurolearn.backends.factory.detect_platform") as mock_detect,
    ):
        platform_info = MagicMock()
        platform_info.backend_impl = "faster"
        platform_info.device = "cuda"
        platform_info.recommended_compute_type = "float16"
        mock_detect.return_value = platform_info

        MockCls.return_value = MagicMock(name="whisper-local")
        build_backend("whisper-local", cfg)

    # Device honored, compute corrected.
    kwargs = MockCls.call_args.kwargs
    assert kwargs["device"] == "cpu", f"device wasn't honored: {kwargs}"
    assert kwargs["compute_type"] == "int8", \
        f"compute should re-derive to int8 for CPU, got {kwargs['compute_type']}"


def test_build_backend_whisper_local_explicit_compute_not_rederived():
    """If user explicitly passed both device AND compute_type, the
    factory must trust them — don't second-guess. Only `auto` triggers
    the rederive logic."""
    cfg = Config(
        whisper_model="turbo",
        whisper_device="cpu",
        whisper_compute_type="float32",  # explicit
        beam_size=5,
        vad=True,
    )
    with (
        patch("skills.neurolearn.backends.factory.WhisperLocalBackend") as MockCls,
        patch("skills.neurolearn.backends.factory.detect_platform") as mock_detect,
    ):
        platform_info = MagicMock()
        platform_info.backend_impl = "faster"
        platform_info.device = "cuda"
        platform_info.recommended_compute_type = "float16"
        mock_detect.return_value = platform_info

        MockCls.return_value = MagicMock(name="whisper-local")
        build_backend("whisper-local", cfg)

    assert MockCls.call_args.kwargs["compute_type"] == "float32", \
        "explicit compute_type must not be overridden"


def test_build_backend_whisper_local_auto_uses_platform_info():
    """When cfg has device/compute_type == 'auto', values come from platform_detect."""
    cfg = Config(
        whisper_model="turbo",
        whisper_device="auto",
        whisper_compute_type="auto",
        beam_size=5,
        vad=True,
    )
    with (
        patch("skills.neurolearn.backends.factory.WhisperLocalBackend") as MockCls,
        patch("skills.neurolearn.backends.factory.detect_platform") as mock_detect,
    ):
        platform_info = MagicMock()
        platform_info.backend_impl = "mlx"
        platform_info.device = "mps"
        platform_info.recommended_compute_type = "float16"
        mock_detect.return_value = platform_info

        instance = MagicMock()
        instance.name = "whisper-local"
        MockCls.return_value = instance

        build_backend("whisper-local", cfg)

    MockCls.assert_called_once_with(
        model="turbo",
        device="mps",
        compute_type="float16",
        impl="mlx",
        beam_size=5,
        vad=True,
    )


def test_build_backend_gemini():
    cfg = Config(gemini_model="gemini-2.5-pro")
    with patch("skills.neurolearn.backends.factory.GeminiBackend") as MockCls:
        instance = MagicMock()
        instance.name = "gemini"
        MockCls.return_value = instance
        b = build_backend("gemini", cfg)
    MockCls.assert_called_once_with(model="gemini-2.5-pro")
    assert b.name == "gemini"


def test_build_backend_groq():
    cfg = Config(groq_model="whisper-large-v3")
    with patch("skills.neurolearn.backends.factory.GroqBackend") as MockCls:
        instance = MagicMock()
        instance.name = "groq"
        MockCls.return_value = instance
        b = build_backend("groq", cfg)
    MockCls.assert_called_once_with(model="whisper-large-v3")
    assert b.name == "groq"


def test_build_backend_openai():
    cfg = Config(openai_model="whisper-1")
    with patch("skills.neurolearn.backends.factory.OpenAIBackend") as MockCls:
        instance = MagicMock()
        instance.name = "openai"
        MockCls.return_value = instance
        b = build_backend("openai", cfg)
    MockCls.assert_called_once_with(model="whisper-1")
    assert b.name == "openai"


def test_build_backend_deepgram():
    cfg = Config(deepgram_model="nova-3")
    with patch("skills.neurolearn.backends.factory.DeepgramBackend") as MockCls:
        instance = MagicMock()
        instance.name = "deepgram"
        MockCls.return_value = instance
        b = build_backend("deepgram", cfg)
    MockCls.assert_called_once_with(model="nova-3")
    assert b.name == "deepgram"


def test_build_backend_assemblyai():
    cfg = Config(assemblyai_model="best")
    with patch("skills.neurolearn.backends.factory.AssemblyAIBackend") as MockCls:
        instance = MagicMock()
        instance.name = "assemblyai"
        MockCls.return_value = instance
        b = build_backend("assemblyai", cfg)
    MockCls.assert_called_once_with(model="best")
    assert b.name == "assemblyai"


def test_build_backend_custom():
    cfg = Config(custom_base_url="https://myapi.example.com/v1", custom_model="my-model")
    with patch("skills.neurolearn.backends.factory.CustomBackend") as MockCls:
        instance = MagicMock()
        instance.name = "custom"
        MockCls.return_value = instance
        b = build_backend("custom", cfg)
    MockCls.assert_called_once_with(
        base_url="https://myapi.example.com/v1",
        model="my-model",
    )
    assert b.name == "custom"


def test_build_backend_unknown_raises():
    cfg = Config()
    with pytest.raises(ValueError, match="Unknown backend"):
        build_backend("not-a-backend", cfg)


# ---------------------------------------------------------------------------
# run_smart: composition logic
# ---------------------------------------------------------------------------


def test_smart_uses_subtitles_for_youtube_when_available():
    """YouTube URL + fast_path_enabled → tries subtitles; success → returns immediately."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local", fast_path_enabled=True)
    fake_subs = MagicMock()
    fake_subs.transcribe.return_value = MagicMock(backend_name="subtitles")
    fake_fallback = MagicMock()

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ):
        result = run_smart("https://youtu.be/abc", cfg, language="en")

    assert result.backend_name == "subtitles"
    fake_fallback.transcribe.assert_not_called()


def test_smart_falls_back_when_subtitles_fail(tmp_path):
    """YouTube URL + subtitles raises BackendError + no Gemini key →
    fallback used after download. The fallback backend receives a local
    file path, not the URL, because non-subtitles/non-gemini backends
    require local audio."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local", fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")

    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\x00")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ) as mock_dl, patch(
        # v0.10.5: smart now also tries Gemini URL before download
        # when key is available. Disable that path for this test by
        # returning no key, so we exercise pure-fallback behavior.
        "skills.neurolearn.backends.factory.get_api_key",
        return_value=None,
    ):
        result = run_smart("https://youtu.be/abc", cfg, language="en")

    assert result.backend_name == "whisper-local"
    fake_fallback.transcribe.assert_called_once()
    # Fallback receives the downloaded file path, not the original URL.
    fallback_arg = fake_fallback.transcribe.call_args.args[0]
    assert str(fallback_arg).endswith("audio.mp3")
    mock_dl.assert_called_once()


def test_smart_tries_gemini_url_after_subtitles_when_key_available(tmp_path):
    """v0.10.5: when subtitles fail on a YouTube URL AND user has a
    Gemini key, smart tries the direct-URL path BEFORE downloading
    audio. Skipped download = 30-90 s saved. Fallback config is
    whisper-local, but smart never gets there because Gemini URL
    succeeds."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local",
                 fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_gemini = MagicMock()
    fake_gemini.transcribe.return_value = MagicMock(backend_name="gemini")
    fake_fallback = MagicMock()  # whisper-local, should not be called

    def build_side_effect(name, c):
        if name == "subtitles":
            return fake_subs
        if name == "gemini":
            return fake_gemini
        return fake_fallback

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=build_side_effect,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
    ) as mock_dl, patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value="fake-gemini-key",
    ):
        url = "https://youtu.be/abc"
        result = run_smart(url, cfg, language="en")

    # Gemini URL succeeded; whisper-local fallback never invoked.
    assert result.backend_name == "gemini"
    fake_gemini.transcribe.assert_called_once_with(url, language="en")
    fake_fallback.transcribe.assert_not_called()
    # Critical: NO download happened.
    mock_dl.assert_not_called()


def test_smart_gemini_url_failure_falls_through_to_download(tmp_path):
    """v0.10.5: when both subtitles AND Gemini URL fail (e.g. Gemini
    429 quota), smart still completes by downloading audio and using
    the configured fallback_backend. User always gets a transcript."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local",
                 fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_gemini = MagicMock()
    fake_gemini.transcribe.side_effect = BackendError("429 quota exhausted")
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\x00")

    def build_side_effect(name, c):
        if name == "subtitles":
            return fake_subs
        if name == "gemini":
            return fake_gemini
        return fake_fallback

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=build_side_effect,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ) as mock_dl, patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value="fake-gemini-key",
    ):
        result = run_smart("https://youtu.be/abc", cfg, language="en")

    # Both subtitles AND Gemini failed → fallback ran via download path.
    assert result.backend_name == "whisper-local"
    fake_gemini.transcribe.assert_called_once()
    mock_dl.assert_called_once()
    fake_fallback.transcribe.assert_called_once()
    arg = fake_fallback.transcribe.call_args.args[0]
    assert str(arg).endswith("audio.mp3")


def test_smart_skips_gemini_url_when_no_key(tmp_path):
    """v0.10.5: without a Gemini key configured, smart goes straight
    from subtitles fail to download+fallback. No spurious Gemini
    invocation."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local",
                 fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_gemini = MagicMock()
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\x00")

    def build_side_effect(name, c):
        if name == "subtitles":
            return fake_subs
        if name == "gemini":
            return fake_gemini
        return fake_fallback

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=build_side_effect,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ), patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value=None,
    ):
        result = run_smart("https://youtu.be/abc", cfg, language="en")

    assert result.backend_name == "whisper-local"
    # Gemini backend NOT touched because there's no key.
    fake_gemini.transcribe.assert_not_called()


def test_smart_youtube_url_with_gemini_fallback_skips_download(tmp_path):
    """v0.10.3 → unchanged in v0.10.5: when subtitles miss and Gemini key
    is configured, we pass the URL directly via the middle-step. With
    fallback_backend=gemini the result still flows from Gemini; no
    download happens."""
    cfg = Config(default_backend="smart", fallback_backend="gemini", fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_gemini = MagicMock()
    fake_gemini.transcribe.return_value = MagicMock(backend_name="gemini")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_gemini,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
    ) as mock_dl, patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value="fake-gemini-key",
    ):
        url = "https://youtu.be/abc"
        result = run_smart(url, cfg, language="en")

    assert result.backend_name == "gemini"
    fake_gemini.transcribe.assert_called_once()
    # Gemini received the original URL, not a downloaded path.
    arg = fake_gemini.transcribe.call_args.args[0]
    assert arg == url
    # And download_audio was NOT called.
    mock_dl.assert_not_called()


def test_smart_gemini_url_fallback_to_download_on_backend_error(tmp_path):
    """If both subtitles AND the Gemini URL middle-step fail (e.g. quota),
    smart composer falls back to download+local-file path so the user
    still gets a transcript via the configured fallback_backend."""
    cfg = Config(default_backend="smart", fallback_backend="gemini", fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")

    fake_gemini = MagicMock()
    # First call (middle-step URL path) errors; second call (downloaded
    # file via fallback_backend=gemini) succeeds.
    fake_gemini.transcribe.side_effect = [
        BackendError("429 RESOURCE_EXHAUSTED"),
        MagicMock(backend_name="gemini"),
    ]

    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\x00")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_gemini,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ) as mock_dl, patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value="fake-gemini-key",
    ):
        run_smart("https://youtu.be/abc", cfg, language="en")

    assert fake_gemini.transcribe.call_count == 2
    mock_dl.assert_called_once()
    # First call: URL via middle-step. Second call: downloaded path via fallback.
    first, second = fake_gemini.transcribe.call_args_list
    assert first.args[0] == "https://youtu.be/abc"
    assert str(second.args[0]).endswith("audio.mp3")


def test_smart_downloads_for_non_youtube_url(tmp_path):
    """Non-YouTube URL (e.g. Instagram reel) → skip subtitles, download
    audio, then transcribe via fallback with the local file path.

    Regression coverage for the v0.8 bug: previously `run_smart` passed
    the URL straight to the fallback backend, which then failed at
    `Path(audio_or_url).exists()` because URLs aren't files.
    """
    cfg = Config(default_backend="smart", fallback_backend="whisper-local",
                 fast_path_enabled=True)
    fake_subs = MagicMock()
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")
    fake_audio = tmp_path / "ig-audio.mp3"
    fake_audio.write_bytes(b"\x00")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ) as mock_dl:
        result = run_smart(
            "https://www.instagram.com/reel/ABC/", cfg, language="auto",
        )

    fake_subs.transcribe.assert_not_called()
    mock_dl.assert_called_once()
    assert result.backend_name == "whisper-local"
    # Fallback receives the downloaded file, not the URL.
    fallback_arg = fake_fallback.transcribe.call_args.args[0]
    assert str(fallback_arg).endswith("ig-audio.mp3")


def test_smart_emits_stage_notifications(tmp_path):
    """run_smart should drive on_stage at phase boundaries so a caller-side
    spinner can show what's happening (subtitles / download / transcribe).

    Uses whisper-local as fallback AND mocks out Gemini key to None so
    the v0.10.5 Gemini-URL middle-step is skipped and the test exercises
    the subtitle → download → fallback path explicitly."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local",
                 fast_path_enabled=True)
    from skills.neurolearn.backends.base import BackendError
    fake_subs = MagicMock()
    fake_subs.transcribe.side_effect = BackendError("no subs")
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")
    fake_audio = tmp_path / "x.mp3"
    fake_audio.write_bytes(b"\x00")
    stages: list[str] = []

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ), patch(
        "skills.neurolearn.backends.factory.get_api_key",
        return_value=None,
    ):
        run_smart(
            "https://youtu.be/abc", cfg, language="auto",
            on_stage=stages.append,
        )

    # Expect: subtitle attempt, download, transcribe-via-fallback.
    text = " | ".join(stages).lower()
    assert "subtitle" in text
    assert "download" in text
    assert "whisper-local" in text


def test_smart_skips_subtitles_for_non_youtube_url():
    """Non-YouTube URL → skip subtitles, go straight to fallback."""
    cfg = Config(default_backend="smart", fallback_backend="whisper-local", fast_path_enabled=True)
    fake_subs = MagicMock()
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ):
        result = run_smart("/tmp/audio.mp3", cfg, language="auto")

    fake_subs.transcribe.assert_not_called()
    assert result.backend_name == "whisper-local"


def test_smart_skips_subtitles_when_fast_path_disabled(tmp_path):
    """fast_path_enabled=False → always skip subtitles, even for YouTube URLs.
    The fallback path still downloads audio because the URL must be turned
    into a local file before any non-subtitles backend can transcribe it."""
    cfg = Config(
        default_backend="smart",
        fallback_backend="whisper-local",
        fast_path_enabled=False,
    )
    fake_subs = MagicMock()
    fake_fallback = MagicMock()
    fake_fallback.transcribe.return_value = MagicMock(backend_name="whisper-local")
    fake_audio = tmp_path / "a.mp3"
    fake_audio.write_bytes(b"\x00")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_subs if n == "subtitles" else fake_fallback,
    ), patch(
        "skills.neurolearn.backends.factory.download_audio",
        return_value=fake_audio,
    ):
        result = run_smart("https://youtu.be/xyz", cfg, language="auto")

    fake_subs.transcribe.assert_not_called()
    assert result.backend_name == "whisper-local"


def test_smart_uses_configured_fallback_backend():
    """run_smart respects cfg.fallback_backend (e.g. gemini, not whisper-local)."""
    cfg = Config(
        default_backend="smart",
        fallback_backend="gemini",
        fast_path_enabled=False,
    )
    fake_gemini = MagicMock()
    fake_gemini.transcribe.return_value = MagicMock(backend_name="gemini")

    with patch(
        "skills.neurolearn.backends.factory.build_backend",
        side_effect=lambda n, c: fake_gemini,
    ):
        result = run_smart("/tmp/audio.mp3", cfg, language="fr")

    assert result.backend_name == "gemini"
