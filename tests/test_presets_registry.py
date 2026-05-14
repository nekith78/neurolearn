"""Tests for OptionField + REGISTRY."""
from skills.neurolearn.presets.registry import (
    OptionField,
    REGISTRY,
    get_field,
    fields_by_section,
)


def test_registry_has_required_fields():
    keys = {f.key for f in REGISTRY}
    assert "transcribe_backend" in keys
    assert "vision_backend" in keys
    assert "detect_method" in keys
    assert "frames_per_window" in keys


def test_field_has_required_metadata():
    f = get_field("transcribe_backend")
    assert f is not None
    assert f.type is str
    assert f.default == "subtitles"
    assert "subtitles" in f.choices
    assert "whisper-local" in f.choices
    assert f.description


def test_each_default_is_in_choices():
    """If a field has choices, default MUST be in choices."""
    for f in REGISTRY:
        if f.choices is not None:
            assert f.default in f.choices, f"{f.key} default {f.default} not in {f.choices}"


def test_fields_by_section_groups():
    by_sect = fields_by_section()
    assert "transcribe" in by_sect
    assert "vision" in by_sect


def test_get_field_unknown_returns_none():
    assert get_field("totally_made_up") is None
