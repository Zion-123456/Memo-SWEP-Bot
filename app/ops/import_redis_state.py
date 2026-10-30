"""Optional one-time legacy state copy. Dry run by default; never deletes Redis."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.database.session import build_engine, build_session_factory
from app.models.telegram_runtime import TelegramState
from app.telegram.persistence.postgres import FIELDS


async def copy_state(redis, sessions, *, apply=False):
    rows = []
    async for key in redis.scan_iter(match="memo:ptb:conversations:*"):
        raw = await redis.get(key)
        if raw is None:
            continue
        name = (key.decode() if isinstance(key, bytes) else key).removeprefix(
            "memo:ptb:conversations:"
        )
        ttl = await redis.ttl(key)
        for encoded, value in json.loads(raw).items():
            decoded = json.loads(encoded)
            if not isinstance(decoded, list):
                raise ValueError("Invalid legacy conversation key")
            rows.append(("conversation:" + name, json.dumps(decoded), value, ttl))
    async for key in redis.scan_iter(match="memo:ptb:onboarding:*"):
        raw = await redis.get(key)
        if raw is None:
            continue
        identifier = (key.decode() if isinstance(key, bytes) else key).removeprefix(
            "memo:ptb:onboarding:"
        )
        int(identifier)
        data = {
            name: value for name, value in json.loads(raw).items() if name in FIELDS
        }
        rows.append(("onboarding", identifier, data, await redis.ttl(key)))
    copied = 0
    if apply:
        async with sessions() as session:
            for namespace, key, data, ttl in rows:
                result = await session.execute(
                    insert(TelegramState)
                    .values(
                        namespace=namespace,
                        key=key,
                        data=data,
                        expires_at=datetime.now(UTC)
                        + timedelta(seconds=min(ttl, 86400) if ttl > 0 else 86400),
                    )
                    .on_conflict_do_nothing(index_elements=["namespace", "key"])
                    .returning(TelegramState.key)
                )
                copied += result.scalar_one_or_none() is not None
            await session.commit()
    return {
        "available_rows": len(rows),
        "copied_rows": copied,
        "source_deleted": False,
        "applied": apply,
    }


async def main():
    from redis.asyncio import (
        Redis,  # Dev/legacy tooling only, never imported at web startup.
    )

    dsn = os.environ.get("DATABASE_URL")
    if not dsn or not os.environ.get("REDIS_URL"):
        raise RuntimeError(
            "Set source REDIS_URL and inspected destination DATABASE_URL securely."
        )
    apply = "--apply" in sys.argv
    if (
        apply
        and os.environ.get("APP_ENV") == "production"
        and os.environ.get("MEMO_MIGRATION_APPROVED") != "true"
    ):
        raise RuntimeError("Production copying requires explicit migration approval.")
    engine = build_engine(dsn)
    redis = Redis.from_url(os.environ["REDIS_URL"])
    try:
        print(
            json.dumps(
                await copy_state(redis, build_session_factory(engine), apply=apply)
            )
        )
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("Legacy state copy failed:", type(exc).__name__)
        raise SystemExit(1) from None
