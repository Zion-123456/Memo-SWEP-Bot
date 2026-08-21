"""Telegram memory capture handlers (Text, Voice, Photo, Document)."""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, date, datetime
from typing import Any

import structlog
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.models.attachment import FileType
from app.models.event import PayloadType, SourceType
from app.repositories.attachment import AttachmentRepository
from app.repositories.event import EventRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.repositories.user import UserRepository
from app.repositories.user_longitudinal_state import UserLongitudinalStateRepository
from app.services.proactive_insight import ProactiveInsightService
from app.services.capture import (
    CaptureRequest,
    CaptureResult,
    CaptureService,
    MediaPayload,
)
from app.storage.exceptions import StorageDownloadError
from app.storage.local import LocalStorageProvider

logger = structlog.get_logger(__name__)

_ALBUM_BUFFER: dict[str, dict[str, Any]] = {}
_ALBUM_TASKS: dict[str, asyncio.Task[None]] = {}
_ALBUM_FLUSH_DELAY_SECONDS = 0.8
_MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024


def _format_confirmation(
    event_date: date,
    source: str,
    attachments_count: int,
    *,
    extra_line: str | None = None,
) -> str:
    """Build the standardized user confirmation message."""
    formatted_date = event_date.strftime("%d %b %Y")
    lines = [
        "✅ Memory saved.",
        "",
        f"📅 Date: {formatted_date}",
        f"📁 Source: {source}",
    ]
    if attachments_count > 0:
        lines.append(f"📎 Attachments: {attachments_count}")
    if extra_line:
        lines.append("")
        lines.append(extra_line)
    return "\n".join(lines)


async def _capture_feedback_lines(
    session_factory: Any,
    user_id: Any,
    event_id: Any,
) -> str | None:
    """Build optional post-capture feedback (connection hint or proactive insight)."""
    async with session_factory() as session:
        insight_service = ProactiveInsightService(
            UserLongitudinalStateRepository(session),
            MemoryConnectionRepository(session),
            EventRepository(session),
        )
        hint = await insight_service.get_connection_hint(user_id, event_id)
        if hint:
            return hint
        pending = await insight_service.pop_pending_insight(user_id)
        if pending and pending.get("message"):
            return f"🧠 Memo noticed something\n\n{pending['message']}"
    return None


