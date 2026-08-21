"""Dashboard inline keyboards for the Telegram Mini Dashboard (Sprint 3.1).

Keyboards are created as pure functions — no shared state — consistent with
the existing onboarding keyboard pattern. Callback data strings encode the
intended action so a single :class:`CallbackQueryHandler` can route all
dashboard interactions.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ---------------------------------------------------------------------------
# Callback data constants
# ---------------------------------------------------------------------------

DASHBOARD_CAPTURE = "dashboard:capture"
DASHBOARD_MEMORIES = "dashboard:memories"
DASHBOARD_INSIGHTS = "dashboard:insights"
DASHBOARD_TODAY = "dashboard:today"
DASHBOARD_PROGRESS = "dashboard:progress"
DASHBOARD_GROWTH = "dashboard:growth"
DASHBOARD_WEEKLY = "dashboard:weekly"
DASHBOARD_PROFILE = "dashboard:profile"
DASHBOARD_HELP = "dashboard:help"
DASHBOARD_ASK = "dashboard:ask"

_CAP_BTN = "\u2795 Capture Memory"


def build_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Build the main dashboard inline keyboard.

    ``Capture Memory`` is placed first so it appears visually prominent
    at the top of the keyboard.

    Returns:
        An :class:`InlineKeyboardMarkup` with all dashboard buttons.
    """
    keyboard = [
        [InlineKeyboardButton(_CAP_BTN, callback_data=DASHBOARD_CAPTURE)],
        [
            InlineKeyboardButton("📖 My Memories", callback_data=DASHBOARD_MEMORIES),
            InlineKeyboardButton("🧠 My Insights", callback_data=DASHBOARD_INSIGHTS),
        ],
        [
            InlineKeyboardButton("📈 My Progress", callback_data=DASHBOARD_PROGRESS),
            InlineKeyboardButton("💬 Ask Memo", callback_data=DASHBOARD_ASK),
        ],
        [
            InlineKeyboardButton("📈 My Growth", callback_data=DASHBOARD_GROWTH),
            InlineKeyboardButton("🗓 Weekly Reflection", callback_data=DASHBOARD_WEEKLY),
        ],
        [
            InlineKeyboardButton("📅 Today's Journey", callback_data=DASHBOARD_TODAY),
            InlineKeyboardButton("⚙️ My Profile", callback_data=DASHBOARD_PROFILE),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data=DASHBOARD_HELP),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_capture_button_keyboard() -> InlineKeyboardMarkup:
    """Build a single-button keyboard for prompting capture.

    Used in empty-state messages to let users immediately start capturing.
    """
    keyboard = [
        [InlineKeyboardButton(_CAP_BTN, callback_data=DASHBOARD_CAPTURE)],
    ]
    return InlineKeyboardMarkup(keyboard)
