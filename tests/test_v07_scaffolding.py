"""Smoke test: v0.7 packages exist and import cleanly."""


def test_shared_imports():
    import skills.neurolearn.shared  # noqa: F401


def test_research_imports():
    import skills.neurolearn.research  # noqa: F401


def test_subscribes_imports():
    import skills.neurolearn.subscribes  # noqa: F401


def test_history_imports():
    import skills.neurolearn.history  # noqa: F401


def test_version_matches_pyproject():
    """v0.9 renamed the project to neurolearn. Bumps should land here so
    the package-level __version__ doesn't drift from `pyproject.toml`.
    """
    import skills.neurolearn
    # v0.11.0 raised the floor from 0.10.1 — audio default switched to Groq.
    # v0.12.2 — plugin UX audit follow-up (Click choices cleanup,
    # wizard TTY guard, config get, doctor warnings + docs sweep).
    parts = skills.neurolearn.__version__.split(".")
    assert int(parts[0]) == 0
    assert int(parts[1]) >= 12
    assert int(parts[2]) >= 2 or int(parts[1]) >= 13
