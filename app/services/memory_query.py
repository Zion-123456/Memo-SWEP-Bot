"""Memory query service — grounded NL answers about stored memories."""

from __future__ import annotations

import uuid

from app.ai.longitudinal_models import MemoryQueryAnswer
from app.ai.provider import AIProvider
from app.services.memory_retrieval import MemoryRetrievalService


class MemoryQueryService:
    """Answer natural-language questions using retrieved memories."""

    def __init__(
        self,
        retrieval_service: MemoryRetrievalService,
        ai_provider: AIProvider | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._retrieval = retrieval_service
        self._provider = ai_provider
        self._enabled = enabled and ai_provider is not None

    async def answer(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        time_range: str | None = None,
        topic: str | None = None,
    ) -> str:
        """Answer a user question using their stored memories."""
        resolved_time = time_range or MemoryRetrievalService.infer_time_range(query)
        resolved_topic = topic or MemoryRetrievalService.infer_topic(query)

        events = await self._retrieval.retrieve(
            user_id,
            query=query,
            time_range=resolved_time,
            topic=resolved_topic,
        )

        if not events:
            return (
                "🧠 I don't have any memories matching that yet.\n\n"
                "Tell Memo what happened and I'll remember it for you."
            )

        if self._enabled and self._provider is not None:
            evidence = MemoryRetrievalService.events_to_evidence(events)
            try:
                result = await self._provider.answer_memory_query(query, evidence)
                return self._format_answer(result)
            except Exception:
                pass

        return self._format_events_fallback(events)

    def _format_answer(self, result: MemoryQueryAnswer) -> str:
        if result.insufficient_evidence or not result.answer.strip():
            return (
                "🧠 I found some memories, but not enough specific evidence to "
                "answer that confidently. Try capturing more about this topic."
            )
        return f"🧠 {result.answer.strip()}"

    @staticmethod
    def _format_events_fallback(events: list) -> str:
        lines = ["🧠 From your memories:\n"]
        for idx, evt in enumerate(events[:10], 1):
            date_str = evt.event_date.strftime("%d %b %Y") if evt.event_date else "unknown"
            summary = (evt.ai_analysis or {}).get("summary") if evt.ai_analysis else None
            preview = summary or (evt.raw_text or "")[:100]
            lines.append(f"{idx}. [{date_str}] {preview}")
        return "\n".join(lines)
