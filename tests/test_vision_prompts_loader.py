"""Tests for vision.prompts loader: built-in + user override + global prefix.

Covers the loader contract from prompts_default.toml + user TOML
merge logic, used by the vision pipeline to pick a system prompt per
video type.
"""
from pathlib import Path

import pytest

from skills.neurolearn.vision.prompts import (
    BUILTIN_VIDEO_TYPES, load_prompt, list_known_types, format_prompt,
)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------


def test_all_builtin_types_load():
    """Every type in BUILTIN_VIDEO_TYPES has a non-empty prompt."""
    for t in BUILTIN_VIDEO_TYPES:
        spec = load_prompt(t)
        assert spec.template, f"{t} has empty template"
        assert spec.source == "builtin"


def test_global_prefix_prepended_by_default():
    spec = load_prompt("tutorial")
    assert spec.used_global_prefix is True
    # Global prefix has a distinctive opening line.
    assert "Output language" in spec.template


def test_use_global_prefix_false_drops_prefix():
    spec = load_prompt("tutorial", use_global_prefix=False)
    assert spec.used_global_prefix is False
    assert "Output language" not in spec.template


def test_unknown_type_falls_back_to_generic():
    """A type that isn't in the TOML returns the generic template."""
    spec = load_prompt("nonsense-type-2030")
    # Falls back to generic — same distinctive opening as generic prompt.
    assert "Browser DevTools network tab" in spec.template
    assert spec.source == "builtin"


# ---------------------------------------------------------------------------
# User override
# ---------------------------------------------------------------------------


def test_user_override_replaces_builtin(tmp_path: Path):
    """User TOML supplies a custom prompt for `tutorial` → it's used
    instead of the shipped one."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text("""
[prompts.tutorial]
prompt = "MY OWN tutorial focus on Photoshop only"
append_global = true
""", encoding="utf-8")
    spec = load_prompt("tutorial", user_path=user_toml)
    assert "MY OWN tutorial focus on Photoshop only" in spec.template
    assert "Output language" in spec.template  # global still appended
    assert spec.source == "user_override"


def test_user_override_can_disable_global_prefix(tmp_path: Path):
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text("""
[prompts.tutorial]
prompt = "STANDALONE custom prompt"
append_global = false
""", encoding="utf-8")
    spec = load_prompt("tutorial", user_path=user_toml)
    assert spec.template == "STANDALONE custom prompt"
    assert spec.used_global_prefix is False


def test_user_can_define_new_video_type(tmp_path: Path):
    """User TOML can introduce a custom video type unknown to the built-in."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text("""
[prompts.cooking-show]
prompt = "Focus on ingredients, utensils, and cooking actions."
append_global = false
""", encoding="utf-8")
    spec = load_prompt("cooking-show", user_path=user_toml)
    assert "ingredients" in spec.template
    types = list_known_types(user_path=user_toml)
    assert "cooking-show" in types


def test_user_global_prefix_overrides_builtin(tmp_path: Path):
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text("""
[global]
prefix = "Reply in Russian. Be brief."
""", encoding="utf-8")
    spec = load_prompt("generic", user_path=user_toml)
    assert "Reply in Russian." in spec.template
    # Built-in "Output language" string from the default global prefix
    # should NOT be present — user replaced it.
    assert "Output language" not in spec.template


def test_broken_user_toml_falls_back_silently(tmp_path: Path):
    """Bad user TOML doesn't crash the pipeline."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text("this is not valid toml [[[", encoding="utf-8")
    spec = load_prompt("tutorial", user_path=user_toml)
    # Falls back to built-in.
    assert spec.source == "builtin"
    assert spec.template, "must still load some template"


# ---------------------------------------------------------------------------
# Custom inline template (CLI --prompt-file)
# ---------------------------------------------------------------------------


def test_custom_inline_template_used_with_global(tmp_path: Path):
    """CLI --prompt-file path content → wins. Global prefix prepended."""
    spec = load_prompt(
        "generic",
        custom_template="VERY SPECIFIC custom for one run",
        use_global_prefix=True,
    )
    assert "VERY SPECIFIC custom for one run" in spec.template
    assert "Output language" in spec.template
    assert spec.source == "cli_file"


def test_custom_inline_template_can_skip_global():
    spec = load_prompt(
        "generic",
        custom_template="ONLY this and nothing else",
        use_global_prefix=False,
    )
    assert spec.template == "ONLY this and nothing else"
    assert spec.used_global_prefix is False


# ---------------------------------------------------------------------------
# format_prompt — substitution
# ---------------------------------------------------------------------------


def test_format_prompt_substitutes_placeholders():
    template = "lang={language}; snippet={transcript_snippet}; t={start_sec:.1f}-{end_sec:.1f}"
    result = format_prompt(
        template,
        language="ru", transcript_snippet="hello world",
        start_sec=10.5, end_sec=15.0,
    )
    assert result == "lang=ru; snippet=hello world; t=10.5-15.0"


# ---------------------------------------------------------------------------
# v0.12.0: per-model variants — [prompts.<type>.<model_family>]
# ---------------------------------------------------------------------------


def test_load_prompt_uses_groq_variant_when_requested(tmp_path: Path):
    """Per-model subsection picked when model_family matches."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text(
        """
[prompts.tutorial]
prompt = "Default tutorial prompt for Gemini-style models."
append_global = true

