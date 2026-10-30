"""Read-only target inspection. Never print the connection string or row data."""

import asyncio
import os

from sqlalchemy import text

from app.database.session import build_engine, database_schema, normalize_database_url


async def inspect():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL securely before database inspection.")
    url = normalize_database_url(dsn)
    expected = os.environ.get("SUPABASE_PROJECT_REF")
    if (
        expected
        and expected not in (url.host or "")
        and expected not in (url.username or "")
    ):
        raise RuntimeError(

                "Connection identity does not match the expected Supabas"
                "e project reference."

        )
    engine = build_engine(dsn)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
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

                        "SELECT schema_name FROM information_schema.schemata WHE"
                        "RE schema_name=:schema"

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

                    "No records changed. Project display name must also be c"
                    "hecked in Supabase settings."

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
