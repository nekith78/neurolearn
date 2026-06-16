"""Grounding check for visual reports — does each caption match its screenshot?

A caption can drift from what its frame actually shows: it asserts a number, a
URL, or an on-screen label the frame doesn't display. This module catches that
class mechanically and **language-agnostically**, using the "blind judge"
pattern from the 2025-2026 grounding-verification literature.

How it works:

1. A vision model reads each frame **blind** — given only the cropped image,
   never the caption — and extracts the atoms it can literally see: numbers,
   URLs, and verbatim on-screen text. Atoms are cached per frame in
   `<frame>.atoms.json` (mtime-invalidated against the crop). The agent
   (Claude in chat) produces them via a *fresh blind sub-agent* that sees only
   the frames and writes the atom files — no external API (see SKILL.md). The
   grounding `--verify-backend gemini` fallback extracts them with Gemini
   instead — `make_gemini_atoms_fn`.
2. For each caption we extract its *claims* language-agnostically: numbers and
   URLs by regex (script-independent), and verbatim on-screen terms the author
   wrapped in guillemets / quotes (the captioning contract — SKILL.md).
3. We diff each claim against the frame's atoms — and, when the claim isn't on
   the frame, against the spoken **transcript** (the text outranks vision: a
   fact the author states is not a fabrication even if it's drawn rather than
   labelled). Severity:
   - **hallucination** — a number or URL on neither the frame nor the
     transcript (a fabricated fact). Blocks the render even by default.
   - **transcript_grounded** — a number/URL the author states but the frame
     doesn't display (the caption leans on words, not the picture). A WARNING;
     blocks only with `--strict`.
   - **unconfirmed** — a quoted term found on neither. A WARNING (a crop may
     have clipped it, or extraction missed small text); blocks with `--strict`.

The model is language-agnostic by construction, so there is no OCR language
list and no per-script tokenisation — the property the old OCR/token gate
lacked. Atom source and transcript are injectable so tests need no model.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Markdown image: ![caption](src)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# --- Caption claim extraction (language-agnostic) ------------------------
# Numbers / stats / percentages as written: +4, 36%, 0.1, 4.88, 124 750.
_NUMBER_RE = re.compile(
    r"(?<![\w.])(?:[+\-]?\d[\d\s.,]*\d|[+\-]?\d)%?(?![\w])",
    re.UNICODE,
)
# A URL/citation: a scheme, or a domain with a path (the dangerous case —
# fabricated citations like "arxiv.org/abs/2512.24601" carry a /path).
_URL_RE = re.compile(
    r"https?://\S+|(?:[\w-]+\.)+[\w-]{2,}/[^\s)\]»\"'”’]*", re.UNICODE
)
# Verbatim on-screen text the author quoted: «…», “…”, "…". This is the
# captioning contract — quote exact on-screen strings so they're checkable.
_QUOTED_RE = re.compile(r"«([^»]{2,})»|“([^”]{2,})”|\"([^\"]{2,})\"")

_FUZZY_THRESHOLD = 0.85


@dataclass
class FrameAtoms:
    """What a vision model read off a single frame, blind to any caption."""
    numbers: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


@dataclass
class CaptionClaims:
    """The checkable assertions pulled from one caption."""
    numbers: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


@dataclass
class GroundingIssue:
    """One image whose caption asserts something not found on the frame."""
    image: str
    caption: str
    hallucinations: list[str] = field(default_factory=list)  # numbers/URLs on neither
    transcript_grounded: list[str] = field(default_factory=list)  # stated, not on frame
    unconfirmed: list[str] = field(default_factory=list)      # quoted terms
    atoms_excerpt: str = ""

    @property
    def severity(self) -> str:
        if self.hallucinations:
            return "hallucination"
        if self.transcript_grounded:
            return "transcript_grounded"
        return "unconfirmed"

    def is_blocking(self, strict: bool) -> bool:
        # transcript_grounded / unconfirmed are advisory by default (the author
        # states the fact, or a crop may have clipped a term); --strict demands
        # everything be literally on the frame.
        return bool(self.hallucinations) or (
            strict and (bool(self.unconfirmed) or bool(self.transcript_grounded))
        )


def _norm_text(text: str) -> str:
    """Unicode-aware normalisation for term/URL comparison: NFKC, casefold,
    collapse runs of non-alphanumerics (any script) to single spaces."""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\W_]+", " ", t, flags=re.UNICODE)
    return t.casefold().strip()


def _canon_number(token: str) -> str:
    """Canonical numeric form: keep only digits and the decimal point, drop
    everything else — sign, %, currency ($, €), thousands separators (space /
    comma). '$1.50'->'1.50', '124 750'->'124750', '+4'->'4', '36%'->'36',
    '0.1'->'0.1'. Both caption and atoms go through this so they compare."""
    t = unicodedata.normalize("NFKC", token)
    t = re.sub(r"[^\d.]", "", t)
    return t.strip(".")


def extract_caption_claims(caption: str) -> CaptionClaims:
    """Pull the checkable claims from a caption, language-agnostically:
    numbers and URLs by structure (script-independent) and verbatim on-screen
    terms the author wrapped in «…» / "…". URLs are matched before numbers so a
    citation's digits aren't mistaken for standalone number claims."""
    numbers: list[str] = []
    urls: list[str] = []
    terms: list[str] = []
    seen: set[str] = set()

    url_spans: list[tuple[int, int]] = []
    for m in _URL_RE.finditer(caption):
        url_spans.append((m.start(), m.end()))
        u = m.group(0).rstrip(".,);]")
        if u.casefold() not in seen:
            seen.add(u.casefold())
            urls.append(u)

    def _in_url(pos: int) -> bool:
        return any(s <= pos < e for s, e in url_spans)

    for m in _NUMBER_RE.finditer(caption):
        if _in_url(m.start()):
            continue  # digits belong to a URL/citation, not a standalone stat
        raw = m.group(0).strip()
        canon = _canon_number(raw)
        if canon and canon not in seen:
            seen.add(canon)
            numbers.append(raw)

    for m in _QUOTED_RE.finditer(caption):
        inner = next(g for g in m.groups() if g is not None).strip()
        key = _norm_text(inner)
        if key and key not in seen:
            seen.add(key)
            terms.append(inner)

    return CaptionClaims(numbers=numbers, urls=urls, terms=terms)


def _number_confirmed(token: str, atoms: FrameAtoms) -> bool:
    canon = _canon_number(token)
    if not canon:
        return True
    canon_set = {_canon_number(n) for n in atoms.numbers}
    if canon in canon_set:
        return True
    if "." in canon:
        # Decimals need an exact match — no substring games, so "1" can't pass
        # off as present just because the frame shows "0.1".
        return False
    # Integer fallback: whole-number boundary match against every atom's digit
    # text, so a number embedded in a term string ("router.py 142 правки")
    # counts — but "+3" must NOT match inside "34" or "0.3" (digit/dot bound).
    blob = unicodedata.normalize("NFKC", " ".join(atoms.numbers + atoms.terms))
    return re.search(
        rf"(?<![\d.,]){re.escape(canon)}(?![\d.,])", blob
    ) is not None


def _url_confirmed(token: str, atoms: FrameAtoms) -> bool:
    t = _norm_text(token)
    if not t:
        return True
    blob = _norm_text(" ".join(atoms.urls + atoms.terms))
    if t in blob:
        return True
    # A URL often survives extraction with a dropped scheme or trailing slash;
    # match the most distinctive part (domain + path tail).
    tail = _norm_text(re.sub(r"^https?", "", token))
    return bool(tail) and tail in blob


def _word_match(a: str, b: str) -> bool:
    """One word matches another tolerant of inflection: containment, or a
    shared prefix covering ≥75% of the shorter (stems 'векторная'≈'векторную',
    'DODGE'≈'DODCE-ish' OCR-style drift)."""
    if a in b or b in a:
        return True
    n = min(len(a), len(b))
    if n < 4:
        return False
    common = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        common += 1
    return common >= 0.75 * n


def _phrase_confirmed(phrase: str, atoms: FrameAtoms) -> bool:
    p = _norm_text(phrase)
    if not p:
        return True
    blob = _norm_text(" ".join(atoms.terms + atoms.urls + atoms.numbers))
    if p in blob:
        return True
    # Token overlap with stem tolerance — language-agnostic (works on any
    # space-separated script; degrades gracefully on spaceless ones). A quoted
    # term is confirmed if ≥70% of its content words appear on the frame.
    p_words = [w for w in p.split() if len(w) >= 3]
    if not p_words:
        return p in blob
    blob_words = blob.split()
    hits = sum(1 for w in p_words if any(_word_match(w, bw) for bw in blob_words))
    return hits / len(p_words) >= 0.70


def _excerpt(atoms: FrameAtoms, limit: int = 220) -> str:
    parts = atoms.numbers + atoms.urls + atoms.terms
    return " | ".join(parts)[:limit]


def verify_markdown_grounding(
    markdown_text: str,
    batch_dir: Path | str,
    *,
    atoms_fn: Callable[[Path], FrameAtoms | None] | None = None,
    strict: bool = False,
    transcript: str | None = None,
) -> list[GroundingIssue]:
    """For every captioned image in the Markdown, diff the caption's claims
    against the frame's blind-extracted atoms. A number/URL not on the frame is
    a hallucination UNLESS the spoken `transcript` states it — then it's a
    non-blocking `transcript_grounded` warning (the text outranks vision: a
    fact the author states isn't a fabrication, even if the frame draws rather
    than labels it). `atoms_fn` defaults to reading the cached
    `<frame>.atoms.json`; inject a fake in tests, or `make_gemini_atoms_fn(...)`
    for the Gemini fallback. Raises RuntimeError if a frame has no atoms yet
    (the blind extraction step hasn't run)."""
    batch_dir = Path(batch_dir)
    root = batch_dir.resolve()
    get_atoms = atoms_fn or load_frame_atoms
    # The transcript becomes a second atom source: a claim the author speaks is
    # grounded even when the blind frame-extractor didn't emit it. Parse its
    # numbers/URLs with the same claim grammar (so prose punctuation — "тройка
    # 3," — doesn't trip the atom-number boundary rules); keep the raw text for
    # phrase matching.
    spoken: FrameAtoms | None = None
    if transcript:
        sc = extract_caption_claims(transcript)
        spoken = FrameAtoms(numbers=sc.numbers, urls=sc.urls, terms=[transcript])
    issues: list[GroundingIssue] = []
    for m in _MD_IMAGE_RE.finditer(markdown_text):
        caption, src = m.group(1).strip(), m.group(2).strip()
        if src.startswith("data:") or not caption:
            continue
        # Contain the path: a caption's src is author-supplied text and the
        # Markdown may come from an untrusted batch — never read outside root.
        img_path = (batch_dir / src).resolve()
        if not img_path.is_relative_to(root):
            issues.append(GroundingIssue(
                image=src, caption=caption,
                hallucinations=["<path traversal rejected>"],
            ))
            continue
        if not img_path.exists():
            issues.append(GroundingIssue(
                image=src, caption=caption,
                hallucinations=["<image file not found>"],
            ))
            continue
        atoms = get_atoms(img_path)
        if atoms is None:
            raise RuntimeError(
                f"No blind-extracted atoms for {src}. Produce them first: run "
                f"the blind sub-agent extraction (see SKILL.md), or pass "
                f"--verify-backend gemini."
            )
        claims = extract_caption_claims(caption)
        hallucinations: list[str] = []
        transcript_grounded: list[str] = []
        for n in claims.numbers:
            if _number_confirmed(n, atoms):
                continue
            if spoken and _number_confirmed(n, spoken):
                transcript_grounded.append(n)
            else:
                hallucinations.append(n)
        for u in claims.urls:
            if _url_confirmed(u, atoms):
                continue
            if spoken and _url_confirmed(u, spoken):
                transcript_grounded.append(u)
            else:
                hallucinations.append(u)
        unconfirmed = [
            t for t in claims.terms
            if not _phrase_confirmed(t, atoms)
            and not (spoken and _phrase_confirmed(t, spoken))
        ]
        if hallucinations or transcript_grounded or unconfirmed:
            issues.append(GroundingIssue(
                image=src, caption=caption,
                hallucinations=hallucinations,
                transcript_grounded=transcript_grounded,
                unconfirmed=unconfirmed,
                atoms_excerpt=_excerpt(atoms),
            ))
    return issues


# --- Atom cache (written by the agent's blind sub-agent, or by Gemini) ----

def _atoms_cache_path(image_path: Path) -> Path:
    return Path(str(image_path) + ".atoms.json")


def load_frame_atoms(image_path: Path) -> FrameAtoms | None:
    """Read `<frame>.atoms.json`, but only if it's newer than the frame —
    re-cropping reuses the filename, so a stale cache would describe the old
    crop. Returns None if absent or stale (caller decides how to react)."""
    cache = _atoms_cache_path(image_path)
    img = Path(image_path)
    if not (cache.exists() and img.exists()):
        return None
    if cache.stat().st_mtime < img.stat().st_mtime:
        return None
    try:
        d = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return FrameAtoms(
        numbers=[str(x) for x in (d.get("numbers") or [])],
        urls=[str(x) for x in (d.get("urls") or [])],
        terms=[str(x) for x in (d.get("terms") or [])],
    )


def write_frame_atoms(image_path: Path, atoms: FrameAtoms) -> None:
    """Persist atoms next to the frame so a passing report stays reproducible
    and re-runs skip re-extraction."""
    try:
        _atoms_cache_path(image_path).write_text(
            json.dumps({
                "numbers": atoms.numbers,
                "urls": atoms.urls,
                "terms": atoms.terms,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


# --- Gemini fallback: blind atom extraction (--verify-backend gemini) -----
_ATOMS_SCHEMA = {
    "type": "object",
    "properties": {
        "numbers": {"type": "array", "items": {"type": "string"}},
        "urls": {"type": "array", "items": {"type": "string"}},
        "terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["numbers", "urls", "terms"],
}
_ATOMS_PROMPT = (
    "You are given a single screenshot. Read ONLY what is literally visible in "
    "this image — do not guess, infer, or add anything not shown. Extract, "
    "verbatim and in the original language/script:\n"
    "- numbers: every number, stat, or percentage exactly as written "
    "(e.g. +3, 36%, 0.1, 124 750).\n"
    "- urls: every URL or web/citation address visible.\n"
    "- terms: every distinct on-screen text label, title, name, or UI string, "
    "verbatim.\n"
    "Return JSON with arrays numbers, urls, terms. Use empty arrays if none."
)
_GEMINI_ATOMS_TIMEOUT_S = 120


def gemini_extract_atoms(
    image_path: Path, *, api_key: str, model: str = "gemini-2.5-flash",
) -> FrameAtoms:
    """Blind extraction: send ONLY the image (never a caption) to Gemini and
    get back the atoms it can read. Language-agnostic by construction."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=0.0,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=_ATOMS_SCHEMA,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
    )
    contents = [
        _ATOMS_PROMPT,
        types.Part.from_bytes(
            data=Path(image_path).read_bytes(), mime_type="image/jpeg",
        ),
    ]
    resp = client.models.generate_content(
        model=model, contents=contents, config=config,
    )
    try:
        d = json.loads(resp.text or "{}")
    except (json.JSONDecodeError, TypeError):
        d = {}
    return FrameAtoms(
        numbers=[str(x) for x in (d.get("numbers") or [])],
        urls=[str(x) for x in (d.get("urls") or [])],
        terms=[str(x) for x in (d.get("terms") or [])],
    )


def make_gemini_atoms_fn(
    api_key: str, model: str = "gemini-2.5-flash",
) -> Callable[[Path], FrameAtoms]:
    """An atoms_fn for the --verify-backend gemini fallback: cached blind
    Gemini extraction per frame."""
    def _fn(image_path: Path) -> FrameAtoms:
        cached = load_frame_atoms(image_path)
        if cached is not None:
            return cached
        atoms = gemini_extract_atoms(image_path, api_key=api_key, model=model)
        write_frame_atoms(image_path, atoms)
        return atoms
    return _fn