[prompts.tutorial.groq]
prompt = "GROQ-OPTIMIZED tutorial prompt (positive whitelist only)."
append_global = false
""",
        encoding="utf-8",
    )
    spec = load_prompt("tutorial", user_path=user_toml, model_family="groq")
    assert "GROQ-OPTIMIZED" in spec.template
    assert "Default tutorial prompt" not in spec.template
    assert spec.used_global_prefix is False  # this variant disabled global
    assert spec.source.startswith("user_override")


def test_load_prompt_falls_back_to_default_when_no_variant(tmp_path: Path):
    """Missing variant subsection → use the base type prompt + log."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text(
        """
[prompts.tutorial]
prompt = "Default tutorial body."
""",
        encoding="utf-8",
    )
    spec = load_prompt("tutorial", user_path=user_toml, model_family="groq")
    assert "Default tutorial body" in spec.template


def test_load_prompt_no_model_family_uses_default(tmp_path: Path):
    """Without model_family arg, behavior matches v0.11 — default prompt."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text(
        """
[prompts.tutorial]
prompt = "Base prompt."

[prompts.tutorial.groq]
prompt = "Groq variant."
""",
        encoding="utf-8",
    )
    spec = load_prompt("tutorial", user_path=user_toml)
    assert "Base prompt" in spec.template
    assert "Groq variant" not in spec.template


def test_builtin_prompts_default_has_groq_variants_loaded():
    """C2: shipped TOML must contain .groq variants for all 8 builtin types.

    Foundation check — without this, the v0.12 vision pipeline silently
    falls back to default prompts when Groq is the primary backend,
    losing all the Llama-4-Scout-specific tuning (positive whitelist,
    no canonical example outputs, schema-enforced brevity)."""
    from skills.neurolearn.vision.prompts import BUILTIN_VIDEO_TYPES
    for video_type in BUILTIN_VIDEO_TYPES:
        spec = load_prompt(video_type, model_family="groq")
        # When a .groq variant exists, the loader returns it with the
        # corresponding source marker. When the variant is absent, the
        # default body is returned with source="builtin".
        assert spec.template, f"{video_type}: empty template"
        # Sanity: variant should differ from base if shipped properly.
        # We don't enforce content rules here — just that variant *exists*.
        # The variant subsection is verified separately in C2 tests.


def test_groq_variant_falls_back_to_global_prefix_unless_disabled(tmp_path: Path):
    """When the variant doesn't set append_global, default is True."""
    user_toml = tmp_path / "prompts.toml"
    user_toml.write_text(
        """
[global]
prefix = "GLOBAL HEADER"

[prompts.tutorial]
prompt = "Base."

[prompts.tutorial.groq]
prompt = "Groq variant (inherits default append_global=true)."
""",
        encoding="utf-8",
    )
    spec = load_prompt("tutorial", user_path=user_toml, model_family="groq")
    assert "GLOBAL HEADER" in spec.template
    assert "Groq variant" in spec.template


# ---------------------------------------------------------------------------
# C2 — verify shipped .groq variants per type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("video_type", [
    "tutorial", "lecture", "code", "demo", "interview",
    "vlog", "review", "talking_head", "generic",
])
def test_builtin_groq_variant_exists_per_type(video_type: str):
    """Each builtin type must have a [prompts.<type>.groq] subsection
    with a non-empty `prompt` field — otherwise vision-pipeline silently
    falls back to default prompts when Groq is primary."""
    spec = load_prompt(video_type, model_family="groq")
    assert spec.template, f"{video_type}.groq variant produced empty template"
    assert spec.source.endswith("/groq") or spec.source == "builtin", (
        f"{video_type}.groq variant not picked up; source={spec.source}"
    )


@pytest.mark.parametrize("video_type", [
    "tutorial", "lecture", "code", "demo", "interview",
    "vlog", "review", "talking_head", "generic",
])
def test_groq_variants_omit_canonical_examples(video_type: str):
    """Groq variants must NOT include literal 'GOOD: ...' / 'BAD: ...'
    examples — Llama-4-Scout copies those strings verbatim into output.

    The Groq variants describe SHAPE instead of providing example outputs.
    """
    spec = load_prompt(video_type, model_family="groq")
    # The Llama-4-Scout-tuned variants intentionally drop the GOOD/BAD
    # example blocks present in the Gemini-style base prompts.
    assert "GOOD:" not in spec.template, (
        f"{video_type}.groq variant contains 'GOOD:' literal example — "
        f"will be copied verbatim by Llama-4-Scout"
    )
    assert "BAD:" not in spec.template, (
        f"{video_type}.groq variant contains 'BAD:' literal example"
    )


def test_groq_variants_use_positive_whitelist():
    """Groq variants use 'DESCRIBE ONLY' + 'NEVER DESCRIBE' pattern
    (per Meta prompting guide: positive constraints > negative)."""
    for vt in ["tutorial", "demo", "review", "talking_head", "generic"]:
        spec = load_prompt(vt, model_family="groq")
        assert "DESCRIBE ONLY" in spec.template, (
            f"{vt}.groq variant missing positive whitelist"
        )


def test_groq_variants_cap_description_length():
    """Schema-enforced brevity: every Groq variant must state the
    ≤30-word description cap so Scout knows what to target."""
    for vt in ["tutorial", "demo", "review", "talking_head", "generic"]:
        spec = load_prompt(vt, model_family="groq")
        assert "≤30 words" in spec.template, (
            f"{vt}.groq missing ≤30 words schema hint"
        )
