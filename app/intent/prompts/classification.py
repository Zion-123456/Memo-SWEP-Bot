"""Strict structured-output prompt for intent classification.

The classifier is instructed to return exactly one label and optional
metadata. The prompt is deliberately compact to keep token usage low
for this high-frequency operation.
"""

from __future__ import annotations

from typing import Any

from app.intent.models import IntentType

INTENT_SYSTEM_PROMPT: str = """\
You are Memo's intent classifier. Classify the user's message into exactly one intent.

INTENTS:
- capture: user is reporting an experience, observation, learning, task,
  problem, achievement, or event they want remembered.
  E.g. "Today I learned about drilling." / "I struggled with the production
  workflow." / "Remember that I studied reservoir engineering."
- retrieve: user asks what has already been recorded.
  E.g. "What did I learn today?" / "Show me my memories about drilling."
- reflect: user asks Memo to analyse patterns, progress, development,
  strengths, weaknesses, learning, or lessons across memories.
  E.g. "How have I progressed?" / "What skills am I developing?" /
  "What should I improve?"
- action: user explicitly asks Memo to perform an operation.
  E.g. "Delete that memory." / "Open my dashboard." / "Help me."
- conversation: greetings, thanks, general questions about Memo, or
  casual conversation. E.g. "Hello." / "What can you do?"
- unknown: confidence is insufficient.

CRITICAL: Never classify a question (containing "?", "what", "how",
"did I", "have I", "can you", "show me", "tell me") as capture.
Questions about past actions are RETRIEVE or REFLECT, not CAPTURE.

Return a JSON object with keys:
- intent: one of capture, retrieve, reflect, action, conversation, unknown
- confidence: float 0.0-1.0
- query: cleaned question text if retrieve/reflect, else null
- action: normalised action keyword if action, else null
- time_range: detected time range if any (e.g. "today", "this week",
  "yesterday"), else null
- topic: detected topic/theme if any, else null
"""


def build_intent_messages(text: str) -> list[dict[str, str]]:
    """Build the chat-completion message list for intent classification.

    Args:
        text: The raw user message to classify.

    Returns:
        A list of ``{"role", "content"}`` dicts suitable for the provider.
    """
    return [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]


def parse_intent_response(
    raw: str | dict[str, Any],
) -> tuple[IntentType, dict[str, Any]]:
    """Parse the LLM response into an :class:`IntentType` and metadata.

    Accepts either a raw JSON string or an already-parsed dict.
    Falls back to UNKNOWN for any parse failure or unknown label.
    """
    import json

    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return IntentType.UNKNOWN, {}
    elif isinstance(raw, dict):
        data = raw
    else:
        return IntentType.UNKNOWN, {}

    if not isinstance(data, dict):
        return IntentType.UNKNOWN, {}

    intent_str = str(data.get("intent", "")).strip().lower()
    try:
        intent = IntentType(intent_str)
    except ValueError:
        intent = IntentType.UNKNOWN

    metadata: dict[str, Any] = {k: v for k, v in data.items() if k != "intent"}
    return intent, metadata
