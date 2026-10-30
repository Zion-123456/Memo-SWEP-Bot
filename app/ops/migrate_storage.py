"""Copy legacy originals to private storage before redeployment; dry run first."""

import asyncio
import hashlib
import json
import os
import sys

from sqlalchemy import select

from app.database.session import build_engine, build_session_factory
from app.models.attachment import Attachment
from app.models.companion import CaptureDraft
from app.models.event import Event
from app.storage.local import LocalStorageProvider
from app.storage.supabase import SupabaseStorageProvider


async def migrate_references(
    sessions, source, destination=None, *, apply=False, owner_id=None
):
    cache = {}
    report = {
        "legacy_references": 0,
        "updated_references": 0,
        "originals_deleted": False,
        "applied": apply,
    }

    async def copy(owner, path, filename):
        report["legacy_references"] += 1
        key = (str(owner), path)
        if key not in cache:
            data = await source.read(path)
            if apply:
                new = await destination.store(
                    data, filename, "application/octet-stream", f"migrated/{owner}"
                )
                if (
                    hashlib.sha256(await destination.read(new)).digest()
                    != hashlib.sha256(data).digest()
                ):
                    raise RuntimeError(
                        "Private copy integrity check failed; original retained"
                    )
                cache[key] = new
            else:
                cache[key] = path
        return cache[key]

    async with sessions() as session:
        statement = select(
            Attachment.id,
            Attachment.storage_url,
            Attachment.original_filename,
            Event.user_id,
        ).join(Event, Event.id == Attachment.event_id)
        if owner_id:
            statement = statement.where(Event.user_id == owner_id)
        attachments = list(await session.execute(statement))
        statement = select(CaptureDraft)
        if owner_id:
            statement = statement.where(CaptureDraft.user_id == owner_id)
        drafts = list((await session.scalars(statement)).all())
    for identifier, path, filename, owner in attachments:
        if not path or path.startswith("supabase:"):
            continue
        new = await copy(owner, path, filename or "original")
        if apply:
            async with sessions() as session:
                row = await session.get(Attachment, identifier, with_for_update=True)
                if row.storage_url != path:
                    raise RuntimeError(
                        "Reference changed; stop writers before migration"
                    )
                row.storage_url = new
                await session.commit()
                report["updated_references"] += 1
    for draft in drafts:
        updated = [dict(item) for item in draft.media]
        changed = 0
        for item in updated:
            path = item.get("storage_url")
            if path and not path.startswith("supabase:"):
                item["storage_url"] = await copy(
                    draft.user_id, path, item.get("filename", "original")
                )
                changed += 1
        if apply and changed:
            async with sessions() as session:
                current = await session.get(
                    CaptureDraft, draft.id, with_for_update=True
                )
                if current.media != draft.media:
                    raise RuntimeError("Draft changed; stop writers before migration")
                current.media = updated
                await session.commit()
                report["updated_references"] += changed
    return report


async def main():
    apply = "--apply" in sys.argv
    if not os.environ.get("DATABASE_URL") or not os.environ.get("LEGACY_UPLOAD_DIR"):
        raise RuntimeError(
            "Set the inspected DATABASE_URL and the original LEGACY_UPLOAD_DIR"
        )
    if (
        apply
        and os.environ.get("APP_ENV") == "production"
        and os.environ.get("MEMO_MIGRATION_APPROVED") != "true"
    ):
        raise RuntimeError("Production copying requires explicit migration approval")
    engine = build_engine(os.environ["DATABASE_URL"])
    destination = None
    try:
        if apply:
            from app.config.settings import Settings
            from app.factory import validate_project_target

            configuration = Settings(storage_provider="supabase")
            validate_project_target(configuration)
            destination = SupabaseStorageProvider(
                os.environ["SUPABASE_URL"],
                os.environ.get("SUPABASE_STORAGE_BUCKET", "memo-private"),
                os.environ["SUPABASE_SERVICE_ROLE_KEY"],
            )
            await destination.check_private_bucket()
        report = await migrate_references(
            build_session_factory(engine),
            LocalStorageProvider(os.environ["LEGACY_UPLOAD_DIR"]),
            destination,
            apply=apply,
        )
        print(json.dumps(report))
    finally:
        if destination:
            await destination.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(
            "Storage migration stopped; originals retained. Error type:",
            type(exc).__name__,
        )
        raise SystemExit(1) from None
