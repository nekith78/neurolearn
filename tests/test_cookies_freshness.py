"""Tests for utils.cookies_freshness — mtime-based staleness detection."""
import os
import time
from pathlib import Path

from skills.neurolearn.utils.cookies_freshness import (
    cookies_age_days, is_cookies_stale,
)


def _aged_file(tmp_path: Path, days: float) -> Path:
    p = tmp_path / "cookies.txt"
    p.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    past = time.time() - days * 86400.0
    os.utime(p, (past, past))
    return p


def test_age_none_for_missing():
    assert cookies_age_days("") is None
    assert cookies_age_days("/no/such/cookies.txt") is None


def test_age_fresh_is_near_zero(tmp_path):
    p = _aged_file(tmp_path, 0)
    age = cookies_age_days(p)
    assert age is not None and age < 0.1


def test_age_reports_backdated(tmp_path):
    p = _aged_file(tmp_path, 5)
    age = cookies_age_days(p)
    assert age is not None and 4.5 < age < 5.5


def test_fresh_not_stale(tmp_path):
    assert is_cookies_stale(_aged_file(tmp_path, 1)) is False


def test_old_is_stale(tmp_path):
    assert is_cookies_stale(_aged_file(tmp_path, 4)) is True


def test_missing_not_stale():
    # Nothing to refresh → not "stale".
    assert is_cookies_stale("/no/such/cookies.txt") is False


def test_custom_threshold(tmp_path):
    p = _aged_file(tmp_path, 2)
    assert is_cookies_stale(p, max_age_days=1.0) is True
    assert is_cookies_stale(p, max_age_days=5.0) is False
