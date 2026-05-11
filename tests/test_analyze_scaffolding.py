"""Smoke test: analyze module skeleton exists and imports cleanly."""


def test_analyze_module_imports():
    import skills.youtube_transcribe.analyze  # noqa: F401


def test_version_is_at_least_v06():
    """analyze module shipped in v0.6; version must be >= 0.6.x."""
    import skills.youtube_transcribe
    v = skills.youtube_transcribe.__version__
    major_minor = tuple(int(p) for p in v.split("-")[0].split(".")[:2])
    assert major_minor >= (0, 6)


def test_picker_imports():
    """Picker module imports cleanly even outside a TTY."""
    from skills.youtube_transcribe.analyze import picker
    assert hasattr(picker, "pick_batch")
    assert hasattr(picker, "pick_videos")
    assert hasattr(picker, "PickerCancelled")
