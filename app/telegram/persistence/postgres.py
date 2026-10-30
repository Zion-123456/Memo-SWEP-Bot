"""PTB persistence backed by PostgreSQL; legacy profile dates survive restart."""

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from telegram.ext import BasePersistence, PersistenceInput

from app.models.telegram_runtime import TelegramState

FIELDS = frozenset(
    {"first_name", "university", "department", "programme", "company", "start_date"}
)


class PostgresPersistence(BasePersistence):
    def __init__(self, sessions):
        super().__init__(
            store_data=PersistenceInput(
                bot_data=False, chat_data=False, user_data=True, callback_data=False
            )
        )
        self.sessions = sessions
        self.write_failures = 0

    async def _rows(self, namespace):
        async with self.sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(TelegramState).where(
                            TelegramState.namespace == namespace,
                            TelegramState.expires_at > datetime.now(UTC),
                        )
                    )
                ).all()
            )

    async def _write(self, namespace, key, data):
        try:
            await self._store(namespace, key, data)
        except Exception:
            self.write_failures += 1
            raise

    async def _store(self, namespace, key, data):
        async with self.sessions() as session:
            if data is None:
                await session.execute(
                    delete(TelegramState).where(
                        TelegramState.namespace == namespace, TelegramState.key == key
                    )
                )
            else:
                statement = insert(TelegramState).values(
                    namespace=namespace,
                    key=key,
                    data=data,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["namespace", "key"],
                        set_={
                            "data": statement.excluded.data,
                            "expires_at": statement.excluded.expires_at,
                        },
                    )
                )
            await session.commit()

    async def get_conversations(self, name):
        result = {}
        for row in await self._rows("conversation:" + name):
            try:
                result[tuple(json.loads(row.key))] = row.data
            except (ValueError, TypeError):
                continue
        return result

    async def update_conversation(self, name, key, new_state):
        await self._write("conversation:" + name, json.dumps(list(key)), new_state)

    async def get_user_data(self):
        result = {}
        for row in await self._rows("onboarding"):
            try:
                data = {key: value for key, value in row.data.items() if key in FIELDS}
                if "start_date" in data:
                    data["start_date"] = date.fromisoformat(data["start_date"])
                result[int(row.key)] = data
            except (ValueError, TypeError, AttributeError):
                continue
        return result

    async def update_user_data(self, user_id, data):
        profile = {
            key: (value.isoformat() if isinstance(value, date) else value)
            for key, value in data.items()
            if key in FIELDS
        }
        await self._write("onboarding", str(user_id), profile or None)

    async def drop_user_data(self, user_id):
        await self._write("onboarding", str(user_id), None)

    async def get_bot_data(self):
        return {}

    async def get_chat_data(self):
        return {}

    async def get_callback_data(self):
        return None

    async def update_bot_data(self, data):
        pass

    async def update_chat_data(self, chat_id, data):
        pass

    async def update_callback_data(self, data):
        pass

    async def refresh_bot_data(self, bot_data):
        pass

    async def refresh_chat_data(self, chat_id, chat_data):
        pass

    async def refresh_user_data(self, user_id, user_data):
        pass

    async def drop_chat_data(self, chat_id):
        pass

    async def flush(self):
        pass
