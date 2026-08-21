"""Reply keyboard builders for the onboarding flow.

Keyboard markup is kept in a dedicated module so that handler code stays
focused on logic rather than presentation. All keyboards are created as
pure functions — no shared state.
"""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove


def remove_keyboard() -> ReplyKeyboardRemove:
    """Return a markup object that hides any active reply keyboard.

    Returns:
        A :class:`ReplyKeyboardRemove` instance.
    """
    return ReplyKeyboardRemove()


def date_format_hint_keyboard() -> ReplyKeyboardMarkup:
    """Return a keyboard showing date format examples.

    Tapping a suggestion fills the text input with that example, which
    reduces formatting errors without forcing a button-driven flow.

    Returns:
        A one-row :class:`ReplyKeyboardMarkup` with date examples.
    """
    return ReplyKeyboardMarkup(
        [["01/09/2025", "15/09/2025", "01/10/2025"]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="DD/MM/YYYY",
    )
