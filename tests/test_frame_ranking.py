"""Tests for content-aware keyframe ranking (Phase A): slide-likeness,
face penalty, stability, with sharpness demoted to a tie-breaker."""
import numpy as np
import pytest

from skills.neurolearn.vision import frames as F

cv2 = pytest.importorskip("cv2")


def _slide_img():
    """A flat diagram/slide: near-white background, a couple of solid blocks
    and lines — few discrete colours, low entropy."""
    img = np.full((180, 280, 3), 245, np.uint8)
    img[20:60, 20:200] = (60, 60, 200)   # a coloured box
    img[80:120, 20:260] = (40, 40, 40)   # a dark code block
    img[140:150, 20:260] = (40, 40, 40)  # a line of "text"
    return img


def _photo_img():
    """A photographic / noisy frame: rich, broad colour distribution."""
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (180, 280, 3), dtype=np.uint8)


def test_slide_likeness_separates_slide_from_photo():
    assert F._slide_likeness(_slide_img()) > 0.6
    assert F._slide_likeness(_photo_img()) < 0.35


def test_rank_prefers_slide_over_photo(tmp_path):
    s = tmp_path / "slide.jpg"
    p = tmp_path / "photo.jpg"
    cv2.imwrite(str(s), _slide_img())
    cv2.imwrite(str(p), _photo_img())
    scores = F._rank_candidates([s, p])
    assert scores is not None
    assert scores[0] > scores[1]  # slide outranks the photo


def test_sharpness_is_only_a_tiebreaker(tmp_path):
    """A sharper photo must NOT beat a less-sharp slide — the core fix for the
    talking-head/meme bug, where a face/photo is sharper than a flat diagram."""
    s = tmp_path / "slide.jpg"
    p = tmp_path / "photo.jpg"
    cv2.imwrite(str(s), _slide_img())
    cv2.imwrite(str(p), _photo_img())
    assert F.frame_sharpness(p) > F.frame_sharpness(s)  # photo is sharper…
    scores = F._rank_candidates([s, p])
    assert scores[0] > scores[1]                         # …yet slide wins


def test_no_face_detected_on_noise():
    assert F._has_large_face(_photo_img()[..., 0]) is False


def test_stability_high_for_static_low_for_changing():
    a = np.zeros((64, 64), np.uint8)
    b = a.copy()
    c = np.full((64, 64), 255, np.uint8)  # very different neighbour
    stab = F._stability([a, b, c])
    # b sits between an identical frame and a very different one;
    # a sits next to an identical frame → a more stable than c.
    assert stab[0] > stab[2]


# --- A3: near-identical frame dedup within a window -----------------------

def _write_jpg(path, arr):
    import cv2 as _cv2
    _cv2.imwrite(str(path), arr)


def test_dedup_drops_near_identical_keeps_distinct(tmp_path):
    """Two byte-identical frames + one visually distinct → the duplicate is
    dropped, the distinct one survives (order preserved)."""
    a = np.zeros((180, 280, 3), np.uint8)
    a[40:140, 40:240] = (200, 50, 50)            # a solid block (structure)
    checker = np.indices((180, 280)).sum(axis=0) % 20 < 10
    c = (checker[..., None] * np.uint8(255)).repeat(3, axis=2).astype(np.uint8)

    pa = tmp_path / "w_0.jpg"; _write_jpg(pa, a)
    pb = tmp_path / "w_1.jpg"; _write_jpg(pb, a)   # identical to A
    pc = tmp_path / "w_2.jpg"; _write_jpg(pc, c)   # different structure

    pytest.importorskip("imagehash")
    kept = F.dedup_near_identical([pa, pb, pc])
    assert kept == [pa, pc]                        # B dropped, order kept


def test_dedup_passthrough_single_or_unreadable(tmp_path):
    """<2 frames → unchanged; unreadable images → kept (never drops signal)."""
    one = tmp_path / "only.jpg"
    one.write_bytes(b"not-an-image")
    assert F.dedup_near_identical([one]) == [one]
    two = tmp_path / "x.jpg"; two.write_bytes(b"also-bad")
    assert F.dedup_near_identical([one, two]) == [one, two]
