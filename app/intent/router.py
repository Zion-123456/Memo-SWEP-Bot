"""Intent router — classifies messages and routes to the appropriate handler."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.intent.classifier import IntentClassifier
from app.intent.models import IntentResult, IntentType
from app.ai.provider import AIProvider
from app.repositories.event import EventRepository
from app.repositories.knowledge_topic import KnowledgeTopicRepository
from app.repositories.memory_connection import MemoryConnectionRepository
from app.services.memory_query import MemoryQueryService
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.progress_narrative import ProgressNarrativeService

logger = structlog.get_logger(__name__)


class IntentRouter:
    """Routes classified user messages to the appropriate service."""

    def __init__(
        self,
        classifier: IntentClassifier,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        ai_provider: AIProvider | None = None,
        progress_narrative_service_factory: Any | None = None,
    ) -> None:
        self._classifier = classifier
        self._session_factory = session_factory
        self._ai_provider = ai_provider
        self._progress_factory = progress_narrative_service_factory

    @property
    def classifier(self) -> IntentClassifier:
        return self._classifier

    async def route(
        self,
        text: str,
        *,
        user_id: UUID,
        telegram_user_id: int,
        chat_id: int,
        reply_to_message_id: int | None = None,
        context: Any = None,
    ) -> IntentResult:
        result = await self._classifier.classify(text)
        logger.debug(
            "intent.routed",
            intent=result.intent.value,
            confidence=result.confidence,
        )
        await self._dispatch(
            result,
            user_id,
            telegram_user_id,
            chat_id,
            reply_to_message_id,
            context,
        )
        return result

    async def _dispatch(
        self,
        result: IntentResult,
        user_id: UUID,
        telegram_user_id: int,
        chat_id: int,
        reply_to_message_id: int | None,
        context: Any,
    ) -> None:
        if context is None:
            return

        bot = context.bot
        if result.intent == IntentType.CONVERSATION:
            await self._handle_conversation(result, bot, chat_id, reply_to_message_id)
        elif result.intent == IntentType.UNKNOWN:
            await self._handle_unknown(result, bot, chat_id, reply_to_message_id)
        elif result.intent == IntentType.ACTION:
            await self._handle_action(
                result,
                user_id,
                telegram_user_id,
                chat_id,
                reply_to_message_id,
                context,
            )
        elif result.intent == IntentType.RETRIEVE:
            await self._handle_retrieval(
                result, user_id, chat_id, reply_to_message_id, context
            )
        elif result.intent == IntentType.REFLECT:
            await self._handle_reflection(
                result, user_id, chat_id, reply_to_message_id, context
            )

    async def _handle_conversation(
        self,
        result: IntentResult,
        bot: Any,
        chat_id: int,
        reply_to_message_id: int | None,
    ) -> None:
        await bot.send_message(
            chat_id=chat_id,
            text=self._conversational_reply(result.raw_text or ""),
            reply_to_message_id=reply_to_message_id,
        )

    async def _handle_unknown(
        self,
        result: IntentResult,
        bot: Any,
        chat_id: int,
        reply_to_message_id: int | None,
    ) -> None:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "I'm not sure what you'd like me to do with that.\n\n"
                "Would you like to save it as a memory, or "
                "ask about your memories?\n\n"
                "💾 Save as memory\n"
                "📖 Ask about my memories"
            ),
            reply_to_message_id=reply_to_message_id,
        )

    async def _handle_action(
        self,
        result: IntentResult,
        user_id: UUID,
        telegram_user_id: int,
        chat_id: int,
        reply_to_message_id: int | None,
        context: Any,
    ) -> None:
        bot = context.bot
        action = (result.action or "").lower()
        raw_lower = (result.raw_text or "").lower()

        if "help" in action or "what can" in raw_lower:
            await bot.send_message(
                chat_id=chat_id,
                text=self._help_reply(),
                reply_markup=build_dashboard_keyboard(),
                reply_to_message_id=reply_to_message_id,
            )
            return

        if "dashboard" in action or "profile" in action:
            await bot.send_message(
                chat_id=chat_id,
                text=self._profile_reply(),
                reply_markup=build_dashboard_keyboard(),
                reply_to_message_id=reply_to_message_id,
            )
            return

        if "delete" in action:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🗑️ To delete a memory, send "
                    "/delete <event_id> or use the dashboard."
                ),
                reply_to_message_id=reply_to_message_id,
            )
            return

        await bot.send_message(
            chat_id=chat_id,
            text=self._help_reply(),
            reply_markup=build_dashboard_keyboard(),
            reply_to_message_id=reply_to_message_id,
        )

    async def _handle_retrieval(
        self,
        result: IntentResult,
        user_id: UUID,
        chat_id: int,
        reply_to_message_id: int | None,
        context: Any,
    ) -> None:
        bot = context.bot
        query = result.query or result.raw_text or ""

        async with self._session_factory() as session:
            if self._ai_provider is not None:
                query_service = MemoryQueryService(
                    MemoryRetrievalService(EventRepository(session)),
                    self._ai_provider,
                    enabled=True,
                )
                text = await query_service.answer(
                    user_id,
                    query,
                    time_range=result.time_range,
                    topic=result.topic,
                )
            else:
                retrieval = MemoryRetrievalService(EventRepository(session))
                events = await retrieval.retrieve(
                    user_id,
                    query=query,
                    time_range=result.time_range,
                    topic=result.topic,
                )
                text = (
                    self._format_memories(list(events))
                    if events
                    else (
                        "🧠 You don't have any memories matching that "
                        "query yet.\n\n"
                        "Tell Memo what happened today and I'll "
                        "remember it for you."
                    )
                )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )

    async def _handle_reflection(
        self,
        result: IntentResult,
        user_id: UUID,
        chat_id: int,
        reply_to_message_id: int | None,
        context: Any,
    ) -> None:
        bot = context.bot
        async with self._session_factory() as session:
            if self._progress_factory is not None:
                service = self._progress_factory(session)
            else:
                service = ProgressNarrativeService(
                    EventRepository(session),
                    KnowledgeTopicRepository(session),
                    MemoryConnectionRepository(session),
                )
            narrative = await service.generate(user_id)
            text = narrative.to_telegram_text()

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )

    def _conversational_reply(self, text: str) -> str:
        lower = text.lower().strip()
        if any(w in lower for w in ("hello", "hi", "hey")):
            return (
                "Hello! I'm Memo — your AI memory "
                "assistant. 📝\n\n"
                "Tell me what happened today, or ask me "
                "about your memories."
            )
        if any(w in lower for w in ("thank", "thanks", "thx")):
            return "You're welcome! 😊 What would you like to do next?"
        if any(w in lower for w in ("what can", "how does", "what are you")):
            return (
                "I'm Memo — your AI memory operating "
                "system.\n\n"
                "You can:\n"
                "• Tell me what happened and I'll remember it\n"
                "• Ask me questions about your memories\n"
                "• Ask me to reflect on your progress\n\n"
                'Try: "What did I learn today?" '
                'or "How have I progressed?"'
            )
        return (
            "I'm here to help you capture and reflect on "
            "your learning.\n\n"
            "You can tell me what happened today, or "
            "ask about your memories.\n\n"
            '💡 Tip: Send "How have I progressed?" '
            "to see your journey."
        )

    def _help_reply(self) -> str:
        return (
            "💬 Ask Memo\n\n"
            "You can ask me things like:\n"
            "• What did I learn this week?\n"
            "• How have I progressed?\n"
            "• What skills am I developing?\n"
            "• What did I work on yesterday?\n"
            "• What have I learned about drilling?\n"
            "• What should I improve?"
        )

    def _profile_reply(self) -> str:
        return (
            "⚙️ Open my dashboard\n\n"
            "Use the buttons below to navigate "
            "Memo's capabilities."
        )

    def _format_memories(self, events: list) -> str:
        lines = ["🧠 Your Memories:\n"]
        for idx, evt in enumerate(events, 1):
            date_str = (
                evt.event_date.strftime("%d %b %Y") if evt.event_date else "unknown"
            )
            raw = evt.raw_text or ""
            preview = raw[:100] + "..." if len(raw) > 100 else raw
            summary = evt.ai_analysis.get("summary") if evt.ai_analysis else None
            display = summary or preview
            lines.append(f"{idx}. [{date_str}] {display}")
            lines.append("")
        return "\n".join(lines)


def build_dashboard_keyboard() -> Any:
    from app.telegram.keyboards.dashboard import build_dashboard_keyboard as _builder

    return _builder()
