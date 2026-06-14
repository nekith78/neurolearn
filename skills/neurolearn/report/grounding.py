"""Grounding check for visual reports — does the text match the screenshots?

A guide's prose can drift from what its screenshots actually show: a caption
emphasises a stat the crop cut off, claims a value the frame doesn't display,
or says an item goes somewhere the tooltip contradicts. This module catches
that class mechanically: for each image referenced in the Markdown, OCR the
(cropped) frame and check that the *checkable claims* in its caption — game
terms (Latin words) and numbers/percentages — actually appear on the image.

It's a surfacing aid, not an oracle: OCR is imperfect and a caption may
legitimately reference a value from another step, so unresolved items are
WARNINGS the author reviews (use `--strict` to make them blocking). The point
is that a text↔image mismatch can no longer ship silently.

OCR uses easyocr (the `ocr` extra) and is cached per frame, so re-runs are
instant. The OCR function is injectable so tests don't need easyocr/torch.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Markdown image: ![caption](src)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# Latin game terms worth checking (≥4 letters); short words are too noisy.
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{3,}")
# Numbers / percentages as written: +4, 36%, +59, 200%.
_NUMBER_TOKEN_RE = re.compile(r"[+\-]?\d+%?")
# Latin words that carry no claim — skip so we don't flag filler.
_STOPWORDS = {
    "with", "this", "that", "from", "into", "your", "here", "item", "items",
    "show", "shows", "tooltip", "panel", "screen", "right", "left", "frame",
}
_FUZZY_THRESHOLD = 0.80


@dataclass
class GroundingIssue:
    """One image whose caption makes claims not found on the image."""
    image: str
    caption: str
    missing: list[str] = field(default_factory=list)
    ocr_excerpt: str = ""


def _normalize(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9%]+", " ", text).upper().strip()


def extract_claim_tokens(caption: str) -> list[str]:
    """Pull the checkable claims out of a caption: Latin game terms (≥4 chars,
    minus filler) and number/percentage strings. In a Russian caption the
    Latin tokens are naturally the English on-screen terms."""
    tokens: list[str] = []
    seen: set[str] = set()
    for m in _LATIN_TOKEN_RE.finditer(caption):
        w = m.group(0)
        key = w.lower()
        if key in _STOPWORDS or key in seen:
            continue
        seen.add(key)
        tokens.append(w)
    for m in _NUMBER_TOKEN_RE.finditer(caption):
        n = m.group(0)
        if n not in seen:
            seen.add(n)
            tokens.append(n)
    return tokens


def _token_found(token: str, ocr_norm: str, ocr_words: list[str]) -> bool:
    """Is `token` present in the OCR text, tolerant of OCR errors?"""
    digits = re.sub(r"\D", "", token)
    if digits and re.fullmatch(r"[+\-]?\d+%?", token):
        # Number claim: the digit run must appear in the OCR's digit runs.
        return any(digits in re.sub(r"\D", "", w) for w in ocr_words if w)
    t = _normalize(token)
    if not t:
        return True
    if t in ocr_norm:  # fast exact path
        return True
    return any(
        difflib.SequenceMatcher(None, t, w).ratio() >= _FUZZY_THRESHOLD
        for w in ocr_words
    )


def verify_markdown_grounding(
    markdown_text: str,
    batch_dir: Path | str,
    *,
    ocr_fn: Callable[[Path], str] | None = None,
) -> list[GroundingIssue]:
    """For every image in the Markdown, OCR its (cropped) frame and report the
    caption claims not found on it. `ocr_fn` defaults to the cached easyocr
    backend; inject a fake in tests."""
    batch_dir = Path(batch_dir)
    ocr = ocr_fn or _default_ocr
    issues: list[GroundingIssue] = []
    for m in _MD_IMAGE_RE.finditer(markdown_text):
        caption, src = m.group(1).strip(), m.group(2).strip()
        if src.startswith("data:") or not caption:
            continue
        img_path = batch_dir / src
        if not img_path.exists():
            issues.append(GroundingIssue(
                image=src, caption=caption,
                missing=["<image file not found>"], ocr_excerpt="",
            ))
            continue
        try:
            ocr_text = ocr(img_path) or ""
        except RuntimeError:
            raise
        except Exception:
            ocr_text = ""
        ocr_norm = _normalize(ocr_text)
        ocr_words = ocr_norm.split()
        missing = [
            tok for tok in extract_claim_tokens(caption)
            if not _token_found(tok, ocr_norm, ocr_words)
        ]
        if missing:
            issues.append(GroundingIssue(
                image=src, caption=caption, missing=missing,
                ocr_excerpt=ocr_text[:200],
            ))
    return issues


# --- OCR backend (easyocr, cached, lazy) ---------------------------------
_READER = None


def _get_reader():
    global _READER
    if _READER is None:
        try:
            import easyocr
        except ImportError as e:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Grounding check needs OCR. Install: uv sync --extra ocr"
            ) from e
        _READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _READER


def _default_ocr(image_path: Path) -> str:
    """OCR a frame with easyocr, cached to `<frame>.ocr.json` so repeat runs
    don't re-OCR (the slow part)."""
    cache = Path(str(image_path) + ".ocr.json")
    # Use the cache only if it's newer than the frame — re-cropping reuses the
    # same filename, so a stale cache would OCR the old crop.
    if cache.exists() and cache.stat().st_mtime >= Path(image_path).stat().st_mtime:
        try:
            return json.loads(cache.read_text(encoding="utf-8")).get("text", "")
        except (OSError, json.JSONDecodeError):
            pass
    text = " ".join(_get_reader().readtext(str(image_path), detail=0))
    try:
        cache.write_text(json.dumps({"text": text}), encoding="utf-8")
    except OSError:
        pass
    return text
