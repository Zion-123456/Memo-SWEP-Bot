import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db():
    if not os.environ.get("MEMO_TEST_DATABASE_URL"):
        pytest.skip("Requires a disposable MEMO_TEST_DATABASE_URL")
    engine = create_async_engine(os.environ["MEMO_TEST_DATABASE_URL"])
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()
