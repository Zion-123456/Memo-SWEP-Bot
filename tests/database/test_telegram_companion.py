"""Telegram flows using real SQL sessions and mocked external delivery."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.companion import CaptureDraft
from app.models.event import Event
from app.models.user import User
from app.services.companion import CompanionService
from app.storage.local import LocalStorageProvider
from app.telegram.handlers.companion import (
    _process_media,
    callback,
    capture,
    command,
    personal_start,
)


def interaction(db, tmp_path):
    telegram_id = uuid.uuid4().int % 2**50
    message = SimpleNamespace(
        text="/start",
        caption=None,
        voice=None,
        audio=None,
        photo=[],
        document=None,
        media_group_id=None,
        chat_id=telegram_id,
        message_id=1,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_id, first_name="Synthetic"),
        effective_chat=SimpleNamespace(id=telegram_id, type="private"),
        effective_message=message,
        message=message,
        callback_query=None,
        update_id=1,
    )
    context = SimpleNamespace(
        bot_data={
            "session_factory": async_sessionmaker(bind=db.bind, expire_on_commit=False),
            "storage_provider": LocalStorageProvider(tmp_path),
        },
        bot=SimpleNamespace(send_document=AsyncMock()),
    )
    return update, context


@pytest.mark.asyncio
async def test_short_start_checkin_resume_confirm_and_search(db, tmp_path):
    update, context = interaction(db, tmp_path)
    await personal_start(update, context)
    assert update.effective_message.reply_text.await_count == 2
    user = await db.scalar(
        select(User).where(User.telegram_id == update.effective_user.id)
    )
    assert user.university is None
    update.effective_message.text = "/checkin"
    await command(update, context)
    update.effective_message.text = "I repaired a synthetic motor."
    await capture(update, context)
    update.effective_message.text = "/resume"
    await command(update, context)
    assert "2/5" in update.effective_message.reply_text.call_args.args[0]
    update.effective_message.text = "/done"
    await command(update, context)
    update.effective_message.text = "/confirm"
    await command(update, context)
    update.effective_message.text = "/search motor"
    await command(update, context)
    assert "synthetic motor" in update.effective_message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_text_review_edit_callback_confirm_is_idempotent(db, tmp_path):
    update, context = interaction(db, tmp_path)
    await personal_start(update, context)
    update.effective_message.text = "Original wording"
    await capture(update, context)
    async with context.bot_data["session_factory"]() as session:
        draft = await session.scalar(
            select(CaptureDraft).where(
                CaptureDraft.source_key == f"telegram:{update.effective_chat.id}:1"
            )
        )
        identifier = draft.id
    update.effective_message.text = "/edit Reviewed wording"
    await command(update, context)
    update.callback_query = SimpleNamespace(
        data=f"memo:confirm:{identifier}", answer=AsyncMock()
    )
    await callback(update, context)
    await callback(update, context)
    assert "Already saved" in update.effective_message.reply_text.call_args.args[0]
    async with context.bot_data["session_factory"]() as session:
        event = await session.scalar(
            select(Event).where(Event.user_id == draft.user_id)
        )
        assert event.raw_text == "Original wording"
        assert event.payload_metadata["confirmed_text"] == "Reviewed wording"


@pytest.mark.asyncio
async def test_transcription_failure_keeps_original_and_retry_recovers(db, tmp_path):
    update, context = interaction(db, tmp_path)
    await personal_start(update, context)
    user = await db.scalar(
        select(User).where(User.telegram_id == update.effective_user.id)
    )
    info = {
        "telegram_file_id": "synthetic",
        "filename": "voice.ogg",
        "file_type": "voice",
        "content_type": "audio/ogg",
    }
    service = CompanionService(db)
    draft = await service.stage(user.id, "voice:1", media=[info])
    await db.flush()
    context.bot_data["ai_provider"] = SimpleNamespace(
        transcribe_audio=AsyncMock(side_effect=TimeoutError)
    )
    with patch(
        "app.telegram.handlers.companion._download_file_bytes",
        new_callable=AsyncMock,
        return_value=b"synthetic audio",
    ):
        await _process_media(update, context, user.id, draft.id)
    async with context.bot_data["session_factory"]() as session:
        saved = await CompanionService(session).draft(user.id, draft.id)
        assert saved.processing_error
        path = saved.media[0]["storage_url"]
    assert await context.bot_data["storage_provider"].read(path) == b"synthetic audio"
    context.bot_data["ai_provider"].transcribe_audio = AsyncMock(
        return_value="Reviewed synthetic transcript"
    )
    await _process_media(update, context, user.id, draft.id)
    async with context.bot_data["session_factory"]() as session:
        saved = await CompanionService(session).draft(user.id, draft.id)
        assert saved.processing_error is None
        assert saved.text == "Reviewed synthetic transcript"
        assert saved.media[0]["storage_url"] == path


@pytest.mark.asyncio
async def test_evidence_callback_rejects_another_users_record(db, tmp_path):
    update, context = interaction(db, tmp_path)
    await personal_start(update, context)
    other = User(telegram_id=uuid.uuid4().int % 2**50, first_name="Other")
    db.add(other)
    await db.flush()
    service = CompanionService(db)
    draft = await service.stage(other.id, "other:1", text="Private content")
    event, _ = await service.confirm(
        other.id, draft.id, context.bot_data["storage_provider"]
    )
    await db.flush()
    update.callback_query = SimpleNamespace(
        data=f"memo:evidence:{event.id}", answer=AsyncMock()
    )
    await callback(update, context)
    assert "unavailable" in update.effective_message.reply_text.call_args.args[0]
    context.bot.send_document.assert_not_awaited()
