"""Smoke test: analyze module skeleton exists and imports cleanly."""


def test_analyze_module_imports():
    import skills.youtube_transcribe.analyze  # noqa: F401


def test_version_is_v06():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.6.")


def test_picker_imports():
    """Picker module imports cleanly even outside a TTY."""
    from skills.youtube_transcribe.analyze import picker
    assert hasattr(picker, "pick_batch")
    assert hasattr(picker, "pick_videos")
    assert hasattr(picker, "PickerCancelled")
