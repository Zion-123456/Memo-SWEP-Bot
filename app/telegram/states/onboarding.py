"""Onboarding conversation states.

Using an IntEnum makes states compatible with PTB's ConversationHandler
which expects integer state values, while keeping the names human-readable
in logs and in the Conversation database table.
"""

from __future__ import annotations

from enum import IntEnum


class OnboardingState(IntEnum):
    """States for the /start onboarding ConversationHandler.

    Each state represents what the bot is *waiting for* from the user.
    The name of each state is stored as a string in the Conversation table
    for observability.
    """

    AWAITING_FIRST_NAME = 0
    AWAITING_UNIVERSITY = 1
    AWAITING_DEPARTMENT = 2
    AWAITING_PROGRAMME = 3
    AWAITING_COMPANY = 4
    AWAITING_START_DATE = 5
    AWAITING_END_DATE = 6
