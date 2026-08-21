"""Tests for unhandled exception conversation state recovery."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.telegram.handlers.error import handle_error


@pytest.mark.asyncio
async def test_handle_error_clears_state_atomically() -> None:
    # Arrange
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock()
    update.effective_chat.id = 123
    update.effective_user = MagicMock()
    update.effective_user.id = 456
    update.effective_message = AsyncMock()

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.error = Exception("Simulation of unhandled bot exception")
    context.user_data = {"temp_key": "stale_onboarding_data"}

    # Mock Redis persistence call on context.application
    context.application.persistence = AsyncMock()

    # Mock Database Session and repositories
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session

    session_factory = MagicMock(return_value=mock_session)
    context.bot_data = {"session_factory": session_factory}

    # Simulate finding an existing user record to trigger DB conversation status reset
    from app.models.user import User
    import uuid
    mock_user = User(id=uuid.uuid4(), telegram_id=456)
    
    # We mock import paths inside the function
    # Mocking app.repositories.user.UserRepository.find_by_telegram_id
    with pytest.MonkeyPatch.context() as mp:
        async def mock_find_by_tg_id(*args: any, **kwargs: any) -> User:
            return mock_user
        
        async def mock_upsert(*args: any, **kwargs: any) -> any:
            return MagicMock()

        from app.repositories.user import UserRepository
        from app.repositories.conversation import ConversationRepository
        mp.setattr(UserRepository, "find_by_telegram_id", mock_find_by_tg_id)
        mp.setattr(ConversationRepository, "upsert", mock_upsert)

        # Act
        await handle_error(update, context)

    # Assert
    # 1. Verify Redis state clearing
    context.application.persistence.update_conversation.assert_called_once_with(
        "onboarding", (123, 456), None
    )
    assert len(context.user_data) == 0

    # 2. Verify User reply
    update.effective_message.reply_text.assert_called_once()
    reply_msg = update.effective_message.reply_text.call_args[0][0]
    assert "Something went wrong" in reply_msg
