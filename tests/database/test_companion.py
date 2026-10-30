"""Run against a dedicated migrated test database, never a production DSN."""

import os
import uuid

import pytest
from sqlalchemy import func, select

from app.models.companion import Project
from app.models.event import Event
from app.models.user import User
from app.services.companion import CompanionService
from app.storage.local import LocalStorageProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("MEMO_TEST_DATABASE_URL"),
    reason="Requires an explicitly provisioned disposable MEMO_TEST_DATABASE_URL",
)


async def owner(db):
    user = User(telegram_id=uuid.uuid4().int % (2**62), first_name="Synthetic")
    db.add(user)
    await db.flush()
    return user.id


@pytest.mark.asyncio
async def test_personal_profile_preserves_nullable_legacy_fields(db):
    user_id = await owner(db)
    user = await db.get(User, user_id)
    assert user.university is None
    assert user.start_date is None


@pytest.mark.asyncio
async def test_default_projects_seed_once_after_rename_and_archive(db):
    user_id = await owner(db)
    service = CompanionService(db)
    projects = await service.projects(user_id)
    assert len(projects) == 7
    projects[0].name, projects[0].name_key = "Renamed", "renamed"
    projects[1].archived = True
    await db.flush()
    assert len(await service.projects(user_id)) == 6
    assert await db.scalar(select(func.count()).select_from(Project)) == 7


@pytest.mark.asyncio
async def test_project_and_draft_cross_owner_access_denied(db):
    first, second = await owner(db), await owner(db)
    service = CompanionService(db)
    project = await service.create_project(first, "Private")
    draft = await service.stage(first, "source", text="Private original")
    with pytest.raises(ValueError, match="Project not found"):
        await service.project(second, project.id)
    with pytest.raises(ValueError, match="Draft not found"):
        await service.draft(second, draft.id)
    assert await service.active(second) is None
    assert await service.search(second, "Private") == []


@pytest.mark.asyncio
async def test_duplicate_source_and_confirmation_save_once(db, tmp_path):
    user_id = await owner(db)
    service = CompanionService(db)
    first = await service.stage(user_id, "telegram:1:2", text="Original wording")
    duplicate = await service.stage(user_id, "telegram:1:2", text="Changed replay")
    assert first.id == duplicate.id
    await service.edit(user_id, first.id, "Reviewed wording")
    event, created = await service.confirm(
        user_id, first.id, LocalStorageProvider(tmp_path)
    )
    repeated, created_again = await service.confirm(
        user_id, first.id, LocalStorageProvider(tmp_path)
    )
    assert created
    assert not created_again
    assert repeated.id == event.id
    assert event.raw_text == "Original wording"
    assert event.payload_metadata["confirmed_text"] == "Reviewed wording"
    assert await db.scalar(select(func.count()).select_from(Event)) == 1
    with pytest.raises(ValueError, match="closed"):
        await service.edit(user_id, first.id, "Must not overwrite")


@pytest.mark.asyncio
async def test_checkin_resume_skip_partial_finish_and_cancel(db, tmp_path):
    user_id = await owner(db)
    service = CompanionService(db)
    draft = await service.stage(user_id, "checkin:1", kind="checkin")
    await service.answer(user_id, draft.id, "I learned to test software.")
    await service.answer(user_id, draft.id)
    await db.flush()
    resumed = await CompanionService(db).active(user_id)
    assert resumed.id == draft.id
    assert resumed.step == 2
    assert sum(bool(item["answer"]) for item in resumed.answers) == 1
    event, _ = await service.confirm(user_id, draft.id, LocalStorageProvider(tmp_path))
    assert "I learned" in event.raw_text
    cancelled = await service.stage(user_id, "checkin:2", kind="checkin")
    cancelled.state = "cancelled"
    await db.flush()
    with pytest.raises(ValueError, match="cancelled"):
        await service.confirm(user_id, cancelled.id, LocalStorageProvider(tmp_path))


@pytest.mark.asyncio
async def test_empty_checkin_cannot_be_confirmed(db, tmp_path):
    user_id = await owner(db)
    service = CompanionService(db)
    draft = await service.stage(user_id, "checkin:empty", kind="checkin")
    with pytest.raises(ValueError, match="Add some text"):
        await service.confirm(user_id, draft.id, LocalStorageProvider(tmp_path))


@pytest.mark.asyncio
async def test_checkin_edit_finishes_review_without_overwriting_original_answers(
    db, tmp_path
):
    user_id = await owner(db)
    service = CompanionService(db)
    draft = await service.stage(user_id, "checkin:edit", kind="checkin")
    await service.answer(user_id, draft.id, "Original answer", source_key="one")
    await service.answer(user_id, draft.id, "Original answer", source_key="one")
    assert draft.step == 1
    await service.edit(user_id, draft.id, "Reviewed answer")
    assert draft.step == 5
    event, _ = await service.confirm(user_id, draft.id, LocalStorageProvider(tmp_path))
    assert "Original answer" in event.raw_text
    assert event.payload_metadata["confirmed_text"] == "Reviewed answer"


@pytest.mark.asyncio
async def test_search_date_project_and_owner_filters(db, tmp_path):
    first, second = await owner(db), await owner(db)
    service = CompanionService(db)
    project = await service.create_project(first, "Test project")
    draft = await service.stage(first, "search:1", text="A drilling lesson")
    draft.project_id = project.id
    await service.edit(first, draft.id, "Reviewed motor lesson")
    event, _ = await service.confirm(first, draft.id, LocalStorageProvider(tmp_path))
    await db.flush()
    assert [
        e.id for e in await service.search(first, "motor", project_id=project.id)
    ] == [event.id]
    assert await service.search(first, "motor", on_date="1900-01-01") == []
    assert await service.search(second, "motor") == []
    assert [
        e.id
        for e in await service.search(
            first, "motor", on_date=event.event_date.isoformat()
        )
    ] == [event.id]


@pytest.mark.asyncio
async def test_cross_owner_or_archived_project_cannot_be_assigned(db, tmp_path):
    first, second = await owner(db), await owner(db)
    service = CompanionService(db)
    project = await service.create_project(first, "Private")
    draft = await service.stage(second, "draft:1", text="Test")
    draft.project_id = project.id
    with pytest.raises(ValueError, match="Project not found"):
        await service.confirm(second, draft.id, LocalStorageProvider(tmp_path))
    project.archived = True
    await db.flush()
    with pytest.raises(ValueError, match="Project not found"):
        await service.project(first, project.id)
    assert (await service.project(first, project.id, active=False)).id == project.id


@pytest.mark.asyncio
async def test_failed_attachment_retains_source_and_cannot_confirm(db, tmp_path):
    user_id = await owner(db)
    service = CompanionService(db)
    draft = await service.stage(
        user_id, "attachment:1", media=[{"telegram_file_id": "synthetic"}]
    )
    with pytest.raises(ValueError, match="not downloaded"):
        await service.confirm(user_id, draft.id, LocalStorageProvider(tmp_path))
    assert draft.media[0]["telegram_file_id"] == "synthetic"
    assert draft.state == "open"
    assert await db.scalar(select(func.count()).select_from(Event)) == 0
