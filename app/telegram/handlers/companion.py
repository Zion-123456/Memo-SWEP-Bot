"""Personal Telegram navigation, reviewable captures and persistent check-ins."""

import asyncio
import hashlib
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.models.user import User
from app.repositories.event import EventRepository
from app.repositories.user import UserRepository
from app.services.companion import CHECKIN_PROMPTS, CompanionService
from app.telegram.handlers.capture import _download_file_bytes

MAX_FILE_BYTES = 20 * 1024 * 1024


async def private_only(update, context):
    from telegram.ext import ApplicationHandlerStop

    if update.effective_chat and update.effective_chat.type != "private":
        if update.callback_query:
            await update.callback_query.answer("Use Memo in a private chat.")
        elif update.effective_message:
            await update.effective_message.reply_text(
                "For privacy, use Memo in a private chat with the bot."
            )
        raise ApplicationHandlerStop


async def personal_start(update, context):
    if not update.effective_user or not update.effective_message:
        return
    person = update.effective_user
    async with context.bot_data["session_factory"]() as session:
        await session.execute(
            insert(User)
            .values(
                id=uuid.uuid4(),
                telegram_id=person.id,
                first_name=(person.first_name or "Friend")[:255],
            )
            .on_conflict_do_nothing(index_elements=["telegram_id"])
        )
        user = await UserRepository(session).find_by_telegram_id(person.id)
        await CompanionService(session).projects(user.id)
        await session.commit()
    await update.effective_message.reply_text(
        "Welcome to Memo. Send text, a voice note, a photo or a document. "
        "You review each capture before saving it. /checkin starts a guided draft; "
        "/resume restores it. Your older SWEP records are preserved."
    )
    from app.telegram.handlers.dashboard import show_dashboard

    await show_dashboard(update, context, first_name=user.first_name)


async def _owner(update, context):
    if not update.effective_user or not update.effective_message:
        return None
    async with context.bot_data["session_factory"]() as session:
        user = await UserRepository(session).find_by_telegram_id(
            update.effective_user.id
        )
    if user is None:
        await update.effective_message.reply_text(
            "Send /start to set up your personal Memo."
        )
    return user


async def _preview(update, draft):
    text = draft.text or "Original attachment retained; no extracted text is available."
    if draft.state == "processing":
        await update.effective_message.reply_text(
            "Your original is queued for processing. Use /resume to check it later."
        )
        return
    await update.effective_message.reply_text(
        "Draft — not saved as a confirmed memory yet"
    )
    for offset in range(0, len(text), 3000):
        await update.effective_message.reply_text(text[offset : offset + 3000])
    message = "Review the full preview above."
    if draft.processing_error:
        message += (
            "\n\nProcessing did not complete. Your source is retained."
            " Use /retry or edit the text."
        )
    if draft.project_id:
        message += f"\n\nProject: {draft.project_id}"
    message += (
        "\n\nConfirm the text above, /edit it, /cancel, or assign /use_project <id>."
    )
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirm", callback_data=f"memo:confirm:{draft.id}"
                ),
                InlineKeyboardButton("Edit", callback_data=f"memo:edit:{draft.id}"),
                InlineKeyboardButton("Cancel", callback_data=f"memo:cancel:{draft.id}"),
            ]
        ]
    )
    await update.effective_message.reply_text(message, reply_markup=buttons)


async def _show_draft(update, draft):
    if (
        draft.kind == "checkin"
        and draft.step < len(CHECKIN_PROMPTS)
        and draft.state != "editing"
    ):
        await update.effective_message.reply_text(
            f"Check-in {draft.step+1}/{len(CHECKIN_PROMPTS)}\n"
            f"{CHECKIN_PROMPTS[draft.step]}\n\n"
            "/skip this question · /done to review · /cancel · /resume later"
        )
    else:
        await _preview(update, draft)


