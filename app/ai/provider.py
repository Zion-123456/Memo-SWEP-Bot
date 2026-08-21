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
        """Stable name of the backend (e.g. ``"groq"``)."""
        ...

    @property
    def default_model(self) -> str:
        """Model identifier currently in use."""
        ...

    async def analyze_memory(self, memory: str) -> MemoryAnalysis:
        """Extract structured information from a raw memory.

        Args:
            memory: The student's raw memory text.

        Returns:
            A validated :class:`MemoryAnalysis`.

        Raises:
            AIProviderError: On network/timeout/quota failures (retryable).
            AIValidationError: If the response cannot be parsed.
        """
        ...

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> str:
        """Transcribe an audio recording into text (derived data).

        Args:
            audio_bytes: Raw audio file bytes.
            filename: Original filename hint.
            mime_type: MIME type of the audio.

        Returns:
            The transcript text.

        Raises:
            AIProviderError: On provider/network failures.
        """
        ...

    async def generate_reflection(
        self,
        memory: str,
        analysis: dict[str, Any],
    ) -> str:
        """Produce a short, student-facing insight string.

        Args:
            memory: The raw memory text (context only).
            analysis: The validated structured analysis (as a dict).

        Returns:
            A short insight string.
        """
        ...

    async def classify_intent(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> str | None:
        """Classify a user message into an intent using structured JSON output.

        Args:
            messages: Chat-completion messages (system + user).
            model: Optional model override for this call.

        Returns:
            The raw LLM response text (expected to be JSON), or None if the
            provider cannot fulfil the request.
        """
        ...

    async def analyze_longitudinal(
        self,
        memories: list[dict[str, Any]],
    ) -> LongitudinalAnalysisResult:
        """Identify topics, progression, and connections across memories."""
        ...

    async def generate_progress_narrative(
        self,
        evidence: dict[str, Any],
    ) -> ProgressNarrative:
        """Generate an evidence-based progress narrative."""
        ...

    async def generate_weekly_reflection(
        self,
        evidence: dict[str, Any],
    ) -> WeeklyReflectionContent:
        """Generate a weekly reflection from week-scoped evidence."""
        ...

    async def answer_memory_query(
        self,
        query: str,
        memories: list[dict[str, Any]],
    ) -> MemoryQueryAnswer:
        """Answer a natural-language question using supplied memories."""
        ...
