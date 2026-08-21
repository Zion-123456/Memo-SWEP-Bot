import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine('postgresql+asyncpg://memo:memo@localhost:5432/memo')
    async with engine.begin() as conn:
        await conn.execute(sa.text('DROP TYPE IF EXISTS topic_status_enum, topic_trend_enum, connection_type_enum, snapshot_trigger_enum CASCADE'))

asyncio.run(main())
