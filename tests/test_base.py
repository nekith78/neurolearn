from skills.youtube_transcribe.backends.base import (
    Transcriber,
    TranscriptionResult,
    BackendError,
    BackendNotConfigured,
)
from skills.youtube_transcribe.utils.output_writer import Segment


def test_transcription_result_construct():
    res = TranscriptionResult(
        text="hello world",
        segments=[Segment(0.0, 1.0, "hello"), Segment(1.0, 2.0, "world")],
        language_detected="en",
        backend_name="dummy",
        duration_seconds=2.0,
    )
    assert res.text == "hello world"
    assert len(res.segments) == 2


def test_backend_errors_are_distinct():
    assert issubclass(BackendNotConfigured, BackendError)
    assert not issubclass(BackendError, BackendNotConfigured)


def test_transcriber_is_protocol():
    # Should NOT be instantiable directly; just verify it's a Protocol
    import typing
    assert getattr(Transcriber, "_is_protocol", False) or hasattr(Transcriber, "__protocol_attrs__")
