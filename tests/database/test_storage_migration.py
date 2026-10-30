import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.attachment import Attachment, FileType
from app.models.event import PayloadType
from app.models.user import User
from app.ops.migrate_storage import migrate_references
from app.repositories.attachment import AttachmentRepository
from app.repositories.event import EventRepository
from app.services.capture import CaptureRequest, CaptureService, MediaPayload
from app.storage.local import LocalStorageProvider


class PrivateRemote:
    def __init__(self):
        self.objects = {}

    async def store(self, data, filename, content_type, subfolder=""):
        path = "supabase:private/" + uuid.uuid4().hex
        self.objects[path] = data
        return path

    async def read(self, path):
        return self.objects[path]


@pytest.mark.asyncio
async def test_storage_copy_verifies_bytes_and_keeps_originals(db, tmp_path):
    user = User(telegram_id=uuid.uuid4().int % 2**50, first_name="Synthetic")
    db.add(user)
    await db.flush()
    source = LocalStorageProvider(tmp_path)
    service = CaptureService(EventRepository(db), AttachmentRepository(db), source)
    result = await service.capture(
        CaptureRequest(
            user_id=user.id,
            event_date=date.today(),
            payload_type=PayloadType.document,
            media_items=[
                MediaPayload(
                    file_bytes=b"original evidence",
                    filename="file.txt",
                    content_type="text/plain",
                    file_type=FileType.document,
                    telegram_file_id="synthetic",
                )
            ],
        )
    )
    row = await db.scalar(
        select(Attachment).where(Attachment.event_id == result.event.id)
    )
    original = row.storage_url
    sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    remote = PrivateRemote()
    dry = await migrate_references(sessions, source, owner_id=user.id)
    assert dry["legacy_references"] == 1
    assert dry["updated_references"] == 0
    copied = await migrate_references(
        sessions, source, remote, apply=True, owner_id=user.id
    )
    assert copied["updated_references"] == 1
    async with sessions() as session:
        changed = await session.get(Attachment, row.id)
        assert await remote.read(changed.storage_url) == b"original evidence"
    assert await source.read(original) == b"original evidence"
    repeated = await migrate_references(
        sessions, source, remote, apply=True, owner_id=user.id
    )
    assert repeated["legacy_references"] == 0
