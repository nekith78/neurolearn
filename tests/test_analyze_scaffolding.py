"""Smoke test: analyze module skeleton exists and imports cleanly."""


def test_analyze_module_imports():
    import skills.youtube_transcribe.analyze  # noqa: F401


def test_version_is_v06():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.6.")
