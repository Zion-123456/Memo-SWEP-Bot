"""Redis-backed persistence for python-telegram-bot ConversationHandler.

Implements :class:`telegram.ext.BasePersistence` to store conversation state
in Redis rather than in memory, ensuring that active onboarding flows survive
process restarts. Conversation state and temporary onboarding profile fields
are persisted with a 24-hour TTL. Bot and chat data remain no-ops.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

import structlog
from redis.asyncio import Redis
from telegram.ext import BasePersistence
from telegram.ext._utils.types import ConversationDict

logger = structlog.get_logger(__name__)



# TTL for conversation state keys in Redis.
# A conversation left in an incomplete state for longer than this will be
# discarded, preventing stale state from accumulating indefinitely.
_CONVERSATION_TTL_SECONDS: int = 86_400  # 24 hours

_KEY_PREFIX: str = "memo:ptb:conversations"
_USER_DATA_PREFIX: str = "memo:ptb:onboarding:"
_ONBOARDING_FIELDS = frozenset(
    {"first_name", "university", "department", "programme", "company", "start_date"}
)


from redis.exceptions import WatchError

# Maximum attempts for Redis transaction retries on conflict.
_MAX_TRANSACTION_RETRIES: int = 5


class RedisPersistence(BasePersistence):  # type: ignore[misc]

    """A :class:`BasePersistence` implementation backed by Redis.

    Conversation state and the small allowlist of onboarding profile fields
    are stored. Other data stores remain no-ops.

    Args:
        redis_client: A connected async Redis client.
    """

    def __init__(self, redis_client: Redis) -> None:  # type: ignore[type-arg]
        super().__init__(
            store_data=self._make_store_data(
                bot_data=False,
                chat_data=False,
                user_data=True,
                callback_data=False,
            )
        )
        self._redis = redis_client

    @staticmethod
    def _make_store_data(**kwargs: bool) -> Any:
        """Construct the PersistenceInput for the superclass."""
        from telegram.ext import PersistenceInput

        return PersistenceInput(**kwargs)

    def _conversation_key(self, name: str) -> str:
        return f"{_KEY_PREFIX}:{name}"

    # ------------------------------------------------------------------
    # Conversation state (the only meaningful implementation)
    # ------------------------------------------------------------------

    async def get_conversations(self, name: str) -> ConversationDict:
        """Load all conversation states for a handler from Redis.

        Args:
            name: The name of the ConversationHandler.

        Returns:
            A dictionary mapping ``(chat_id, user_id)`` tuples to states.
        """
        raw = await self._redis.get(self._conversation_key(name))
        if raw is None:
            return {}
        try:
            # Keys are serialised as JSON arrays since Redis keys are strings.
            return {
                tuple(json.loads(k)): v
                for k, v in json.loads(raw).items()
            }
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to deserialise conversation state from Redis.")
            return {}

    async def update_conversation(
        self,
        name: str,
        key: tuple[int | str, ...],
        new_state: object | None,
    ) -> None:
        """Persist a single conversation state transition atomically.

        Uses Redis WATCH/MULTI/EXEC optimistic locking to prevent concurrent
        updates from overwriting each other. Retries on conflict.

        Args:
            name: The name of the ConversationHandler.
            key: The ``(chat_id, user_id)`` tuple identifying the conversation.
            new_state: The new state value, or ``None`` to remove the entry.
        """
        redis_key = self._conversation_key(name)
        str_key = json.dumps(list(key))

        for attempt in range(1, _MAX_TRANSACTION_RETRIES + 1):
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(redis_key)
                    raw = await pipe.get(redis_key)

                    # Deserialize current states
                    all_conversations: dict[tuple[int | str, ...], Any] = {}
                    if raw is not None:
                        try:
                            all_conversations = {
                                tuple(json.loads(k)): v
                                for k, v in json.loads(raw).items()
                            }
                        except (json.JSONDecodeError, ValueError):
                            logger.warning(
                                "Failed to deserialise conversation state during transaction."
                            )

                    # Modify specific user state
                    if new_state is None:
                        all_conversations.pop(tuple(json.loads(str_key)), None)
                    else:
                        all_conversations[tuple(json.loads(str_key))] = new_state

                    # Serialize back
                    serialisable = {
                        json.dumps(list(k)): v for k, v in all_conversations.items()
                    }
                    serialized = json.dumps(serialisable)

                    # Execute atomic transaction
                    pipe.multi()
                    pipe.set(redis_key, serialized, ex=_CONVERSATION_TTL_SECONDS)
                    await pipe.execute()
                    return  # Success

                except WatchError:
                    if attempt == _MAX_TRANSACTION_RETRIES:
                        logger.error(
                            "Redis transaction failed after max retries due to conflict.",
                            key=redis_key,
                        )
                        raise
                    logger.debug(
                        "Redis transaction conflict detected, retrying...",
                        attempt=attempt,
                        key=redis_key,
                    )


    # ------------------------------------------------------------------
    # No-op implementations for unused data stores
    # ------------------------------------------------------------------

    async def get_bot_data(self) -> dict[Any, Any]:
        return {}

    async def update_bot_data(self, data: dict[Any, Any]) -> None:
        pass

    async def refresh_bot_data(self, bot_data: dict[Any, Any]) -> None:
        pass

    async def get_chat_data(self) -> dict[int, dict[Any, Any]]:
        return {}

    async def update_chat_data(
        self, chat_id: int, data: dict[Any, Any]
    ) -> None:
        pass

    async def refresh_chat_data(
        self, chat_id: int, chat_data: dict[Any, Any]
    ) -> None:
        pass

    async def drop_chat_data(self, chat_id: int) -> None:
        pass

    async def get_user_data(self) -> dict[int, dict[Any, Any]]:
        """Restore in-progress profile fields alongside conversation states."""
        result: dict[int, dict[Any, Any]] = {}
        async for key in self._redis.scan_iter(match=f"{_USER_DATA_PREFIX}*"):
            raw = await self._redis.get(key)
            if raw is None:
                continue
            try:
                key_text = key.decode() if isinstance(key, bytes) else key
                user_id = int(key_text.removeprefix(_USER_DATA_PREFIX))
                data = json.loads(raw)
                data = {k: v for k, v in data.items() if k in _ONBOARDING_FIELDS}
                if "start_date" in data:
                    data["start_date"] = date.fromisoformat(data["start_date"])
                result[user_id] = data
            except (ValueError, TypeError, AttributeError):
                logger.warning("Invalid persisted onboarding profile; ignoring it.")
        return result

    async def update_user_data(
        self, user_id: int, data: dict[Any, Any]
    ) -> None:
        # Store only the profile fields needed to resume onboarding. Arbitrary
        # bot state and credentials must not enter this persistence namespace.
        profile = {k: v for k, v in data.items() if k in _ONBOARDING_FIELDS}
        if not profile:
            await self.drop_user_data(user_id)
            return
        if isinstance(profile.get("start_date"), date):
            profile["start_date"] = profile["start_date"].isoformat()
        await self._redis.set(
            f"{_USER_DATA_PREFIX}{user_id}",
            json.dumps(profile),
            ex=_CONVERSATION_TTL_SECONDS,
        )

    async def refresh_user_data(
        self, user_id: int, user_data: dict[Any, Any]
    ) -> None:
        pass

    async def drop_user_data(self, user_id: int) -> None:
        await self._redis.delete(f"{_USER_DATA_PREFIX}{user_id}")

    async def get_callback_data(self) -> None:
        return None

    async def update_callback_data(self, data: Any) -> None:
        pass

    async def flush(self) -> None:
        pass

    def get_conversations_callback(self, name: str) -> Callable[[], ConversationDict]:  # type: ignore[override]
        """Not used — async get_conversations is preferred."""
        raise NotImplementedError
