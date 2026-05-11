"""Tests for analyze.select_parser — parse 1-based comma/range strings."""
import pytest

from skills.youtube_transcribe.analyze.select_parser import parse_select


def test_single_index():
    assert parse_select("3", total=10) == [2]


def test_comma_separated():
    assert parse_select("1,3,5", total=10) == [0, 2, 4]


def test_range():
    assert parse_select("2-5", total=10) == [1, 2, 3, 4]


def test_mixed():
    assert parse_select("1,3,5-7", total=10) == [0, 2, 4, 5, 6]


def test_dedups_and_sorts():
    assert parse_select("5,3,5,3-4", total=10) == [2, 3, 4]


def test_whitespace_tolerant():
    assert parse_select(" 1 , 3 - 5 ", total=10) == [0, 2, 3, 4]


def test_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_select("", total=10)


def test_zero_raises():
    with pytest.raises(ValueError, match="1-based"):
        parse_select("0", total=10)


def test_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        parse_select("1,15", total=10)


def test_reverse_range_raises():
    with pytest.raises(ValueError, match="invalid range"):
        parse_select("5-3", total=10)


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_select("abc", total=10)