async def _get_user_or_reply_error(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Any | None:
    """Ensure the Telegram user has completed onboarding."""
    if not update.effective_user or not update.effective_message:
        return None

    session_factory = context.bot_data.get("session_factory")
    if not session_factory:
        return None

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_by_telegram_id(update.effective_user.id)
        if not user:
            await update.effective_message.reply_text(
                "⚠️ You need to complete onboarding first before saving memories. Send /start to begin."
            )
            return None
        return user


async def _download_file_bytes(
    context: ContextTypes.DEFAULT_TYPE,
    telegram_file_id: str,
    *,
    attempts: int = 3,
) -> bytes:
    """Download Telegram file bytes with a small retry budget."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            file_obj = await context.bot.get_file(telegram_file_id)
            file_bytes_io = io.BytesIO()
            await file_obj.download_to_memory(out=file_bytes_io)
            return file_bytes_io.getvalue()
        except (
            Exception
        ) as exc:  # pragma: no cover - network failures are integration-only
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(0.25 * attempt)

    raise StorageDownloadError(
        f"Failed to download Telegram file '{telegram_file_id}'.",
        details=str(last_error) if last_error else None,
    )


async def _persist_capture(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: Any,
    payload_type: PayloadType,
    source_label: str,
    raw_text: str | None = None,
    media_items: list[MediaPayload] | None = None,
    payload_metadata: dict[str, Any] | None = None,
    media_group_id: str | None = None,
    chat_id: int,
    reply_message_id: int | None = None,
    captured_at: datetime | None = None,
) -> None:
    """Persist a single memory capture through the unified CaptureService."""
    session_factory = context.bot_data["session_factory"]
    storage_provider = context.bot_data.get("storage_provider", LocalStorageProvider())
    ai_service = context.bot_data.get("ai_service")

    result: CaptureResult | None = None
    async with session_factory() as session:
        event_repo = EventRepository(session)
        attachment_repo = AttachmentRepository(session)
        capture_service = CaptureService(event_repo, attachment_repo, storage_provider)

        req = CaptureRequest(
            user_id=user_id,
            event_date=date.today(),
            payload_type=payload_type,
            source_type=SourceType.telegram,
            raw_text=raw_text,
            media_items=media_items or [],
            payload_metadata=payload_metadata,
            captured_at=captured_at or datetime.now(UTC),
            media_group_id=media_group_id,
        )
        result = await capture_service.capture(req)
        await session.commit()
        logger.info(
            "telegram.event_persisted",
            event_id=str(result.event.id),
            payload_type=result.event.payload_type,
        )

    # Non-blocking: schedule AI processing AFTER the capture transaction commits.
    if ai_service is not None and result is not None:
        ai_service.schedule(result.event.id)

    extra_line = await _capture_feedback_lines(
        session_factory,
        user_id,
        result.event.id,
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=_format_confirmation(
            result.event.event_date,
            source_label,
            result.attachments_count,
            extra_line=extra_line,
        ),
        reply_to_message_id=reply_message_id,
    )


async def _flush_album_capture(
    album_id: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Persist buffered Telegram media-group items as one event."""
    try:
        await asyncio.sleep(_ALBUM_FLUSH_DELAY_SECONDS)
        album_data = _ALBUM_BUFFER.pop(album_id, None)
        if not album_data:
            return

        payload_types = album_data["payload_types"]
        media_items = album_data["media_items"]
        payload_type = (
            PayloadType.multimodal
            if len(media_items) > 1 or len(payload_types) > 1
            else next(iter(payload_types))
        )
        source_label = (
            "Album"
            if payload_type is PayloadType.multimodal
            else payload_type.value.title()
        )

        await _persist_capture(
            context=context,
            user_id=album_data["user_id"],
            payload_type=payload_type,
            source_label=source_label,
            raw_text=album_data["caption"],
            media_items=media_items,
            payload_metadata={"telegram_media_group_id": album_id},
            media_group_id=album_id,
            chat_id=album_data["chat_id"],
            reply_message_id=album_data["reply_message_id"],
            captured_at=album_data["captured_at"],
        )
    except Exception as exc:  # pragma: no cover - depends on Telegram runtime
        logger.error("capture.album_failed", media_group_id=album_id, error=str(exc))
        album_data = _ALBUM_BUFFER.get(album_id)
        if album_data:
            await context.bot.send_message(
                chat_id=album_data["chat_id"],
                text="⚠️ I couldn't save that media album. Please try sending it again.",
                reply_to_message_id=album_data["reply_message_id"],
            )
    finally:
        _ALBUM_TASKS.pop(album_id, None)
        _ALBUM_BUFFER.pop(album_id, None)


def _queue_album_item(
    *,
    media_group_id: str,
    user_id: Any,
    media_item: MediaPayload,
    payload_type: PayloadType,
    caption: str | None,
    chat_id: int,
    reply_message_id: int | None,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Buffer an incoming Telegram media-group item for multimodal capture."""
    album_data = _ALBUM_BUFFER.setdefault(
        media_group_id,
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "reply_message_id": reply_message_id,
            "caption": caption,
            "media_items": [],
            "payload_types": set(),
            "captured_at": datetime.now(UTC),
        },
    )
    album_data["media_items"].append(media_item)
    album_data["payload_types"].add(payload_type)
    if caption and not album_data["caption"]:
        album_data["caption"] = caption

    if media_group_id not in _ALBUM_TASKS:
        _ALBUM_TASKS[media_group_id] = asyncio.create_task(
            _flush_album_capture(media_group_id, context)
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text message — classify intent, then route accordingly.

    Only CAPTURE intents proceed to CaptureService. Questions, commands,
    and conversational messages are routed to the intent router instead.
    Media messages continue to default to CAPTURE.
    """
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message or not update.effective_message.text:
        return

    text_content = update.effective_message.text.strip()
    logger.info(
        "telegram.text_handler_invoked",
        user_id=str(user.id),
        text_preview=text_content[:60],
    )

    # --- Intent classification (Sprint 4) ---
    intent_router = context.bot_data.get("intent_router")
    if intent_router is not None:
        result = await intent_router.route(
            text_content,
            user_id=user.id,
            telegram_user_id=update.effective_user.id,
            chat_id=update.effective_message.chat_id,
            reply_to_message_id=update.effective_message.message_id,
            context=context,
        )
        logger.info(
            "telegram.intent_result",
            intent=result.intent.value,
            confidence=result.confidence,
            should_capture=result.should_capture(),
        )
        if not result.should_capture():
            # Intent was not CAPTURE — do NOT create a memory.
            # The router has already dispatched to the appropriate handler
            # (retrieval, reflection, action, conversation, or clarification).
            return

    # --- CAPTURE path (preserves existing pipeline) ---
    await _persist_capture(
        context=context,
        user_id=user.id,
        payload_type=PayloadType.text,
        source_label="Text",
        raw_text=text_content,
        chat_id=update.effective_message.chat_id,
        reply_message_id=update.effective_message.message_id,
        captured_at=update.effective_message.date.astimezone(UTC),
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice note submission."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message or not update.effective_message.voice:
        return

    voice = update.effective_message.voice
    media_item = MediaPayload(
        file_bytes=await _download_file_bytes(context, voice.file_id),
        filename=f"voice_{voice.file_unique_id}.ogg",
        content_type=voice.mime_type or "audio/ogg",
        file_type=FileType.voice,
        telegram_file_id=voice.file_id,
        duration_seconds=voice.duration,
    )

    await _persist_capture(
        context=context,
        user_id=user.id,
        payload_type=PayloadType.voice,
        source_label="Voice",
        raw_text=update.effective_message.caption,
        media_items=[media_item],
        chat_id=update.effective_message.chat_id,
        reply_message_id=update.effective_message.message_id,
        captured_at=update.effective_message.date.astimezone(UTC),
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo capture, including Telegram media albums."""
    user = await _get_user_or_reply_error(update, context)
    if not user or not update.effective_message or not update.effective_message.photo:
        return

    photo = update.effective_message.photo[-1]
    media_item = MediaPayload(
        file_bytes=await _download_file_bytes(context, photo.file_id),
        filename=f"photo_{photo.file_unique_id}.jpg",
        content_type="image/jpeg",
        file_type=FileType.photo,
        telegram_file_id=photo.file_id,
        width=photo.width,
        height=photo.height,
    )

    media_group_id = update.effective_message.media_group_id
    if media_group_id:
        _queue_album_item(
            media_group_id=media_group_id,
            user_id=user.id,
            media_item=media_item,
            payload_type=PayloadType.photo,
            caption=update.effective_message.caption,
            chat_id=update.effective_message.chat_id,
            reply_message_id=update.effective_message.message_id,
            context=context,
        )
        return

    await _persist_capture(
        context=context,
        user_id=user.id,
        payload_type=PayloadType.photo,
        source_label="Photo",
        raw_text=update.effective_message.caption,
        media_items=[media_item],
        chat_id=update.effective_message.chat_id,
        reply_message_id=update.effective_message.message_id,
        captured_at=update.effective_message.date.astimezone(UTC),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document capture, including Telegram media albums."""
    user = await _get_user_or_reply_error(update, context)
    if (
        not user
        or not update.effective_message
        or not update.effective_message.document
    ):
        return

    doc = update.effective_message.document
    if doc.file_size and doc.file_size > _MAX_DOCUMENT_SIZE_BYTES:
        await update.effective_message.reply_text(
            "⚠️ File size exceeds the 20MB limit."
        )
        return

    media_item = MediaPayload(
        file_bytes=await _download_file_bytes(context, doc.file_id),
        filename=doc.file_name or f"doc_{doc.file_unique_id}",
        content_type=doc.mime_type or "application/octet-stream",
        file_type=FileType.document,
        telegram_file_id=doc.file_id,
    )

    media_group_id = update.effective_message.media_group_id
    if media_group_id:
        _queue_album_item(
            media_group_id=media_group_id,
            user_id=user.id,
            media_item=media_item,
            payload_type=PayloadType.document,
            caption=update.effective_message.caption,
            chat_id=update.effective_message.chat_id,
            reply_message_id=update.effective_message.message_id,
            context=context,
        )
        return

    await _persist_capture(
        context=context,
        user_id=user.id,
        payload_type=PayloadType.document,
        source_label="Document",
        raw_text=update.effective_message.caption,
        media_items=[media_item],
        chat_id=update.effective_message.chat_id,
        reply_message_id=update.effective_message.message_id,
        captured_at=update.effective_message.date.astimezone(UTC),
    )


handle_text_memory = handle_text
handle_voice_memory = handle_voice
handle_photo_memory = handle_photo
handle_document_memory = handle_document


def register_capture_handlers(app: Any) -> None:
    """Register media capture handlers on the Telegram Application."""
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
