"""Integration tests for intent routing in the capture handler.

Verifies that questions, commands, and conversational messages are NOT
saved as events — the critical regression bug where
"how have i made progress so far" was incorrectly saved as a memory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.intent.router import IntentRouter
from app.models.user import User
from app.services.capture import CaptureResult
from app.telegram.handlers.capture import handle_text
from tests.integration.conftest import make_async_session_mock


def _make_mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        telegram_id=123456789,
        first_name="Alice",
        last_name=None,
        username="alice_test",
        university="Tech University",
        department="Engineering",
        programme="Software Engineering",
        company="Memo",
        supervisor=None,
        start_date=date(2025, 6, 1),
        end_date=date(2025, 9, 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _get_sent_text(mock_send: AsyncMock) -> str:
    """Extract the text argument from a send_message mock call."""
    return mock_send.call_args.kwargs.get("text") or mock_send.call_args[0][1]


def _make_mock_context(
    user: User,
    mock_session: MagicMock,
    intent_router=None,
    mock_send_message: AsyncMock | None = None,
) -> MagicMock:
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    mock_session_factory = MagicMock(return_value=mock_session)

    context.bot_data = {
        "session_factory": mock_session_factory,
        "storage_provider": AsyncMock(),
    }
    if intent_router is not None:
        context.bot_data["intent_router"] = intent_router
    if mock_send_message is not None:
        context.bot.send_message = mock_send_message
    else:
        context.bot.send_message = AsyncMock()

    return context


def _make_mock_update(text: str) -> MagicMock:
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    message = MagicMock()
    message.text = text
    message.caption = None
    message.message_id = 42
    message.chat_id = 100
    message.date = datetime.now(UTC)
    message.media_group_id = None
    message.reply_text = AsyncMock()
    update.effective_message = message
    return update


def _make_intent_router(mock_session: MagicMock) -> IntentRouter:
    """Build a real IntentRouter with a rule-based classifier and mocked repos."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.config.settings import get_settings
    from app.intent.classifier import IntentClassifier

    get_settings()
    classifier = IntentClassifier(ai_provider=None, enabled=False)
    sf = MagicMock(spec=async_sessionmaker)
    sf.return_value = mock_session
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return IntentRouter(classifier, sf)


def _make_mock_event_repo():
    """Create a mock EventRepository with the methods the router uses."""
    mock_repo = MagicMock()
    mock_repo.find_by_user_id = AsyncMock(return_value=[])
    mock_repo.find_by_user_and_date = AsyncMock(return_value=[])
    mock_repo.find_by_user_date_range = AsyncMock(return_value=[])
    mock_repo.search_by_topic = AsyncMock(return_value=[])
    return mock_repo


@pytest.fixture
def mock_capture_service():
    """Mock CaptureService so no real events are created."""

    async def mock_capture(req):
        return CaptureResult(
            event=MagicMock(id=uuid.uuid4(), event_date=date.today()),
            attachments_count=0,
        )

    with patch("app.telegram.handlers.capture.CaptureService") as mock_cs_cls:
        mock_cs_cls.return_value.capture = mock_capture
        yield mock_cs_cls


class TestIntentRouting:
    """Tests that the capture handler correctly routes intents."""

    @pytest.mark.asyncio
    async def test_progress_question_not_saved_as_memory(
        self, mock_capture_service: MagicMock
    ) -> None:
        """CRITICAL: 'how have i made progress so far' must NOT create an Event."""
        user = _make_mock_user()
        mock_session = make_async_session_mock()

        router = _make_intent_router(mock_session)
        mock_repo = _make_mock_event_repo()

        with patch("app.intent.router.EventRepository", return_value=mock_repo):
            context = _make_mock_context(
                user=user,
                mock_session=mock_session,
                intent_router=router,
            )

            with patch(
                "app.telegram.handlers.capture." "UserRepository.find_by_telegram_id",
                new_callable=AsyncMock,
                return_value=user,
            ):
                update = _make_mock_update("how have i made progress so far")
                await handle_text(update, context)

                mock_capture_service.assert_not_called()
                mock_send = context.bot.send_message
                mock_send.assert_called_once()
                sent = _get_sent_text(mock_send)
                assert "progress" in sent.lower() or "📈" in sent

    @pytest.mark.asyncio
    async def test_retrieval_question_not_saved(
        self, mock_capture_service: MagicMock
    ) -> None:
        """'What did I learn today?' must NOT create an Event."""
        user = _make_mock_user()
        mock_session = MagicMock()
        mock_session.execute = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        router = _make_intent_router(mock_session)
        mock_repo = _make_mock_event_repo()

        with patch("app.intent.router.EventRepository", return_value=mock_repo):
            context = _make_mock_context(
                user=user,
                mock_session=mock_session,
                intent_router=router,
            )

            with patch(
                "app.telegram.handlers.capture." "UserRepository.find_by_telegram_id",
                new_callable=AsyncMock,
                return_value=user,
            ):
                update = _make_mock_update("What did I learn today?")
                await handle_text(update, context)

                mock_capture_service.assert_not_called()
                mock_send = context.bot.send_message
                sent = _get_sent_text(mock_send)
                assert "memor" in sent.lower() or "🧠" in sent

    @pytest.mark.asyncio
    async def test_capture_message_does_create_event(
        self, mock_capture_service: MagicMock
    ) -> None:
        """A genuine CAPTURE message must still create an Event."""
        user = _make_mock_user()
        mock_session = make_async_session_mock()
        mock_send = AsyncMock()

        router = _make_intent_router(mock_session)

        context = _make_mock_context(
            user=user,
            mock_session=mock_session,
            intent_router=router,
            mock_send_message=mock_send,
        )

        with patch(
            "app.telegram.handlers.capture." "UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ):
            update = _make_mock_update("Today I learned about drilling operations.")
            await handle_text(update, context)

            mock_capture_service.assert_called_once()
            mock_send.assert_called_once()
            sent = _get_sent_text(mock_send)
            assert "✅ Memory saved." in sent

    @pytest.mark.asyncio
    async def test_conversation_not_saved(
        self, mock_capture_service: MagicMock
    ) -> None:
        """'Hello Memo' must NOT create an Event."""
        user = _make_mock_user()
        mock_session = MagicMock()
        mock_session.execute = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        router = _make_intent_router(mock_session)

        context = _make_mock_context(
            user=user,
            mock_session=mock_session,
            intent_router=router,
        )

        with patch(
            "app.telegram.handlers.capture." "UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ):
            update = _make_mock_update("Hello Memo")
            await handle_text(update, context)

            mock_capture_service.assert_not_called()
            mock_send = context.bot.send_message
            sent = _get_sent_text(mock_send)
            assert "hello" in sent.lower() or "📝" in sent

    @pytest.mark.asyncio
    async def test_no_intent_router_defaults_to_capture(
        self, mock_capture_service: MagicMock
    ) -> None:
        """Without intent_router, text falls through to capture (backward compat)."""
        user = _make_mock_user()
        mock_session = make_async_session_mock()
        mock_send = AsyncMock()

        context = _make_mock_context(
            user=user,
            mock_session=mock_session,
            intent_router=None,
            mock_send_message=mock_send,
        )

        with patch(
            "app.telegram.handlers.capture." "UserRepository.find_by_telegram_id",
            new_callable=AsyncMock,
            return_value=user,
        ):
            update = _make_mock_update("Today I learned about drilling.")
            await handle_text(update, context)

            mock_capture_service.assert_called_once()
            mock_send.assert_called_once()
            sent = _get_sent_text(mock_send)
            assert "✅ Memory saved." in sent
