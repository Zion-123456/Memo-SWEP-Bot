"""Abstract AI provider interface.

Any backend (Groq, OpenAI, Claude, a local model, or a test fake) implements
this protocol. Keeping the boundary here means Memo is never coupled to a single
provider — Groq is the MVP backend only.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.ai.longitudinal_models import (
    LongitudinalAnalysisResult,
    MemoryQueryAnswer,
    ProgressNarrative,
    WeeklyReflectionContent,
)
from app.ai.models import MemoryAnalysis


class AIProvider(Protocol):
    """Interface every AI backend must satisfy."""

    @property
    def provider_name(self) -> str:
        ...

    @property
    def default_model(self) -> str:
        ...

    async def analyze_memory(self, memory: str) -> MemoryAnalysis:
        ...

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> str:
        ...

    async def generate_reflection(
        self,
        memory: str,
        analysis: dict[str, Any],
    ) -> str:
        ...

    async def classify_intent(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> str | None:
        ...

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate and validate a JSON object for a domain-specific workflow."""
        ...

    async def analyze_longitudinal(
        self,
        memories: list[dict[str, Any]],
    ) -> LongitudinalAnalysisResult:
        ...

    async def generate_progress_narrative(
        self,
        evidence: dict[str, Any],
    ) -> ProgressNarrative:
        ...

    async def generate_weekly_reflection(
        self,
        evidence: dict[str, Any],
    ) -> WeeklyReflectionContent:
        ...

    async def answer_memory_query(
        self,
        query: str,
        memories: list[dict[str, Any]],
    ) -> MemoryQueryAnswer:
        ...
