"""Intent classification module.

Uses the existing :class:`~app.ai.provider.AIProvider` abstraction so the
intent classifier is provider-independent. Falls back to a deterministic
regex-based classifier when AI is unavailable or disabled.
"""

from __future__ import annotations

import asyncio
import re

import structlog

from app.ai.exceptions import AIError
from app.ai.provider import AIProvider
from app.config.settings import get_settings
from app.intent.models import IntentResult, IntentType
from app.intent.prompts.classification import (
    build_intent_messages,
    parse_intent_response,
)

logger = structlog.get_logger(__name__)

# Confidence threshold below which we fall back to the rule-based classifier.
_CONFIDENCE_THRESHOLD = 0.6
# Timeout for the AI classification call (must be fast — high frequency).
_CLASSIFY_TIMEOUT_SECONDS = 8.0


class IntentClassifier:
    """Classifies user messages into intents using an AIProvider backend.

    When AI is disabled or fails, a deterministic rule-based fallback is used
    so classification never blocks the bot.

    Args:
        ai_provider: The backend implementing the AIProvider protocol.
        model: Optional model override for intent classification. If not
            provided, falls back to ``INTENT_MODEL`` env var, then the
            provider's default model.
        enabled: If False, always uses the rule-based fallback.
    """

    def __init__(
        self,
        ai_provider: AIProvider | None,
        *,
        model: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._provider = ai_provider
        settings = get_settings()
        self._model = model or settings.intent_model
        self._enabled = enabled if enabled is not None else settings.ai_enabled

    @property
    def is_enabled(self) -> bool:
        """Return True if AI-based classification is available and enabled."""
        return self._enabled and self._provider is not None

    async def classify(self, text: str) -> IntentResult:
        """Classify a user message.

        Args:
            text: The raw user message (already stripped).

        Returns:
            An :class:`IntentResult` with the classified intent and metadata.
        """
        if not text or not text.strip():
            return IntentResult(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                raw_text=text,
            )

        if self.is_enabled and self._provider is not None:
            result = await self._classify_with_ai(text)
            if result is not None:
                return result

        # Fallback: deterministic rule-based classification.
        return self._classify_with_rules(text)

    async def _classify_with_ai(self, text: str) -> IntentResult | None:
        """Attempt AI-based classification. Returns None on any failure."""
        assert self._provider is not None
        messages = build_intent_messages(text)
        try:
            completion = await asyncio.wait_for(
                self._provider.classify_intent(messages, model=self._model),
                timeout=_CLASSIFY_TIMEOUT_SECONDS,
            )
        except (AIError, TimeoutError, Exception) as exc:
            logger.warning(
                "intent.classification_ai_failed",
                error=str(exc),
            )
            return None

        if not completion:
            return None

        content = completion.strip()
        if not content:
            return None

        intent, metadata = parse_intent_response(content)
        confidence = float(metadata.get("confidence", 0.0)) if metadata else 0.0
        model = metadata.get("model_used", self._model) if metadata else self._model

        if confidence < _CONFIDENCE_THRESHOLD:
            # Low confidence from AI — fall back to rules.
            logger.debug(
                "intent.low_confidence_fallback",
                confidence=confidence,
            )
            return None

        return IntentResult(
            intent=intent,
            confidence=confidence,
            query=metadata.get("query"),
            action=metadata.get("action"),
            time_range=metadata.get("time_range"),
            topic=metadata.get("topic"),
            raw_text=text,
            model_used=model,
        )

    def _classify_with_rules(self, text: str) -> IntentResult:
        """Deterministic fallback classifier based on keyword patterns.

        This handles the most common cases robustly when AI is unavailable
        or returns low confidence.
        """
        lower = text.lower().strip()
        stripped = text.strip()

        # --- ACTION ---
        action_patterns = [
            r"^\s*/(start|menu|today|timeline|insights|delete|help|profile)\b",
            r"\b(delete|remove)\s+(that|the|today's|this)\s*(memory|memories|note)?\b",
            r"\b(show|open)\s+(my|the)\s+(dashboard|profile|menu)\b",
            r"\b(help|start|begin)\s*(my|the)?\s*(swep|logbook)?\b",
        ]
        for pattern in action_patterns:
            if re.search(pattern, lower):
                return IntentResult(
                    intent=IntentType.ACTION,
                    confidence=0.8,
                    action=lower,
                    raw_text=stripped,
                )

        # --- CONVERSATION ---
        conversation_patterns = [
            r"^(hi|hello|hey|héllo|heya)\b",
            r"^(thanks?|thank you|thx)\b",
            r"\b(how (are|r) you|how's it going|what's up|hi there)\b",
            r"\b(interesting|cool|awesome|great|nice|ok|okay|sure|got it|right)\b",
            r"\b(what can you do|how does this work|what (are|r) you)",
            r"\b(how (do|does) (this|memo|it) work)",
        ]
        for pattern in conversation_patterns:
            if re.search(pattern, lower):
                return IntentResult(
                    intent=IntentType.CONVERSATION,
                    confidence=0.85,
                    raw_text=stripped,
                )

        is_question = "?" in text or text.lower().startswith(
            ("what", "how", "did", "do", "can", "show")
        )

        # --- REFLECT (check before RETRIEVE to disambiguate overlapping cases) ---
        # REFLECT asks for analysis of patterns/progress/skills across memories.
        reflect_patterns = [
            r"\b(how have i (progressed|made progress|improved|developed|better))",
            r"\b(how (much|far) have i (learned|come|progressed|improved))",
            r"\b(what skills am i developing|what am i getting better at)",
            r"\b(what have i learned)",
            r"\b(what should i improve|what are my strengths|my weaknesses)",
            r"\b(what problems have i (encountered|had))"
            r"|\biggest things i've learned\b",
            r"\b(how is my progress|how have i made progress)",
            r"\b(what's my (learning|progress) so far)",
            r"\b(analyze|analyse)\s+(my|the)\s+"
            r"(progress|learning|memories|journey)",
            r"\b(what patterns|what have i been spending)",
            r"\b(what are the biggest|how much have i learned)",
        ]
        for pattern in reflect_patterns:
            if re.search(pattern, lower):
                return IntentResult(
                    intent=IntentType.REFLECT,
                    confidence=0.8,
                    query=stripped,
                    raw_text=stripped,
                )

        # --- RETRIEVE (questions asking for facts already recorded) ---
        retrieve_patterns = [
            r"\b(what did i (learn|do|work on|record|study|see|observe))",
            r"\b(show me|show my|show the)\b" r".*\b(memories|notes|entries|records)\b",
            r"\b(do you remember|can you remember)\b",
            r"\bwhat have i (done|learned|studied|recorded|worked on|captured)",
        ]
        for pattern in retrieve_patterns:
            if re.search(pattern, lower):
                return IntentResult(
                    intent=IntentType.RETRIEVE,
                    confidence=0.75,
                    query=stripped,
                    raw_text=stripped,
                )

        # --- CAPTURE heuristics ---
        # Explicit "remember that" prefix → CAPTURE
        if re.search(r"^\s*(remember|remember that|remind me|reminder)\b", lower):
            # But NOT "do you remember" or "can you remember" — those are retrieve.
            if not re.search(r"\b(do you remember|can you remember)\b", lower):
                return IntentResult(
                    intent=IntentType.CAPTURE,
                    confidence=0.7,
                    query=stripped,
                    raw_text=stripped,
                )

        # Declarative statements with "I" + past tense or learning verbs → CAPTURE
        capture_patterns = [
            r"\bi(?:['\u2019]?\s*(ve|have))?\s+"
            r"(learned|studied|worked on|did|spent|attended|saw|observed|"
            r"struggled with|practised|practiced|completed|built|created|"
            r"implemented|designed|tested|debugged|wrote|read|reviewed|"
            r"participated|met|collaborated|discovered|figured out)",
            r"\bi\s+(was|am|have been)\s+"
            r"(learning|studying|working on|struggling with|building|working)",
            r"^\s*(today i|i today|today|i spent|i worked|i studied|"
            r"i learned|i observed|i struggled|i attended)",
            r"\bi\s+(remember|recall|noticed|realized|realised|"
            r"thought|felt)\s+(that)?\b",
            r"^\s*(we had|we attended|we met|we discussed|"
            r"we reviewed|we worked|we observed)",
            r"\b(today|this week|this morning|this afternoon|this evening)\b"
            r".*\b(learned|studied|worked|attended|observed|discussed|"
            r"met|completed)\b",
            r"\bi have (learned|studied|worked on|done)\b",
        ]
        for pattern in capture_patterns:
            if re.search(pattern, lower):
                return IntentResult(
                    intent=IntentType.CAPTURE,
                    confidence=0.7,
                    query=stripped,
                    raw_text=stripped,
                )

        # Default: if it's a question and we couldn't classify it, assume RETRIEVE.
        if is_question:
            return IntentResult(
                intent=IntentType.RETRIEVE,
                confidence=0.4,
                query=stripped,
                raw_text=stripped,
            )

        # Not a question, not a known action/conversation → unknown with low confidence.
        return IntentResult(
            intent=IntentType.UNKNOWN,
            confidence=0.3,
            raw_text=stripped,
        )