async def _results(update, records):
    if not records:
        await update.effective_message.reply_text(
            "No matching saved memories. Try another keyword or date."
        )
        return
    lines, buttons = [], []
    for event in records[:10]:
        meta = event.payload_metadata or {}
        text = meta.get("confirmed_text") or event.raw_text or "Attachment"
        label = (
            "User-confirmed"
            if meta.get("verification") == "user_confirmed"
            else "Legacy record; verification not recorded"
        )
        lines.append(f"{event.event_date} · {label}\n{text[:220]}\nRecord: {event.id}")
        buttons.append(
            [
                InlineKeyboardButton(
                    f"Original evidence · {event.event_date}",
                    callback_data=f"memo:evidence:{event.id}",
                )
            ]
        )
    await update.effective_message.reply_text(
        "\n\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )


async def command(update, context):
    user = await _owner(update, context)
    if user is None:
        return
    message = update.effective_message
    action = message.text.split()[0].split("@")[0].lstrip("/")
    argument = message.text.partition(" ")[2].strip()
    try:
        async with context.bot_data["session_factory"]() as session:
            service = CompanionService(session)
            draft = await service.active(user.id)
            if action in ("checkin", "resume", "draft"):
                if draft is None and action == "checkin":
                    draft = await service.stage(
                        user.id, f"checkin:{update.update_id}", kind="checkin"
                    )
                await session.commit()
                if draft:
                    await _show_draft(update, draft)
                else:
                    await message.reply_text(
                        "No open draft. Send a memory or use /checkin."
                    )
                return
            if action in (
                "skip",
                "done",
                "edit",
                "cancel",
                "confirm",
                "use_project",
                "retry",
            ):
                if draft is None:
                    await message.reply_text(
                        "No open draft. Use /resume or send a new capture."
                    )
                    return
                if draft.state == "processing" and action not in ("cancel", "retry"):
                    await message.reply_text(
                        "Processing is in progress. /resume checks it; /cancel s"
                        "tops this draft."
                    )
                    return
                if action == "retry":
                    if draft.state == "processing":
                        await message.reply_text(
                            "Processing is already queued. Use /resume later."
                        )
                        return
                    draft.state = "processing"
                    await session.commit()
                    context.application.create_task(
                        _bounded_media(update, context, user.id, draft.id)
                    )
                    await message.reply_text(
                        "Retry queued; the original source is retained."
                    )
                    return
                if action == "skip":
                    draft = await service.answer(
                        user.id, draft.id, source_key=str(update.update_id)
                    )
                elif action == "done":
                    draft = await service.draft(user.id, draft.id)
                    draft.step = len(CHECKIN_PROMPTS)
                elif action == "edit":
                    if argument:
                        draft = await service.edit(user.id, draft.id, argument)
                    else:
                        draft = await service.draft(user.id, draft.id)
                        draft.state = "editing"
                        await session.commit()
                        await message.reply_text(
                            "Send the replacement text. "
                            "The original evidence will b"
                            "e preserved."
                        )
                        return
                elif action == "cancel":
                    draft = await service.draft(user.id, draft.id)
                    draft.state = "cancelled"
                    await session.commit()
                    await message.reply_text(
                        "Draft cancelled. No confirmed memory was created."
                    )
                    return
                elif action == "use_project":
                    project = await service.project(user.id, uuid.UUID(argument))
                    draft = await service.draft(user.id, draft.id)
                    draft.project_id = project.id
                elif action == "confirm":
                    event, created = await service.confirm(
                        user.id, draft.id, context.bot_data["storage_provider"]
                    )
                    await session.commit()
                    _schedule(context, event.id, created)
                    await message.reply_text(
                        f"{'Saved' if created else 'Already saved'} once. "
                        f"Record: {event.id}"
                    )
                    return
                await session.commit()
                await _show_draft(update, draft)
                return
            if action in ("projects", "project", "rename_project", "archive_project"):
                await service.projects(user.id)
                if action == "project":
                    if not argument:
                        raise ValueError("Usage: /project <name>")
                    await service.create_project(user.id, argument)
                elif action in ("rename_project", "archive_project"):
                    identifier, _, name = argument.partition(" ")
                    project = await service.project(user.id, uuid.UUID(identifier))
                    if action == "archive_project":
                        project.archived = True
                    else:
                        if not name.strip() or len(name.strip()) > 100:
                            raise ValueError(
                                "Usage: /rename_project <id> "
                                "<new name up to 100 charact"
                                "ers>"
                            )
                        existing = await session.scalar(
                            select(type(project)).where(
                                type(project).user_id == user.id,
                                type(project).name_key == name.strip().casefold(),
                            )
                        )
                        if existing and existing.id != project.id:
                            raise ValueError("A project already has that name.")
                        project.name, project.name_key = (
                            name.strip(),
                            name.strip().casefold(),
                        )
                projects = await service.projects(user.id)
                await session.commit()
                await message.reply_text(
                    "Your projects and life areas. /project <name> creates one.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    p.name, callback_data=f"memo:project:{p.id}"
                                )
                            ]
                            for p in projects[:40]
                        ]
                    ),
                )
                return
            if action in ("search", "memories"):
                words, project_id, on_date = [], None, None
                for part in argument.split():
                    if part.startswith("date:"):
                        on_date = part[5:]
                        date.fromisoformat(on_date)
                    elif part.startswith("project:"):
                        project_id = uuid.UUID(part[8:])
                    else:
                        words.append(part)
                records = await service.search(
                    user.id, " ".join(words), project_id=project_id, on_date=on_date
                )
                await _results(update, records)
                return
    except ValueError as exc:
        await message.reply_text(
            str(exc) if str(exc) else "Check the command arguments."
        )


