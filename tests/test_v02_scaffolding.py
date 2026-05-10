"""Smoke test: v0.2 module skeletons exist and import cleanly."""

def test_quality_module_imports():
    import skills.youtube_transcribe.quality  # noqa: F401

def test_detection_module_imports():
    import skills.youtube_transcribe.detection  # noqa: F401

def test_vision_module_imports():
    import skills.youtube_transcribe.vision  # noqa: F401

def test_presets_module_imports():
    import skills.youtube_transcribe.presets  # noqa: F401

def test_version_bumped():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.2.")
