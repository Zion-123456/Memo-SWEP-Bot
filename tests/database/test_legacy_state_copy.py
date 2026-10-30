import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ops.import_redis_state import copy_state
from app.telegram.persistence.postgres import PostgresPersistence


class LegacyRedis:
    def __init__(self):
        self.values = {
            "memo:ptb:conversations:onboarding": json.dumps({"[123, 456]": 3}),
            "memo:ptb:onboarding:456": json.dumps(
                {"first_name": "Legacy", "start_date": "2026-10-01"}
            ),
        }

    async def scan_iter(self, match):
        for key in self.values:
            if key.startswith(match.rstrip("*")):
                yield key

    async def get(self, key):
        return self.values.get(key)

    async def ttl(self, key):
        return 60


@pytest.mark.asyncio
async def test_legacy_copy_is_dry_by_default_and_never_overwrites_or_deletes(db):
    sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    redis = LegacyRedis()
    persistence = PostgresPersistence(sessions)
    await persistence.update_user_data(456, {"first_name": "Newer PG state"})
    dry = await copy_state(redis, sessions)
    assert dry["copied_rows"] == 0
    assert await persistence.get_conversations("onboarding") == {}
    applied = await copy_state(redis, sessions, apply=True)
    assert applied["copied_rows"] == 1
    assert await persistence.get_conversations("onboarding") == {(123, 456): 3}
    assert (await persistence.get_user_data())[456]["first_name"] == "Newer PG state"
    assert len(redis.values) == 2
