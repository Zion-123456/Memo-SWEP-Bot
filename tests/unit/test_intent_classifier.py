"""Unit tests for intent classification — covers all intent types and
the critical regression case where a question must NOT become a memory.
"""

from __future__ import annotations

import asyncio

import pytest

from app.config.settings import Settings, get_settings
from app.intent.classifier import IntentClassifier
from app.intent.models import IntentType


@pytest.fixture
def rule_classifier() -> IntentClassifier:
    """Return a rule-based classifier (AI disabled)."""
    settings = Settings(
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        database_url="postgresql+asyncpg://memo:memo@localhost:5432/memo",
        redis_url="redis://localhost:6379/0",
        app_env="development",
    )
    get_settings.cache_clear()
    import app.config.settings as cs

    cs.get_settings = lambda: settings
    return IntentClassifier(ai_provider=None, enabled=False)


@pytest.fixture
def ai_classifier() -> IntentClassifier:
    """Return an AI-backed classifier with a mock provider."""
    from unittest.mock import AsyncMock, MagicMock

    from app.ai.provider import AIProvider

    mock_provider = MagicMock(spec=AIProvider)
    mock_provider.classify_intent = AsyncMock(return_value=None)
    settings = Settings(
        telegram_bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        database_url="postgresql+asyncpg://memo:memo@localhost:5432/memo",
        redis_url="redis://localhost:6379/0",
        app_env="development",
    )
    get_settings.cache_clear()
    import app.config.settings as cs

    cs.get_settings = lambda: settings
    return IntentClassifier(ai_provider=mock_provider, enabled=False)


class TestIntentClassifier:
    """Tests for the intent classifier."""

    # --- CAPTURE ---

    @pytest.mark.parametrize(
        "text",
        [
            "Today I learned about drilling operations.",
            "I spent two hours studying reservoir engineering.",
            "We had a meeting about inventory planning today.",
            "I struggled with understanding the production workflow.",
            "I observed how the engineers handled the equipment.",
            "Remember that I studied reservoir engineering.",
            "Remember that I spent today studying reservoir engineering.",
            "I've learned a lot about drilling.",
            "Today I studied drilling operations and reservoir engineering.",
        ],
    )
    def test_capture_classification(
        self, rule_classifier: IntentClassifier, text: str
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent == IntentType.CAPTURE
        assert result.should_capture()

    # --- RETRIEVE ---

    @pytest.mark.parametrize(
        "text",
        [
            "What did I learn today?",
            "What did I do yesterday?",
            "Show me everything I've captured about drilling.",
            "What did I work on last week?",
            "What have I recorded about reservoir engineering?",
            "What did I learn this week?",
            "Show my memories.",
            "Do you remember that I studied reservoir engineering?",
        ],
    )
    def test_retrieve_classification(
        self, rule_classifier: IntentClassifier, text: str
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent == IntentType.RETRIEVE
        assert not result.should_capture()

    # --- REFLECT ---

    @pytest.mark.parametrize(
        "text",
        [
            "How have I progressed so far?",
            "How have i made progress so far",
            "What skills am I developing?",
            "What should I improve?",
            "What problems have I encountered?",
            "What am I getting better at?",
            "What have I been spending most of my time learning?",
            "What are the biggest things I've learned during SWEP?",
            "What have I learned?",
            "How much have I learned?",
        ],
    )
    def test_reflect_classification(
        self, rule_classifier: IntentClassifier, text: str
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent == IntentType.REFLECT
        assert not result.should_capture()

    # --- ACTION ---

    @pytest.mark.parametrize(
        "text",
        [
            "Delete that memory.",
            "Delete today's memories.",
            "Show my profile.",
            "Open my dashboard.",
            "Help me.",
            "Start my SWEP logbook.",
        ],
    )
    def test_action_classification(
        self, rule_classifier: IntentClassifier, text: str
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent in (IntentType.ACTION, IntentType.UNKNOWN)
        assert not result.should_capture()

    # --- CONVERSATION ---

    @pytest.mark.parametrize(
        "text",
        [
            "Hello Memo",
            "Hello",
            "Hi there",
            "Thanks!",
            "Thank you",
            "That's interesting",
            "What can you do?",
            "How does this work?",
        ],
    )
    def test_conversation_classification(
        self, rule_classifier: IntentClassifier, text: str
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent == IntentType.CONVERSATION
        assert not result.should_capture()

    # --- CRITICAL REGRESSION TEST ---

    def test_regression_progress_not_captured(
        self, rule_classifier: IntentClassifier
    ) -> None:
        """The exact bug: progress question must NOT become a memory."""
        text = "how have i made progress so far"
        result = asyncio.run(rule_classifier.classify(text))

        assert result.intent == IntentType.REFLECT
        assert (
            not result.should_capture()
        ), "ERROR: A question was classified as CAPTURE!"

    # --- Edge cases ---

    def test_empty_text(self, rule_classifier: IntentClassifier) -> None:
        result = asyncio.run(rule_classifier.classify(""))
        assert result.intent == IntentType.UNKNOWN

    def test_whitespace_text(self, rule_classifier: IntentClassifier) -> None:
        result = asyncio.run(rule_classifier.classify("   "))
        assert result.intent == IntentType.UNKNOWN

    def test_should_capture_only_for_capture(
        self, rule_classifier: IntentClassifier
    ) -> None:
        assert asyncio.run(
            rule_classifier.classify("I learned something today")
        ).should_capture()
        assert not asyncio.run(
            rule_classifier.classify("What did I learn?")
        ).should_capture()
        assert not asyncio.run(rule_classifier.classify("Hello")).should_capture()

    # --- AI fallback when provider returns None ---

    def test_ai_fallback_when_provider_returns_none(
        self, ai_classifier: IntentClassifier
    ) -> None:
        result = asyncio.run(ai_classifier.classify("How have I progressed?"))
        assert result.intent == IntentType.REFLECT
        assert not result.should_capture()

    # --- Ambiguous cases from spec ---

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Today I learned about drilling.", IntentType.CAPTURE),
            ("What did I learn today?", IntentType.RETRIEVE),
            ("I've learned a lot about drilling.", IntentType.CAPTURE),
            ("How much have I learned about drilling?", IntentType.REFLECT),
            ("I struggled with drilling calculations.", IntentType.CAPTURE),
            ("Remember that I studied reservoir engineering.", IntentType.CAPTURE),
            (
                "Do you remember that I studied reservoir engineering?",
                IntentType.RETRIEVE,
            ),
            ("Delete the reservoir engineering memory.", IntentType.ACTION),
        ],
    )
    def test_ambiguous_cases(
        self,
        rule_classifier: IntentClassifier,
        text: str,
        expected: IntentType,
    ) -> None:
        result = asyncio.run(rule_classifier.classify(text))
        assert result.intent == expected
