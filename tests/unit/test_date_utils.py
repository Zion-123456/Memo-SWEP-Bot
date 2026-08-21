"""Unit tests for date parsing utilities."""

from datetime import date

import pytest

from app.utils.dates import format_date, parse_date


@pytest.mark.parametrize(
    ("input_str", "expected"),
    [
        ("15/09/2025", date(2025, 9, 15)),
        ("15-09-2025", date(2025, 9, 15)),
        ("15.09.2025", date(2025, 9, 15)),
        ("2025-09-15", date(2025, 9, 15)),
        ("  15/09/2025  ", date(2025, 9, 15)),  # Tests stripping
    ],
)
def test_parse_date_valid_formats(input_str: str, expected: date) -> None:
    assert parse_date(input_str) == expected


@pytest.mark.parametrize(
    "input_str",
    [
        "invalid",
        "15/13/2025",  # Invalid month
        "32/09/2025",  # Invalid day
        "",
    ],
)
def test_parse_date_invalid_formats(input_str: str) -> None:
    assert parse_date(input_str) is None


def test_format_date() -> None:
    d = date(2025, 9, 15)
    assert format_date(d) == "15/09/2025"
