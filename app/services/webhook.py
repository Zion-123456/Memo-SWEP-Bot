"""Durable, deduplicated Telegram delivery with bounded retry and dispatch."""

import asyncio
import contextlib
import contextvars
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import String, and_, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from telegram import Update

from app.models.companion import CaptureDraft
from app.models.event import Event, ProcessingStatus
from app.models.telegram_runtime import TelegramInbox, TelegramLease, TelegramState

UPDATE_FAILED = contextvars.ContextVar("memo_update_failed", default=False)
logger = structlog.get_logger(__name__)


class Inbox:
    def __init__(self, sessions):
        self.sessions = sessions

    async def accept(self, payload):
        async with self.sessions() as session:
            result = await session.execute(
                insert(TelegramInbox)
                .values(
                    update_id=payload["update_id"],
                    payload=payload,
                    state="pending",
                    attempts=0,
                )
                .on_conflict_do_nothing(index_elements=["update_id"])
                .returning(TelegramInbox.update_id)
            )
            created = result.scalar_one_or_none() is not None
            await session.commit()
            return created

    async def recover(self):
        async with self.sessions() as session:
            await session.execute(
                update(TelegramInbox)
                .where(TelegramInbox.state == "processing")
                .values(state="pending", available_at=func.now())
            )
            await session.execute(
                delete(TelegramState).where(TelegramState.expires_at < func.now())
            )
            await session.execute(
                update(CaptureDraft)
                .where(CaptureDraft.state == "processing")
                .values(state="open", processing_error="interrupted_processing")
            )
            await session.execute(
                update(Event)
                .where(Event.status == ProcessingStatus.processing)
                .values(status=ProcessingStatus.pending)
            )
            await session.commit()

    async def process_one(self, bot_app):
        older = aliased(TelegramInbox)

        def chat(row):
            return func.coalesce(
                row.payload["message"]["chat"]["id"].astext,
                row.payload["callback_query"]["message"]["chat"]["id"].astext,
                cast(row.update_id, String),
            )

        earlier_for_chat = (
            select(older.update_id)
            .where(
                older.state.in_(["pending", "processing"]),
                chat(older) == chat(TelegramInbox),
                or_(
                    older.received_at < TelegramInbox.received_at,
                    and_(
                        older.received_at == TelegramInbox.received_at,
                        older.update_id < TelegramInbox.update_id,
                    ),
                ),
            )
            .exists()
        )
        async with self.sessions() as session:
            row = await session.scalar(
                select(TelegramInbox)
                .where(
                    TelegramInbox.state == "pending",
                    TelegramInbox.available_at <= func.now(),
                    ~earlier_for_chat,
                )
                .order_by(TelegramInbox.received_at, TelegramInbox.update_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return False
            row.state = "processing"
            row.attempts += 1
            row.locked_at = datetime.now(UTC)
            identifier, payload, attempts = (
                row.update_id,
                dict(row.payload),
                row.attempts,
            )
            await session.commit()
        token = UPDATE_FAILED.set(False)
        error = None
        persistence = getattr(bot_app, "persistence", None)
        previous_failures = getattr(persistence, "write_failures", 0)
        try:
            await bot_app.process_update(Update.de_json(payload, bot_app.bot))
            if UPDATE_FAILED.get():
                raise RuntimeError("Telegram handler reported failure")
            # Flush modified conversation/profile state before acknowledging work.
            await bot_app.update_persistence()
            if (
                UPDATE_FAILED.get()
                or getattr(persistence, "write_failures", 0) != previous_failures
            ):
                raise RuntimeError("Conversation persistence failed")
        except asyncio.CancelledError:
            raise  # New lease holder recovers the processing row after restart.
        except Exception as exc:
            error = type(exc).__name__
        finally:
            UPDATE_FAILED.reset(token)
        async with self.sessions() as session:
            row = await session.get(TelegramInbox, identifier)
            if error:
                row.state = "failed" if attempts >= 5 else "pending"
                row.last_error_type = error
                row.available_at = datetime.now(UTC) + timedelta(
                    seconds=min(60, 2**attempts)
                )
                logger.error(
                    "webhook.dispatch_failed",
                    update_id=identifier,
                    attempt=attempts,
                    error_type=error,
                )
            else:
                row.state = "done"
                row.payload = (
                    {}
                )  # Retain the receipt, not another copy of private messages.
                row.last_error_type = None
            await session.commit()
        return True


class DispatcherLease:
    def __init__(self, sessions, bot_id):
        self.sessions = sessions
        self.key = f"dispatcher:{bot_id}"
        self.owner = uuid.uuid4().hex

    async def acquire(self):
        async with self.sessions() as session:
            statement = insert(TelegramLease).values(
                key=self.key,
                owner=self.owner,
                expires_at=func.now() + timedelta(seconds=90),
            )
            row = await session.scalar(
                statement.on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "owner": self.owner,
                        "expires_at": statement.excluded.expires_at,
                    },
                    where=TelegramLease.expires_at < func.now(),
                ).returning(TelegramLease.owner)
            )
            await session.commit()
            return row == self.owner

    async def renew(self):
        async with self.sessions() as session:
            result = await session.execute(
                update(TelegramLease)
                .where(
                    TelegramLease.key == self.key,
                    TelegramLease.owner == self.owner,
                    TelegramLease.expires_at > func.now(),
                )
                .values(expires_at=func.now() + timedelta(seconds=90))
                .returning(TelegramLease.key)
            )
            owned = result.scalar_one_or_none() is not None
            await session.commit()
            return owned

    async def release(self):
        async with self.sessions() as session:
            await session.execute(
                delete(TelegramLease).where(
                    TelegramLease.key == self.key, TelegramLease.owner == self.owner
                )
            )
            await session.commit()


