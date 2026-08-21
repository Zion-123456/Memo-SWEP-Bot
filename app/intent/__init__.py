"""Intent detection and conversational routing layer (Sprint 4).

This package classifies incoming user messages into high-level intents
(capture, retrieve, reflect, action, conversation, unknown) so that the
text handler can route them appropriately without ever confusing a
question with a memory to save.
"""

from __future__ import annotations

from app.intent.models import IntentResult, IntentType
from app.intent.router import IntentRouter

__all__ = ["IntentResult", "IntentRouter", "IntentType"]
