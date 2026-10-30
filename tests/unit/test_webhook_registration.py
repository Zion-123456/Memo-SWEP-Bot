from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.factory import configure_webhook, validate_project_target


@pytest.mark.asyncio
async def test_registration_preserves_pending_updates_and_uses_secret():
    bot = SimpleNamespace(
        get_webhook_info=AsyncMock(return_value=SimpleNamespace(url="")),
        set_webhook=AsyncMock(),
    )
    settings = SimpleNamespace(
        register_webhook=True,
        webhook_url="https://pilot.example/telegram/webhook",
        telegram_webhook_secret=SecretStr("synthetic-webhook-secret"),
    )
    await configure_webhook(bot, settings)
    arguments = bot.set_webhook.call_args.kwargs
    assert arguments["drop_pending_updates"] is False
    assert arguments["secret_token"] == "synthetic-webhook-secret"
    assert arguments["max_connections"] == 1


@pytest.mark.asyncio
async def test_registration_refuses_to_replace_another_deployment():
    bot = SimpleNamespace(
        get_webhook_info=AsyncMock(
            return_value=SimpleNamespace(url="https://other.example/webhook")
        ),
        set_webhook=AsyncMock(),
    )
    settings = SimpleNamespace(
        register_webhook=True, webhook_url="https://pilot.example/telegram/webhook"
    )
    with pytest.raises(RuntimeError, match="different webhook"):
        await configure_webhook(bot, settings)
    bot.set_webhook.assert_not_awaited()


def test_mismatched_supabase_projects_are_rejected_before_network_access():
    settings = SimpleNamespace(
        storage_provider="supabase",
        supabase_project_ref="confirmed",
        supabase_url="https://confirmed.supabase.co",
        database_url="postgresql://user:synthetic@db.different.supabase.co/postgres",
    )
    with pytest.raises(RuntimeError, match="same confirmed Supabase project"):
        validate_project_target(settings)
