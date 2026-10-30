"""Bounded synthetic SQL workload; refuses non-local or non-test databases."""

import asyncio
import json
import os
import statistics
import tempfile
import time
import uuid

from sqlalchemy import delete, insert

from app.database.session import (
    build_engine,
    build_session_factory,
    normalize_database_url,
)
from app.models.companion import CaptureDraft, Project
from app.models.event import Event
from app.models.user import User
from app.services.companion import CompanionService
from app.storage.local import LocalStorageProvider


async def run(users=1000, concurrency=10):
    dsn = os.environ.get("MEMO_TEST_DATABASE_URL", "")
    url = normalize_database_url(dsn)
    if url.host not in ("127.0.0.1", "localhost") or not (url.database or "").startswith("memo_test_"):
        raise RuntimeError("Load tests require a local disposable memo_test_ database.")
    engine = build_engine(dsn)
    factory = build_session_factory(engine)
    identifiers = [uuid.uuid4() for _ in range(users)]
    project_ids = [uuid.uuid4() for _ in range(users)]
    semaphore = asyncio.Semaphore(concurrency)
    elapsed, failures = [], []
    created = False
    try:
        async with factory() as session:
            await session.execute(insert(User), [
                {"id":identifier,"telegram_id":uuid.uuid4().int % 2**62,"first_name":"Synthetic load test"}
                for identifier in identifiers
            ])
            await session.execute(insert(Project), [
                {"id":project_ids[index],"user_id":identifier,"name":"Synthetic project","name_key":"synthetic project","archived":False}
                for index,identifier in enumerate(identifiers)
            ])
            await session.commit()
            created = True
        with tempfile.TemporaryDirectory(prefix="memo-load-") as directory:
            storage = LocalStorageProvider(directory)

            async def interaction(index):
                async with semaphore:
                    started = time.perf_counter()
                    try:
                        async with factory() as session:
                            service = CompanionService(session)
                            draft = await service.stage(identifiers[index],f"load:{index}",text=f"Synthetic motor lesson {index}")
                            draft.project_id=project_ids[index]
                            await session.commit()
                            event,first=await service.confirm(identifiers[index],draft.id,storage)
                            await session.commit()
                            repeated,again=await service.confirm(identifiers[index],draft.id,storage)
                            assert first and not again and repeated.id==event.id
                            found=await service.search(identifiers[index],"motor",project_id=project_ids[index])
                            assert len(found)==1 and found[0].user_id==identifiers[index]
                            await session.commit()
                    except Exception as exc:
                        failures.append(type(exc).__name__)
                    elapsed.append(1000*(time.perf_counter()-started))

            start=time.perf_counter()
            await asyncio.gather(*(interaction(index) for index in range(users)))
            seconds=time.perf_counter()-start
        ordered=sorted(elapsed)
        result={"registered_users":users,"concurrent_interactions":concurrency,
                "interactions":len(elapsed),"failures":len(failures),
                "duration_seconds":round(seconds,3),"interactions_per_second":round(users/seconds,2),
                "p50_ms":round(statistics.median(elapsed),2),
                "p95_ms":round(ordered[int(len(ordered)*.95)-1],2),
                "workload":"draft commit, confirm commit, duplicate confirmation, project-filtered owner search",
                "excluded":"Telegram delivery/rate limits, AI and voice latency/quotas, remote Supabase and Render, attachment storage load, dependency outage recovery"}
        print(json.dumps(result,indent=2))
        if failures:
            raise RuntimeError("Load interactions failed")
        return result
    finally:
        if created:
            async with factory() as session:
                for model in (CaptureDraft,Event,Project):
                    await session.execute(delete(model).where(model.user_id.in_(identifiers)))
                await session.execute(delete(User).where(User.id.in_(identifiers)))
                await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
