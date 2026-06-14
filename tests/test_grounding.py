"""Tests for the visual-report grounding check (text↔image)."""
from skills.neurolearn.report.grounding import (
    extract_claim_tokens, verify_markdown_grounding,
)


def test_extract_claim_tokens():
    toks = extract_claim_tokens("На картинке: Arcane Surge на крите, +12% и 270 ES")
    low = [t.lower() for t in toks]
    assert "arcane" in low and "surge" in low
    assert "+12%" in toks and "270" in toks
    # filler words are skipped
    assert "this" not in low and "tooltip" not in low


def _fake_ocr(mapping):
    def _ocr(path):
        return mapping.get(path.name, "")
    return _ocr


def test_flags_caption_term_not_on_image(tmp_path):
    (tmp_path / "frames").mkdir()
    img = tmp_path / "frames" / "g_crop.jpg"
    img.write_bytes(b"x")
    md = "![На картинке: Arcane Surge на крите](frames/g_crop.jpg)\n"
    # OCR of the image does NOT contain Arcane Surge (crop cut it off).
    issues = verify_markdown_grounding(
        md, tmp_path,
        ocr_fn=_fake_ocr({"g_crop.jpg": "ENERGY SHIELD MAXIMUM MANA RARITY"}),
    )
    assert len(issues) == 1
    assert any("Arcane" in m or "Surge" in m for m in issues[0].missing)


def test_passes_when_terms_present_with_ocr_noise(tmp_path):
    (tmp_path / "frames").mkdir()
    img = tmp_path / "frames" / "g_crop.jpg"
    img.write_bytes(b"x")
    md = "![На картинке: Arcane Surge, Critical Hit, +12%](frames/g_crop.jpg)\n"
    # OCR with typical easyocr noise (HII for HIT) — fuzzy match still passes.
    issues = verify_markdown_grounding(
        md, tmp_path,
        ocr_fn=_fake_ocr({
            "g_crop.jpg":
            "12(10-15)% CHANCE TO GAIN ARCANE SURGE WHEN YOU DEAL A CRITICAL HII",
        }),
    )
    assert issues == []


def test_number_grounding_catches_wrong_value(tmp_path):
    (tmp_path / "frames").mkdir()
    img = tmp_path / "frames" / "a_crop.jpg"
    img.write_bytes(b"x")
    # Caption claims +4 but the frame shows +3.
    md = "![+4 to all Spell Skills](frames/a_crop.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        ocr_fn=_fake_ocr({"a_crop.jpg": "+3 TO LEVEL OF ALL SPELL SKILLS"}),
    )
    assert len(issues) == 1 and "+4" in issues[0].missing


def test_number_not_matched_as_substring(tmp_path):
    """'+3' must NOT be considered present just because OCR has '34%'."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "a_crop.jpg").write_bytes(b"x")
    md = "![+3 to Spell Skills](frames/a_crop.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        ocr_fn=_fake_ocr({"a_crop.jpg": "34% INCREASED ENERGY SHIELD +47 SPIRIT"}),
    )
    assert len(issues) == 1 and "+3" in issues[0].missing
    # ...but a genuine standalone match passes.
    ok = verify_markdown_grounding(
        md, tmp_path,
        ocr_fn=_fake_ocr({"a_crop.jpg": "+3 TO LEVEL OF ALL SPELL SKILLS"}),
    )
    assert ok == []


def test_missing_image_file_flagged(tmp_path):
    md = "![something](frames/nope.jpg)\n"
    issues = verify_markdown_grounding(md, tmp_path, ocr_fn=_fake_ocr({}))
    assert len(issues) == 1 and "not found" in issues[0].missing[0]


def test_data_uri_and_captionless_skipped(tmp_path):
    md = (
        "![](frames/x.jpg)\n"           # no caption → skip
        "![cap](data:image/jpeg;base64,AAA)\n"  # data uri → skip
    )
    assert verify_markdown_grounding(md, tmp_path, ocr_fn=_fake_ocr({})) == []
