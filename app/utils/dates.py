"""Date parsing and formatting utilities.

Centralises all date handling so that format strings are never duplicated
across the codebase. Supports the formats that students are most likely to
type naturally.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final

# Ordered from most-to-least common to minimise failed parse attempts.
_SUPPORTED_FORMATS: Final[tuple[str, ...]] = (
    "%d/%m/%Y",  # 15/09/2025  (primary)
    "%d-%m-%Y",  # 15-09-2025
    "%d.%m.%Y",  # 15.09.2025
    "%Y-%m-%d",  # 2025-09-15  (ISO 8601)
)

_DISPLAY_FORMAT: Final[str] = "%d/%m/%Y"


def parse_date(text: str) -> date | None:
    """Attempt to parse a date string using several common formats.

    Tries each supported format in order and returns the first successful
    parse. Returns ``None`` rather than raising so callers can provide
    user-friendly error messages instead of catching exceptions.

    Args:
        text: The raw user-supplied date string.

    Returns:
        A :class:`date` object on success, or ``None`` if no format matched.
    """
    stripped = text.strip()
    for fmt in _SUPPORTED_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def format_date(d: date) -> str:
    """Format a date for display to users.

    Args:
        d: The date to format.

    Returns:
        A string in ``DD/MM/YYYY`` format.
    """
    return d.strftime(_DISPLAY_FORMAT)
