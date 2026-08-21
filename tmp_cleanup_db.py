"""Clean up the old buggy events from the database."""
import asyncio
from app.database.session import build_engine, build_session_factory
from app.config.settings import get_settings
from sqlalchemy import text


async def cleanup():
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sf = build_session_factory(engine)
    async with sf() as session:
        # Delete the buggy events (questions saved as memories)
        result = await session.execute(
            text(
                "SELECT id, raw_text FROM events "
                "WHERE raw_text IN ('how have i  made progress so far', "
                "'how have i  made so far') "
                "OR raw_text IS NULL"
            )
        )
        for row in result:
            print(f"Deleting event {row.id}: {repr(row.raw_text)[:60]}")

        await session.execute(
            text(
                "DELETE FROM events "
                "WHERE raw_text IN ('how have i  made progress so far', "
                "'how have i  made so far') "
                "OR raw_text IS NULL"
            )
        )
        await session.commit()

        result2 = await session.execute(text("SELECT COUNT(*) FROM events"))
        print(f"Remaining events: {result2.scalar()}")

    await engine.dispose()


asyncio.run(cleanup())