class WebhookRuntime:
    """Standby receivers can become healthy during a rolling deployment.

    Only the lease holder initializes PTB conversation state and dispatches.
    This avoids both stale state and a rollout waiting forever for the old host.
    """

    def __init__(self, sessions, bot_id, builder):
        self.sessions, self.builder = sessions, builder
        self.inbox = Inbox(sessions)
        self.lease = DispatcherLease(sessions, bot_id)
        self.wakeup = asyncio.Event()
        self.active = False
        self.stopping = False

    async def run(self):
        while not self.stopping:
            if not await self.lease.acquire():
                await asyncio.sleep(2)
                continue
            app = self.builder()
            initialized = False
            renewer = None
            try:
                await self.inbox.recover()
                await app.initialize()
                initialized = True
                await app.start()
                self.active = True
                dispatcher = asyncio.current_task()

                async def renew():
                    try:
                        while True:
                            await asyncio.sleep(20)
                            if not await self.lease.renew():
                                raise RuntimeError("Dispatcher lease lost")
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.error("webhook.lease_lost")
                        dispatcher.cancel()

                renewer = asyncio.create_task(renew())
                while not self.stopping:
                    ai = app.bot_data.get("ai_service")
                    if ai is not None:
                        async with self.sessions() as session:
                            pending = await session.scalars(
                                select(Event.id)
                                .where(
                                    Event.status == ProcessingStatus.pending,
                                    Event.is_deleted.is_(False),
                                )
                                .order_by(Event.captured_at)
                                .limit(32)
                            )
                            for identifier in pending:
                                ai.schedule(identifier)
                    if await self.inbox.process_one(app):
                        continue
                    self.wakeup.clear()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self.wakeup.wait(), timeout=2)
            finally:
                self.active = False
                if renewer:
                    renewer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await renewer
                if app.running:
                    await app.stop()
                if initialized:
                    await app.shutdown()
                with contextlib.suppress(Exception):
                    await self.lease.release()

    async def stop(self):
        self.stopping = True
        self.wakeup.set()
