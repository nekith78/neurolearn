"""Smoke test: v0.7 packages exist and import cleanly."""


def test_shared_imports():
    import skills.youtube_transcribe.shared  # noqa: F401


def test_research_imports():
    import skills.youtube_transcribe.research  # noqa: F401


def test_subscribes_imports():
    import skills.youtube_transcribe.subscribes  # noqa: F401


def test_history_imports():
    import skills.youtube_transcribe.history  # noqa: F401


def test_version_is_v07():
    import skills.youtube_transcribe
    assert skills.youtube_transcribe.__version__.startswith("0.7.")
