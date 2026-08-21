"""Check current events in database."""
import asyncio
from app.database.session import build_engine, build_session_factory
from app.config.settings import get_settings
from sqlalchemy import text


async def check():
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sf = build_session_factory(engine)
    async with sf() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM events")
        )
        count = result.scalar()
        print(f"Total events: {count}")
        result2 = await session.execute(
            text(
                "SELECT id, raw_text FROM events "
                "ORDER BY created_at DESC LIMIT 5"
            )
        )
        for row in result2:
            raw = row.raw_text
            print(f"  {row.id}: {repr(raw)[:80] if raw else None}")
    await engine.dispose()


asyncio.run(check())
