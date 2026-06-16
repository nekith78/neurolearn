"""Tests for the visual-report grounding check (caption ↔ blind frame atoms)."""
from skills.neurolearn.report.grounding import (
    FrameAtoms, extract_caption_claims, verify_markdown_grounding,
    load_frame_atoms, write_frame_atoms,
)


def _fake_atoms(mapping):
    """Inject FrameAtoms per frame filename; missing frame → empty atoms."""
    def _fn(path):
        return mapping.get(path.name, FrameAtoms())
    return _fn


def _verify(md, batch, **kw):
    from skills.neurolearn.report.grounding import verify_markdown_grounding
    return verify_markdown_grounding(md, batch, **kw)


# --- caption claim extraction (language-agnostic) ------------------------

def test_extract_claims_numbers_urls_terms():
    claims = extract_caption_claims(
        'На картинке: «Arcane Surge» на крите, +12% и F1 ≈ 58%, '
        'ссылка arxiv.org/abs/2512.24601'
    )
    assert "+12%" in claims.numbers and "58" in " ".join(claims.numbers)
    assert any("arxiv.org/abs/2512.24601" in u for u in claims.urls)
    assert "Arcane Surge" in claims.terms


def test_url_digits_not_double_counted_as_numbers():
    """A citation's digits stay part of the URL, not standalone number claims."""
    claims = extract_caption_claims("см. arxiv.org/abs/2512.24601")
    assert claims.urls and not claims.numbers


def test_extract_claims_works_for_non_latin_terms():
    """Quoted terms are pulled regardless of script (no language list)."""
    claims = extract_caption_claims('схема: «Векторная БД» и «Эмбеддер»')
    assert "Векторная БД" in claims.terms and "Эмбеддер" in claims.terms


# --- grounding diff ------------------------------------------------------

def test_hallucinated_url_is_blocking(tmp_path):
    (tmp_path / "frames").mkdir()
    img = tmp_path / "frames" / "f_crop.jpg"
    img.write_bytes(b"x")
    md = "![см. arxiv.org/abs/2512.24601](frames/f_crop.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"f_crop.jpg": FrameAtoms(
            terms=["Cost of RLM and baselines", "GPT-5-mini"],
        )}),
    )
    assert len(issues) == 1
    assert any("arxiv" in h for h in issues[0].hallucinations)
    assert issues[0].is_blocking(strict=False)  # URL → blocks by default


def test_url_confirmed_when_on_frame(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "f_crop.jpg").write_bytes(b"x")
    md = "![см. arxiv.org/abs/2512.24601](frames/f_crop.jpg)\n"
    issues = _verify(
        md, tmp_path,
        atoms_fn=_fake_atoms({"f_crop.jpg": FrameAtoms(
            urls=["arxiv.org/abs/2512.24601"],
        )}),
    )
    assert issues == []


def test_wrong_number_is_blocking(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "a_crop.jpg").write_bytes(b"x")
    # Caption claims +4 but the frame shows +3.
    md = "![+4 to all Spell Skills](frames/a_crop.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"a_crop.jpg": FrameAtoms(numbers=["+3"])}),
    )
    assert len(issues) == 1 and "+4" in issues[0].hallucinations
    assert issues[0].is_blocking(strict=False)


def test_number_not_matched_as_substring(tmp_path):
    """'+3' must NOT count as present just because the frame shows '34%'."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "a_crop.jpg").write_bytes(b"x")
    md = "![+3 to Spell Skills](frames/a_crop.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"a_crop.jpg": FrameAtoms(numbers=["34%", "+47"])}),
    )
    assert len(issues) == 1 and "+3" in issues[0].hallucinations
    ok = _verify(
        md, tmp_path,
        atoms_fn=_fake_atoms({"a_crop.jpg": FrameAtoms(numbers=["+3"])}),
    )
    assert ok == []


def test_decimal_vs_integer_distinguished(tmp_path):
    """The 0.1% vs 1% case: a wrong rounding is caught."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "f.jpg").write_bytes(b"x")
    md = "![F1 ≈ 1%](frames/f.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"f.jpg": FrameAtoms(numbers=["0.1%", "58%"])}),
    )
    assert len(issues) == 1 and "1%" in issues[0].hallucinations


def test_unconfirmed_term_is_warning_not_blocking(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "g.jpg").write_bytes(b"x")
    md = "![на схеме «Arcane Surge»](frames/g.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"g.jpg": FrameAtoms(terms=["Energy Shield"])}),
    )
    assert len(issues) == 1 and "Arcane Surge" in issues[0].unconfirmed
    assert not issues[0].is_blocking(strict=False)   # warning by default
    assert issues[0].is_blocking(strict=True)        # blocks under --strict