def _schedule(context, event_id, created):
    ai = context.bot_data.get("ai_service")
    if created and ai:
        ai.schedule(event_id)


async def callback(update, context):
    query = update.callback_query
    await query.answer()
    user = await _owner(update, context)
    if user is None:
        return
    parts = query.data.split(":")
    action = parts[1]
    if action in ("checkin", "projects", "search"):
        if action == "search":
            await update.effective_message.reply_text(
                "Use /search <words> [date:YYYY-MM-DD] [project:ID]. /me"
                "mories browses your saved records."
            )
        else:
            # Callback updates do not carry command text; preserve the same
            # owner-scoped service behavior without fabricating an Update.
            async with context.bot_data["session_factory"]() as session:
                service = CompanionService(session)
                if action == "checkin":
                    draft = await service.active(user.id) or await service.stage(
                        user.id, f"checkin:{update.update_id}", kind="checkin"
                    )
                    await session.commit()
                    await _show_draft(update, draft)
                else:
                    projects = await service.projects(user.id)
                    await session.commit()
                    await update.effective_message.reply_text(
                        "Your life areas. /project <name> adds one.",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        p.name, callback_data=f"memo:project:{p.id}"
                                    )
                                ]
                                for p in projects[:40]
                            ]
                        ),
                    )
        return
    try:
        identifier = uuid.UUID(parts[2])
        async with context.bot_data["session_factory"]() as session:
            service = CompanionService(session)
            if action == "project":
                project = await service.project(user.id, identifier, active=False)
                records = await service.search(user.id, project_id=identifier)
                await update.effective_message.reply_text(
                    f"{project.name}\nID: {project.id}\n"
                    f"/use_project {project.id} assigns your draft.\n"
                    f"/rename_project {project.id} <name> · "
                    f"/archive_project {project.id}",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "Assign to my open draft",
                                    callback_data=f"memo:assign:{project.id}",
                                )
                            ]
                        ]
                    ),
                )
                await _results(update, records)
                return
            if action == "assign":
                project = await service.project(user.id, identifier)
                draft = await service.active(user.id)
                if draft is None or draft.state == "processing":
                    raise ValueError("No ready draft")
                draft = await service.draft(user.id, draft.id)
                draft.project_id = project.id
                await session.commit()
                await _preview(update, draft)
                return
            if action == "evidence":
                event = await EventRepository(session).get_by_id_with_attachments(
                    identifier
                )
                if event is None or event.user_id != user.id:
                    raise ValueError("Record not found.")
                await update.effective_message.reply_text(
                    f"Original source · {event.captured_at.isoformat()}\n"
                    f"{(event.raw_text or 'Original attachment')[:3000]}\n"
                    "AI interpretations are suggestions, not verified facts."
                )
                for attachment in event.attachments:
                    # Return only the authorized owner's original Telegram file.
                    kind = attachment.file_type.value
                    method, field = {
                        "voice": ("send_voice", "voice"),
                        "audio": ("send_audio", "audio"),
                        "photo": ("send_photo", "photo"),
                    }.get(kind, ("send_document", "document"))
                    try:
                        await getattr(context.bot, method)(
                            chat_id=update.effective_chat.id,
                            **{field: attachment.telegram_file_id},
                        )
                    except TelegramError:
                        original = await context.bot_data["storage_provider"].read(
                            attachment.storage_url
                        )
                        await getattr(context.bot, method)(
                            chat_id=update.effective_chat.id,
                            **{
                                field: InputFile(
                                    original,
                                    filename=attachment.original_filename or "original",
                                )
                            },
                        )
                return
            draft = await service.draft(user.id, identifier)
            if action == "confirm":
                event, created = await service.confirm(
                    user.id, identifier, context.bot_data["storage_provider"]
                )
                await session.commit()
                _schedule(context, event.id, created)
                await update.effective_message.reply_text(
                    f"{'Saved' if created else 'Already saved'} once. "
                    f"Record: {event.id}"
                )
            elif action in ("cancel", "edit"):
                if draft.state not in ("open", "editing", "processing") or (
                    draft.state == "processing" and action == "edit"
                ):
                    raise ValueError("This draft is already closed or processing.")
                draft.state = "cancelled" if action == "cancel" else "editing"
                await session.commit()
                await update.effective_message.reply_text(
                    "Draft cancelled."
                    if action == "cancel"
                    else "Send the replacement text; original evidence is preserved."
                )
    except (ValueError, IndexError):
        await update.effective_message.reply_text(
            "Draft, project or record unavailable. Use /resume or /projects."
        )


