"""Tests for shared.date_filter — --days / --since-until parsing."""
from datetime import date, datetime, timedelta, timezone

import pytest

from skills.neurolearn.shared.date_filter import (
    DateWindow,
    parse_window,
    in_window,
)


def test_parse_days_simple():
    w = parse_window(days=30, since=None, until=None, now=date(2026, 5, 12))
    assert w.start == date(2026, 4, 12)
    assert w.end == date(2026, 5, 12)


def test_parse_since_until():
    w = parse_window(days=None, since=date(2024, 1, 1), until=date(2024, 12, 31),
                     now=date(2026, 5, 12))
    assert w.start == date(2024, 1, 1)
    assert w.end == date(2024, 12, 31)


def test_parse_since_only():
    """--since without --until defaults end to now."""
    w = parse_window(days=None, since=date(2024, 6, 1), until=None,
                     now=date(2026, 5, 12))
    assert w.start == date(2024, 6, 1)
    assert w.end == date(2026, 5, 12)


def test_parse_until_only_requires_since():
    with pytest.raises(ValueError, match="--until requires --since"):
        parse_window(days=None, since=None, until=date(2024, 12, 31),
                     now=date(2026, 5, 12))


def test_days_and_since_mutex():
    with pytest.raises(ValueError, match="mutually exclusive"):
        parse_window(days=30, since=date(2024, 1, 1), until=None,
                     now=date(2026, 5, 12))


def test_in_window_inclusive():
    w = DateWindow(start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert in_window(date(2024, 6, 15), w) is True
    assert in_window(date(2024, 1, 1), w) is True
    assert in_window(date(2024, 12, 31), w) is True
    assert in_window(date(2023, 12, 31), w) is False
    assert in_window(date(2025, 1, 1), w) is False


def test_in_window_with_datetime():
    """Accept datetime input — strip to date."""
    w = DateWindow(start=date(2024, 1, 1), end=date(2024, 1, 31))
    assert in_window(datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc), w) is True
    assert in_window(datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc), w) is False


def test_zero_days_raises():
    with pytest.raises(ValueError, match="days must be positive"):
        parse_window(days=0, since=None, until=None, now=date(2026, 5, 12))


def test_negative_days_raises():
    with pytest.raises(ValueError, match="days must be positive"):
        parse_window(days=-5, since=None, until=None, now=date(2026, 5, 12))


def test_reverse_range_raises():
    with pytest.raises(ValueError, match="--since must be before --until"):
        parse_window(days=None, since=date(2024, 12, 1), until=date(2024, 6, 1),
                     now=date(2026, 5, 12))


def test_no_args_returns_none():
    """No --days and no --since means caller decides (e.g. stateful subscribes)."""
    w = parse_window(days=None, since=None, until=None, now=date(2026, 5, 12))
    assert w is None
