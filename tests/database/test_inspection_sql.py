"""Run the reviewed SQL including optional inventory branches on local PostgreSQL."""

import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url


@pytest.mark.asyncio
async def test_readonly_inventory_with_migration_bucket_and_inbox_metadata():
    dsn = os.environ.get("MEMO_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires an isolated local test database")
    url = make_url(dsn)
    assert url.host in {"127.0.0.1", "localhost"}
    assert url.database.startswith("memo_test_")
    connection = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    schema = "inspection_test_" + uuid.uuid4().hex
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(f"""
            CREATE TABLE "{schema}".alembic_version (version_num text);
            INSERT INTO "{schema}".alembic_version VALUES ('0004');
            CREATE TABLE "{schema}".buckets
                (name text, public boolean, file_size_limit bigint);
            INSERT INTO "{schema}".buckets
                VALUES ('synthetic-private', false, 20971520);
            CREATE TABLE "{schema}".memo_telegram_inbox (state text, attempts integer);
            INSERT INTO "{schema}".memo_telegram_inbox VALUES ('failed', 5);
        """)
        source = Path("docs/supabase-inspection.sql").read_text()
        source = source.replace("storage.buckets", f'"{schema}".buckets')
        source = source.replace("n.nspname = 'storage'", f"n.nspname = '{schema}'")
        assert await connection.execute(source) == "ROLLBACK"
        assert (
            await connection.fetchval(
                f'SELECT version_num FROM "{schema}".alembic_version'
            )
            == "0004"
        )
        assert (
            await connection.fetchval(f'SELECT public FROM "{schema}".buckets') is False
        )
        assert (
            await connection.fetchval(
                f'SELECT attempts FROM "{schema}".memo_telegram_inbox'
            )
            == 5
        )
    finally:
        await connection.execute("ROLLBACK")
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