async def capture(update, context):
    user = await _owner(update, context)
    if user is None:
        return
    message = update.effective_message
    async with context.bot_data["session_factory"]() as session:
        service = CompanionService(session)
        active = await service.active(user.id)
        if active and message.text:
            if active.state == "editing":
                draft = await service.edit(user.id, active.id, message.text)
            elif active.kind == "checkin" and active.step < len(CHECKIN_PROMPTS):
                draft = await service.answer(
                    user.id, active.id, message.text, source_key=str(update.update_id)
                )
            else:
                await message.reply_text(
                    "You have an open draft. /confirm, /edit, /cancel or /re"
                    "sume it first."
                )
                return
            await session.commit()
            await _show_draft(update, draft)
            return
        album_key = (
            f"telegram-album:{message.chat_id}:{message.media_group_id}"
            if message.media_group_id
            else None
        )
        if active and active.source_key != album_key:
            await message.reply_text(
                "Finish or /cancel your open draft before sending another attachment."
            )
            return
    if message.text:
        router = context.bot_data.get("intent_router")
        if router:
            result = await router.route(
                message.text,
                user_id=user.id,
                telegram_user_id=update.effective_user.id,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                context=context,
            )
            if not result.should_capture():
                return
    media, text = [], message.text or message.caption
    attachment = (
        message.voice
        or message.audio
        or (message.photo[-1] if message.photo else None)
        or message.document
    )
    if attachment:
        if (attachment.file_size or 0) > MAX_FILE_BYTES:
            await message.reply_text(
                "The file exceeds the 20 MB limit. Please send a smaller file."
            )
            return
        kind = (
            "voice"
            if message.voice
            else "audio" if message.audio else "photo" if message.photo else "document"
        )
        suffix = {
            "voice": ".ogg",
            "audio": ".mp3",
            "photo": ".jpg",
            "document": ".bin",
        }[kind]
        filename = Path(
            getattr(attachment, "file_name", None)
            or f"{kind}_{attachment.file_unique_id}{suffix}"
        ).name[:200]
        media = [
            {
                "telegram_file_id": attachment.file_id,
                "filename": filename,
                "file_type": kind,
                "content_type": getattr(attachment, "mime_type", None)
                or ("image/jpeg" if kind == "photo" else "application/octet-stream"),
            }
        ]
    async with context.bot_data["session_factory"]() as session:
        draft = await CompanionService(session).stage(
            user.id,
            album_key or f"telegram:{message.chat_id}:{message.message_id}",
            text=text,
            media=media,
        )
        if draft.state == "cancelled" or draft.event_id:
            await message.reply_text(
                "This message was already handled. Send a new message to"
                " create another capture."
            )
            return
        if media and message.media_group_id:
            existing_ids = {item["telegram_file_id"] for item in draft.media}
            draft.media = [
                *draft.media,
                *(
                    item
                    for item in media
                    if item["telegram_file_id"] not in existing_ids
                ),
            ]
        if media:
            draft.state = "processing"
        await session.commit()
    if media:
        tasks = context.bot_data.setdefault("capture_processing_tasks", {})
        if draft.id not in tasks or tasks[draft.id].done():
            task = context.application.create_task(
                _bounded_media(update, context, user.id, draft.id)
            )
            tasks[draft.id] = task
            task.add_done_callback(
                lambda completed, identifier=draft.id: (
                    tasks.pop(identifier, None)
                    if tasks.get(identifier) is completed
                    else None
                )
            )
        await message.reply_text(
            "Original attachment queued. I'll send an editable previ"
            "ew; /resume checks your draft."
        )
    else:
        if draft.event_id:
            await message.reply_text(f"Already saved. Record: {draft.event_id}")
        else:
            await _preview(update, draft)


