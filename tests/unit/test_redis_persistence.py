"""Unit tests for the atomic RedisPersistence transaction and concurrency retry logic."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import WatchError

from app.telegram.persistence.redis_persistence import RedisPersistence


@pytest.mark.asyncio
async def test_update_conversation_retries_on_watch_error_and_succeeds() -> None:
    # Arrange
    mock_redis = MagicMock()
    mock_pipeline = AsyncMock()
    mock_pipeline.__aenter__.return_value = mock_pipeline
    mock_redis.pipeline.return_value = mock_pipeline

    # After pipe.multi() is called, commands are queued *synchronously* in a
    # real Redis pipeline. The AsyncMock intercepts them as coroutines, which
    # produces RuntimeWarning. Using MagicMock for these two methods matches
    # the actual Redis pipeline contract.
    mock_pipeline.multi = MagicMock()
    mock_pipeline.set = MagicMock()

    # First 2 execute() calls raise WatchError, the 3rd succeeds.
    mock_pipeline.execute.side_effect = [WatchError(), WatchError(), None]
    mock_pipeline.get.return_value = None

    persistence = RedisPersistence(mock_redis)
    chat_id, user_id = 123, 456

    # Act
    await persistence.update_conversation("onboarding", (chat_id, user_id), "AWAITING_UNIVERSITY")

    # Assert — 3 pipeline iterations (2 conflicts, 1 success)
    assert mock_redis.pipeline.call_count == 3
    assert mock_pipeline.watch.call_count == 3
    assert mock_pipeline.multi.call_count == 3
    assert mock_pipeline.set.call_count == 3
    assert mock_pipeline.execute.call_count == 3

    # Check the key written in the successful call
    set_call = mock_pipeline.set.call_args_list[-1]
    redis_key = set_call[0][0]
    serialized_val = set_call[0][1]

    assert redis_key == "memo:ptb:conversations:onboarding"
    deserialized = json.loads(serialized_val)
    key_str = json.dumps([chat_id, user_id])
    assert deserialized[key_str] == "AWAITING_UNIVERSITY"


@pytest.mark.asyncio
async def test_update_conversation_raises_after_max_retries() -> None:
    # Arrange
    mock_redis = MagicMock()
    mock_pipeline = AsyncMock()
    mock_pipeline.__aenter__.return_value = mock_pipeline
    mock_redis.pipeline.return_value = mock_pipeline

    mock_pipeline.multi = MagicMock()
    mock_pipeline.set = MagicMock()
    # Always raise WatchError to exhaust retry limit of 5
    mock_pipeline.execute.side_effect = WatchError()
    mock_pipeline.get.return_value = None

    persistence = RedisPersistence(mock_redis)
    chat_id, user_id = 123, 456

    # Act & Assert
    with pytest.raises(WatchError):
        await persistence.update_conversation("onboarding", (chat_id, user_id), "AWAITING_UNIVERSITY")

    # Exactly 5 attempts before giving up
    assert mock_redis.pipeline.call_count == 5

