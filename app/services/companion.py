"""Transactional, owner-scoped drafts, projects and evidence-backed search."""

import hashlib
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import String, cast, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import FileType
from app.models.companion import CaptureDraft, Project
from app.models.event import Event, PayloadType
from app.repositories.attachment import AttachmentRepository
from app.repositories.event import EventRepository
from app.services.capture import CaptureRequest, CaptureService, MediaPayload

DEFAULT_AREAS = (
    "Academics",
    "Learning and skills",
    "Personal projects",
    "Personal reflections",
    "Volunteering and leadership",
    "Entrepreneurship",
    "Other",
)
CHECKIN_PROMPTS = (
    "What did you do?",
    "What did you learn?",
    "What challenged you?",
    "What did you contribute?",
    "What do you want to remember?",
)


class CompanionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_project(self, owner, name):
        name = name.strip()
        if not 1 <= len(name) <= 100:
            raise ValueError("Project names must contain 1-100 characters.")
        await self.session.execute(
            insert(Project)
            .values(
                id=uuid.uuid4(),
                user_id=owner,
                name=name,
                name_key=name.casefold(),
                archived=False,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "name_key"])
        )
        return (
            await self.session.execute(
                select(Project).where(
                    Project.user_id == owner, Project.name_key == name.casefold()
                )
            )
        ).scalar_one()

    async def projects(self, owner):
        if not await self.session.scalar(
            select(Project.id).where(Project.user_id == owner).limit(1)
        ):
            for name in DEFAULT_AREAS:
                await self.create_project(owner, name)
        return list(
            (
                await self.session.scalars(
                    select(Project)
                    .where(Project.user_id == owner, Project.archived.is_(False))
                    .order_by(Project.name)
                )
            ).all()
        )

    async def project(self, owner, project_id, *, active=True):
        project = await self.session.scalar(
            select(Project)
            .where(Project.id == project_id, Project.user_id == owner)
            .with_for_update()
        )
        if project is None or (active and project.archived):
            raise ValueError("Project not found or unavailable.")
        return project

    async def draft(self, owner, draft_id):
        draft = await self.session.scalar(
            select(CaptureDraft)
            .where(CaptureDraft.id == draft_id, CaptureDraft.user_id == owner)
            .with_for_update()
        )
        if draft is None:
            raise ValueError("Draft not found.")
        return draft

    async def active(self, owner):
        return await self.session.scalar(
            select(CaptureDraft)
            .where(
                CaptureDraft.user_id == owner,
                CaptureDraft.state.in_(["open", "editing", "processing"]),
            )
            .order_by(CaptureDraft.updated_at.desc(), CaptureDraft.id)
            .limit(1)
        )

    async def stage(self, owner, source_key, *, text=None, media=None, kind="capture"):
        await self.session.execute(
            insert(CaptureDraft)
            .values(
                id=uuid.uuid4(),
                user_id=owner,
                source_key=source_key,
                kind=kind,
                state="open",
                original_text=text,
                text=text,
                media=media or [],
                step=0,
                answers=[],
            )
            .on_conflict_do_nothing(index_elements=["user_id", "source_key"])
        )
        return await self.session.scalar(
            select(CaptureDraft).where(
                CaptureDraft.user_id == owner, CaptureDraft.source_key == source_key
            )
        )

    async def edit(self, owner, draft_id, text):
        draft = await self.draft(owner, draft_id)
        if draft.state not in ("open", "editing"):
            raise ValueError("This draft is already closed.")
        if not text.strip() or len(text) > 20000:
            raise ValueError("Enter 1-20,000 characters.")
        draft.text, draft.state = text.strip(), "open"
        if draft.kind == "checkin":
            draft.step = len(CHECKIN_PROMPTS)
        return draft

    async def answer(self, owner, draft_id, text=None, *, source_key=None):
        draft = await self.draft(owner, draft_id)
        if source_key and any(
            item.get("source_key") == source_key for item in draft.answers
        ):
            return draft
        if (
            draft.kind != "checkin"
            or draft.state != "open"
            or draft.step >= len(CHECKIN_PROMPTS)
        ):
            raise ValueError("Use /resume to inspect your draft.")
        if text:
            if len(text) > 4000:
                raise ValueError("Please keep each answer under 4,000 characters.")
        draft.answers = [
            *draft.answers,
            {
                "prompt": CHECKIN_PROMPTS[draft.step],
                "answer": text or "",
                "source_key": source_key,
            },
        ]
        draft.step += 1
        draft.original_text = "\n\n".join(
            x["prompt"] + "\n" + x["answer"] for x in draft.answers if x["answer"]
        )
        draft.text = draft.original_text
        return draft

    async def confirm(self, owner, draft_id, storage):
        draft = await self.draft(owner, draft_id)
        if draft.event_id:
            return await self.session.get(Event, draft.event_id), False
        if draft.state not in ("open", "editing"):
            raise ValueError("This draft was cancelled.")
        if not draft.text and not draft.media:
            raise ValueError("Add some text or an attachment before confirming.")
        if draft.project_id:
            await self.project(owner, draft.project_id)
        items = []
        for media in draft.media:
            if not media.get("storage_url"):
                raise ValueError(
                    "The original attachment is not downloaded yet. Use /retry first."
                )
            original = await storage.read(media["storage_url"])
            if media.get("checksum") and hashlib.sha256(original).hexdigest() != media["checksum"]:
                raise ValueError("Original attachment integrity check failed. Use /retry.")
            items.append(
                MediaPayload(
                    file_bytes=original,
                    filename=media["filename"],
                    content_type=media["content_type"],
                    file_type=FileType(media["file_type"]),
                    telegram_file_id=media["telegram_file_id"],
                )
            )
        payload_type = PayloadType.text
        if items:
            payload_type = {
                FileType.voice: PayloadType.voice,
                FileType.audio: PayloadType.voice,
                FileType.photo: PayloadType.photo,
            }.get(items[0].file_type, PayloadType.document)
            if len(items) > 1:
                payload_type = PayloadType.multimodal
        result = await CaptureService(
            EventRepository(self.session), AttachmentRepository(self.session), storage
        ).capture(
            CaptureRequest(
                user_id=owner,
                event_date=draft.created_at.date(),
                payload_type=payload_type,
                raw_text=draft.original_text,
                media_items=items,
                captured_at=draft.created_at,
                payload_metadata={
                    "draft_id": str(draft.id),
                    "confirmed_text": draft.text,
                    "verification": "user_confirmed",
                    "ai_interpretation": "unverified",
                    "source_key": draft.source_key,
                    "processing_error": draft.processing_error,
                },
            )
        )
        result.event.project_id = draft.project_id
        draft.event_id, draft.state = result.event.id, "confirmed"
        draft.verified_at = datetime.now(UTC)
        return result.event, True

    async def search(self, owner, query="", *, project_id=None, on_date=None, limit=20):
        statement = select(Event).where(
            Event.user_id == owner, Event.is_deleted.is_(False)
        )
        if project_id:
            await self.project(owner, project_id, active=False)
            statement = statement.where(Event.project_id == project_id)
        if on_date:
            statement = statement.where(Event.event_date == date.fromisoformat(on_date))
        if query.strip():
            # Treat % and _ as literal characters rather than wildcard queries.
            pattern = (
                "%"
                + query.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                + "%"
            )
            statement = statement.where(
                or_(
                    Event.raw_text.ilike(pattern),
                    cast(Event.payload_metadata, String).ilike(pattern),
                    cast(Event.ai_analysis, String).ilike(pattern),
                )
            )
        return list(
            (
                await self.session.scalars(
                    statement.order_by(
                        Event.event_date.desc(), Event.captured_at.desc()
                    ).limit(limit)
                )
            ).all()
        )
