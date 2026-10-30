"""Actual PTB dispatch through authenticated HTTP and SQL; Telegram API mocked."""

import json
import asyncio
import os
import time
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from telegram.request import BaseRequest

from app.api.telegram_webhook import router
from app.models.companion import CaptureDraft, Project
from app.models.event import Event
from app.models.telegram_runtime import TelegramInbox, TelegramState
from app.models.user import User
from app.services.webhook import Inbox, WebhookRuntime
from app.storage.local import LocalStorageProvider
from app.telegram.bot import build_bot_application


class TelegramAPI(BaseRequest):
    def __init__(self):
        self.messages = []

    @property
    def read_timeout(self):
        return 10

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        action = url.rsplit("/", 1)[-1]
        data = request_data.parameters if request_data else {}
        if action == "getMe":
            result = {
                "id": 123456789,
                "is_bot": True,
                "first_name": "Memo",
                "username": "use_memo_bot",
            }
        elif action == "sendMessage":
            self.messages.append(data["text"])
            result = {
                "message_id": len(self.messages),
                "date": int(time.time()),
                "chat": {"id": int(data["chat_id"]), "type": "private"},
                "text": data["text"],
            }
        else:
            raise AssertionError("Unexpected Telegram method " + action)
        return 200, json.dumps({"ok": True, "result": result}).encode()


@pytest.mark.asyncio
async def test_real_ptb_webhook_capture_and_restart_resume(tmp_path):
    dsn = os.environ.get("MEMO_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires a disposable database")
    engine = create_async_engine(dsn)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    actor = uuid.uuid4().int % 2**50
    update_ids = []
    identifier = uuid.uuid4().int % 2**31
    api = TelegramAPI()
    storage = LocalStorageProvider(tmp_path)

    def build():
        return build_bot_application(
            token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
            session_factory=sessions,
            storage_provider=storage,
            request=api,
        )

    application = build()
    initialized = False
    runtime = None
    runtime_task = None
    app = FastAPI()
    app.include_router(router)
    secret = "synthetic-webhook-" + ("x" * 40)
    app.state.settings = type(
        "Settings", (), {"telegram_webhook_secret": SecretStr(secret)}
    )()
    inbox = Inbox(sessions)
    app.state.telegram_inbox = inbox

    async def send(text):
        nonlocal identifier
        identifier += 1
        update_ids.append(identifier)
        message = {
            "message_id": identifier,
            "date": int(time.time()),
            "chat": {"id": actor, "type": "private"},
            "from": {"id": actor, "is_bot": False, "first_name": "Synthetic"},
            "text": text,
        }
        if text.startswith("/"):
            message["entities"] = [
                {"type": "bot_command", "offset": 0, "length": len(text.split()[0])}
            ]
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/telegram/webhook",
                json={"update_id": identifier, "message": message},
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            )
        assert response.status_code == 200
        assert await inbox.process_one(application)
        async with sessions() as session:
            row = await session.get(TelegramInbox, identifier)
            assert row.state == "done", row.last_error_type

    try:
        await application.initialize()
        initialized = True
        await application.start()
        await send("/start")
        await send("/project Pilot")
        async with sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_id == actor))
            project = await session.scalar(
                select(Project).where(
                    Project.user_id == user.id, Project.name == "Pilot"
                )
            )
        await send("Today I fixed a synthetic motor.")
        await send("/use_project " + str(project.id))
        await send("/edit Today I fixed a verified motor.")
        await send("/confirm")
        await send("/search verified project:" + str(project.id))
        assert "verified motor" in api.messages[-1]
        await send("/checkin")
        await send("I learned to test software.")
        await application.stop()
        await application.shutdown()
        initialized = False
        application = build()
        await application.initialize()
        initialized = True
        await application.start()
        await send("/resume")
        assert "2/5" in api.messages[-1]
        await send("/done")
        await send("/confirm")
        async with sessions() as session:
            events = list(
                (
                    await session.scalars(select(Event).where(Event.user_id == user.id))
                ).all()
            )
            assert len(events) == 2
            assert any(event.project_id == project.id for event in events)
            assert any(
                event.raw_text == "Today I fixed a synthetic motor." for event in events
            )
        await application.stop()
        await application.shutdown()
        initialized=False
        identifier+=1
        update_ids.append(identifier)
        await inbox.accept({'update_id':identifier,'message':{'message_id':identifier,
            'date':int(time.time()),'chat':{'id':actor,'type':'private'},
            'from':{'id':actor,'is_bot':False,'first_name':'Synthetic'},'text':'/memories',
            'entities':[{'type':'bot_command','offset':0,'length':9}]}})
        runtime=WebhookRuntime(sessions,f'synthetic-runtime-{actor}',build)
        runtime_task=asyncio.create_task(runtime.run())
        completed=False
        for _ in range(100):
            async with sessions() as session:
                row=await session.get(TelegramInbox,identifier)
                completed=row.state=='done'
            if completed: break
            await asyncio.sleep(.05)
        assert completed
        assert runtime.active
        assert 'Record:' in api.messages[-1]
    finally:
        if runtime:
            await runtime.stop()
            await asyncio.wait_for(runtime_task,timeout=5)
        if application.running:
            await application.stop()
        if initialized:
            await application.shutdown()
        async with sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_id == actor))
            if user:
                for model in (CaptureDraft, Event, Project):
                    await session.execute(delete(model).where(model.user_id == user.id))
                await session.delete(user)
            await session.execute(
                delete(TelegramInbox).where(TelegramInbox.update_id.in_(update_ids))
            )
            await session.execute(
                delete(TelegramState).where(
                    TelegramState.key.in_([str(actor), json.dumps([actor, actor])])
                )
            )
            await session.commit()
        await engine.dispose()
