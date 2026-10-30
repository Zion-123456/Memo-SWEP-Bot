"""Read-only target inspection. Never print the connection string or row data."""

import asyncio
import os
from types import SimpleNamespace

from sqlalchemy import text

from app.database.session import build_engine, database_schema
from app.factory import validate_project_target


async def inspect():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL securely before database inspection.")
    expected = os.environ.get("SUPABASE_PROJECT_REF")
    if expected != "verhllnqohsdypbyyeib":
        raise RuntimeError("Set the confirmed SUPABASE_PROJECT_REF before inspection.")
    validate_project_target(
        SimpleNamespace(
            storage_provider="supabase",
            supabase_project_ref=expected,
            supabase_url=os.environ.get(
                "SUPABASE_URL", f"https://{expected}.supabase.co"
            ),
            database_url=dsn,
        )
    )
    engine = build_engine(dsn)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            await connection.execute(text("SET LOCAL lock_timeout = '1s'"))
            db = await connection.scalar(text("SELECT current_database()"))
            rows = await connection.execute(
                text(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
                    "ORDER BY table_schema,table_name"
                )
            )
            schemas = await connection.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name=:schema"
                ),
                {"schema": database_schema()},
            )
            print("Database name:", db)
            print("Requested isolated schema:", database_schema())
            print("Schema exists:", schemas.first() is not None)
            print(
                "Visible table names (metadata only):", [f"{r[0]}.{r[1]}" for r in rows]
            )
            print(
                "No records changed. Verify the project display name "
                "in Supabase settings."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(inspect())
    except Exception as exc:
        # Connection errors can contain passwords or token-bearing URLs.
        print("Database inspection failed:", type(exc).__name__)
        raise SystemExit(1) from None
