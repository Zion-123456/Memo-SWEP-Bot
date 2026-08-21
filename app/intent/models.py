"""Strongly-typed intent classification models.

Every user message is classified into exactly one :class:`IntentType`
with an associated confidence score and optional structured metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class IntentType(StrEnum):
    """The high-level intent behind a user message."""

    CAPTURE = "capture"
    RETRIEVE = "retrieve"
    REFLECT = "reflect"
    ACTION = "action"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """The result of classifying a single user message.

    Attributes:
        intent: The classified intent type.
        confidence: A float in [0.0, 1.0] indicating classification confidence.
        query: The cleaned query text (for RETRIEVE/REFLECT), if applicable.
        action: A normalised action keyword (for ACTION), if applicable.
        time_range: A natural-language time range (e.g. "today", "this week"),
            if the user specified one.
        topic: A topic keyword the user is interested in, if extractable.
        raw_text: The original (unmodified) user message that was classified.
    """

    intent: IntentType
    confidence: float = 0.0
    query: str | None = None
    action: str | None = None
    time_range: str | None = None
    topic: str | None = None
    raw_text: str | None = None
    model_used: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_capture(self) -> bool:
        return self.intent == IntentType.CAPTURE

    @property
    def is_retrieval(self) -> bool:
        return self.intent == IntentType.RETRIEVE

    @property
    def is_reflection(self) -> bool:
        return self.intent == IntentType.REFLECT

    @property
    def is_action(self) -> bool:
        return self.intent == IntentType.ACTION

    @property
    def is_conversation(self) -> bool:
        return self.intent == IntentType.CONVERSATION

    def should_capture(self) -> bool:
        """Return True only if the intent indicates the message should become a memory.

        This is the single gate that prevents questions/commands from being
        accidentally stored as events.
        """
        return self.intent == IntentType.CAPTURE