def test_term_confirmed_with_extraction_noise(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "g.jpg").write_bytes(b"x")
    md = "![на схеме «Векторная БД»](frames/g.jpg)\n"
    issues = _verify(
        md, tmp_path,
        atoms_fn=_fake_atoms({"g.jpg": FrameAtoms(
            terms=["3. Складываем все векторы в Векторную БД"],
        )}),
    )
    assert issues == []


def test_missing_atoms_raises(tmp_path):
    """A frame with no atoms.json (extraction not run) is an error, not a pass."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "x.jpg").write_bytes(b"x")
    md = "![+4 to Spell Skills](frames/x.jpg)\n"
    import pytest
    with pytest.raises(RuntimeError, match="No blind-extracted atoms"):
        verify_markdown_grounding(md, tmp_path)  # default cache reader, no file


def test_sparse_visual_frame_not_flagged(tmp_path):
    """A legit text-sparse content frame (a digit-in-grid) whose caption is
    fully confirmed must pass — there is no atom-count 'low content' guard."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "grid.jpg").write_bytes(b"x")
    md = "![сетка «28px» × «28px»](frames/grid.jpg)\n"
    assert verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"grid.jpg": FrameAtoms(
            numbers=["28", "28"], terms=["28px", "28px"],
        )}),
    ) == []


# --- transcript outranks vision (W1) -------------------------------------

def test_number_in_transcript_is_warning_not_blocking(tmp_path):
    """A number the frame draws rather than labels (so the blind extractor
    misses it) but the author states in the transcript is grounded: a
    non-blocking transcript_grounded warning, not a fabrication."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "digit.jpg").write_bytes(b"x")
    md = "![рукописная цифра «3» на сетке](frames/digit.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"digit.jpg": FrameAtoms(terms=["28px"])}),
        transcript="а вот рукописная тройка 3, разложенная по 784 пикселям",
    )
    assert len(issues) == 1
    assert "3" in issues[0].transcript_grounded
    assert not issues[0].hallucinations
    assert not issues[0].is_blocking(strict=False)  # transcript outranks vision
    assert issues[0].is_blocking(strict=True)        # strict demands on-frame


def test_number_in_neither_is_blocking_hallucination(tmp_path):
    """A number absent from BOTH frame and transcript stays a blocking
    hallucination — the transcript layer doesn't weaken real fabrication."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "f.jpg").write_bytes(b"x")
    md = "![точность «99%»](frames/f.jpg)\n"
    issues = verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"f.jpg": FrameAtoms(numbers=["58%"])}),
        transcript="мы говорим только про вход и скрытые слои",
    )
    assert len(issues) == 1 and "99%" in issues[0].hallucinations
    assert issues[0].is_blocking(strict=False)


def test_term_in_transcript_clears_unconfirmed(tmp_path):
    """A quoted term the frame lacks but the author speaks is not flagged."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "g.jpg").write_bytes(b"x")
    md = "![на схеме «сигмоида»](frames/g.jpg)\n"
    assert verify_markdown_grounding(
        md, tmp_path,
        atoms_fn=_fake_atoms({"g.jpg": FrameAtoms(terms=["Sigmoid"])}),
        transcript="эту функцию называют сигмоида, она сжимает в 0..1",
    ) == []


def test_missing_image_file_flagged(tmp_path):
    md = "![+4 something](frames/nope.jpg)\n"
    issues = verify_markdown_grounding(md, tmp_path, atoms_fn=_fake_atoms({}))
    assert len(issues) == 1 and "not found" in issues[0].hallucinations[0]


def test_data_uri_and_captionless_skipped(tmp_path):
    md = (
        "![](frames/x.jpg)\n"                    # no caption → skip
        "![cap](data:image/jpeg;base64,AAA)\n"   # data uri → skip
    )
    assert verify_markdown_grounding(md, tmp_path, atoms_fn=_fake_atoms({})) == []


# --- atom cache round-trip + mtime invalidation --------------------------

def test_atoms_cache_roundtrip_and_staleness(tmp_path):
    img = tmp_path / "f.jpg"
    img.write_bytes(b"x")
    write_frame_atoms(img, FrameAtoms(numbers=["+3"], terms=["Spirit"]))
    loaded = load_frame_atoms(img)
    assert loaded and loaded.numbers == ["+3"] and loaded.terms == ["Spirit"]
    # Re-cropping (frame newer than cache) invalidates the cache.
    import os
    cache = tmp_path / "f.jpg.atoms.json"
    os.utime(img, (cache.stat().st_mtime + 10, cache.stat().st_mtime + 10))
    assert load_frame_atoms(img) is None
