from unittest.mock import MagicMock

import pytest

from app.ops import inspect_database


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reference", "dsn"),
    [
        (
            "different",
            "postgresql://synthetic:synthetic@db.different.supabase.co/postgres",
        ),
        (
            "verhllnqohsdypbyyeib",
            "postgresql://synthetic:synthetic@db.verhllnqohsdypbyyeib.supabase.co.attacker.example/postgres",
        ),
    ],
)
async def test_inspector_refuses_unconfirmed_or_substring_targets_before_connecting(
    monkeypatch, reference, dsn
):
    monkeypatch.setenv("SUPABASE_PROJECT_REF", reference)
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    builder = MagicMock()
    monkeypatch.setattr(inspect_database, "build_engine", builder)
    with pytest.raises(RuntimeError):
        await inspect_database.inspect()
    builder.assert_not_called()