async def _bounded_media(update, context, owner, draft_id):
    semaphore = context.bot_data.setdefault("media_semaphore", asyncio.Semaphore(4))
    async with semaphore:
        if update.effective_message.media_group_id:
            await asyncio.sleep(0.8)
        await _process_media(update, context, owner, draft_id)


async def _process_media(update, context, owner, draft_id):
    storage = context.bot_data["storage_provider"]
    failed = False
    for index in range(10):
        async with context.bot_data["session_factory"]() as session:
            draft = await CompanionService(session).draft(owner, draft_id)
            if draft.state in ("cancelled", "confirmed"):
                return
            if index >= len(draft.media):
                break
            info = dict(draft.media[index])
        try:
            if not info.get("storage_url"):
                data = await _download_file_bytes(context, info["telegram_file_id"])
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError("File too large")
                info["storage_url"] = await storage.store(
                    data, info["filename"], info["content_type"], f"drafts/{owner}"
                )
            else:
                data = await storage.read(info["storage_url"])
            info["checksum"] = hashlib.sha256(data).hexdigest()
            # Commit original bytes before calling an interpretation provider.
            async with context.bot_data["session_factory"]() as session:
                draft = await CompanionService(session).draft(owner, draft_id)
                items = list(draft.media)
                items[index] = info
                draft.media = items
                await session.commit()
                if draft.state == "cancelled":
                    return
            derived = info.get("original_transcript")
            if not derived and info["file_type"] in ("voice", "audio"):
                provider = context.bot_data.get("ai_provider")
                if provider is None:
                    raise ValueError("Transcription unavailable")
                derived = await provider.transcribe_audio(
                    data, filename=info["filename"], mime_type=info["content_type"]
                )
                if not derived.strip():
                    raise ValueError("Empty transcript")
            elif (
                not derived
                and info["file_type"] == "document"
                and (
                    info["content_type"] == "application/pdf"
                    or info["filename"].lower().endswith(".pdf")
                )
            ):
                from app.documents.pdf import PdfTextExtractor

                extracted = await PdfTextExtractor(max_characters=20000).extract(
                    data, filename=info["filename"], mime_type=info["content_type"]
                )
                if not extracted.has_text:
                    raise ValueError("No extractable PDF text")
                derived = extracted.text
            if derived:
                info["original_transcript"] = derived[:20000]
                async with context.bot_data["session_factory"]() as session:
                    draft = await CompanionService(session).draft(owner, draft_id)
                    if draft.state == "cancelled":
                        return
                    items = list(draft.media)
                    items[index] = info
                    draft.media = items
                    draft.text = "\n\n".join(
                        filter(
                            None,
                            [
                                draft.original_text,
                                *[item.get("original_transcript") for item in items],
                            ],
                        )
                    )[:20000]
                    await session.commit()
        except Exception:
            failed = True
    async with context.bot_data["session_factory"]() as session:
        draft = await CompanionService(session).draft(owner, draft_id)
        if draft.state in ("cancelled", "confirmed"):
            return
        draft.processing_error = "attachment_processing_failed" if failed else None
        draft.state = "open"
        await session.commit()
    await _preview(update, draft)


def register_personal_handlers(app):
    names = [
        "checkin",
        "resume",
        "draft",
        "skip",
        "done",
        "edit",
        "cancel",
        "confirm",
        "retry",
        "projects",
        "project",
        "rename_project",
        "archive_project",
        "use_project",
        "search",
        "memories",
    ]
    app.add_handler(CommandHandler(names, command))
    app.add_handler(CallbackQueryHandler(callback, pattern=r"^memo:"))
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND)
            | filters.VOICE
            | filters.AUDIO
            | filters.PHOTO
            | filters.Document.ALL,
            capture,
        )
    )
