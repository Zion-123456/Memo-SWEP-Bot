"""Groq implementation of the :class:`~app.ai.provider.AIProvider` interface.

API key is accepted only via constructor (wired from settings) and is never
logged, serialised in errors, or returned to clients. Transcription uses the
currently supported Whisper model; it is configurable because model names
change over time.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from groq import APIConnectionError, APIError, APITimeoutError, AsyncGroq

from app.ai.exceptions import AIProviderError, AIValidationError
from app.ai.longitudinal_models import (
    LongitudinalAnalysisResult,
    MemoryQueryAnswer,
    ProgressNarrative,
    WeeklyReflectionContent,
)
from app.ai.models import MemoryAnalysis
from app.ai.prompts import build_extraction_messages, build_reflection_messages
from app.ai.prompts.longitudinal_analysis import build_longitudinal_messages
from app.ai.prompts.memory_query import build_memory_query_messages
from app.ai.prompts.progress_narrative import build_progress_narrative_messages
from app.ai.prompts.weekly_reflection import build_weekly_reflection_messages

logger = structlog.get_logger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3"
_RESPONSE_MAX_TOKENS = 1024


def _strip_code_fences(content: str) -> str:
    """Remove markdown code-fences so ``json.loads`` only sees the JSON payload."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class GroqProvider:
    """AI provider backed by the Groq API (chat + audio transcription)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("GroqProvider requires an API key.")
        self._model = model
        self._transcription_model = transcription_model
        self._timeout = timeout
        self._client: AsyncGroq | None = None
        # Store the key only inside the lazy client; never expose it.
        self._api_key = api_key

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def transcription_model(self) -> str:
        return self._transcription_model

    def _client_lazy(self) -> AsyncGroq:
        """Lazily build the async client so no network happens at import."""
        if self._client is None:
            self._client = AsyncGroq(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def analyze_memory(self, memory: str) -> MemoryAnalysis:
        """Extract a :class:`MemoryAnalysis` from raw memory text."""
        if not memory or not memory.strip():
            return MemoryAnalysis(
                model_used=self._model,
                processed_at=datetime.now(UTC).isoformat(),
            )

        messages = build_extraction_messages(memory)
        client = self._client_lazy()
        try:
            completion = await client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[call-overload]
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=_RESPONSE_MAX_TOKENS,
            )
        except APITimeoutError as exc:
            raise AIProviderError(
                "Groq request timed out during memory analysis.",
                category="timeout",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderError(
                "Network error contacting Groq for memory analysis.",
                category="network",
                retryable=True,
            ) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            category = "quota" if status == 429 else "provider_error"
            retryable = status == 429
            raise AIProviderError(
                f"Groq API error during memory analysis (status={status}).",
                category=category,
                retryable=retryable,
            ) from exc

        content = (completion.choices[0].message.content or "").strip()
        content = _strip_code_fences(content)
        if not content:
            raise AIValidationError("Groq returned an empty analysis response.")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIValidationError("Groq response was not valid JSON.") from exc

        if not isinstance(data, dict):
            raise AIValidationError("Groq JSON response was not an object.")

        analysis = MemoryAnalysis.from_dict(data)
        analysis.model_used = self._model or None
        analysis.processed_at = datetime.now(UTC).isoformat()
        logger.debug(
            "ai.analyzed",
            provider=self.provider_name,
            model=self._model,
            has_summary=analysis.summary is not None,
        )
        return analysis

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> str:
        """Transcribe an audio file via Groq Whisper. Returns derived text."""
        if not audio_bytes:
            return ""
        client = self._client_lazy()
        try:
            transcription = await client.audio.transcriptions.create(
                model=self._transcription_model,
                file=(filename, audio_bytes, mime_type),
            )
        except APITimeoutError as exc:
            raise AIProviderError(
                "Groq transcription request timed out.",
                category="timeout",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderError(
                "Network error contacting Groq for transcription.",
                category="network",
                retryable=True,
            ) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            category = "quota" if status == 429 else "provider_error"
            retryable = status == 429
            raise AIProviderError(
                f"Groq API error during transcription (status={status}).",
                category=category,
                retryable=retryable,
            ) from exc

        text = getattr(transcription, "text", "") or ""
        return text.strip()

    async def generate_reflection(
        self,
        memory: str,
        analysis: dict[str, Any],
    ) -> str:
        """Generate a short insight string from validated analysis."""
        if not analysis:
            return ""
        messages = build_reflection_messages(memory, analysis)
        client = self._client_lazy()
        try:
            completion = await client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.3,
                max_tokens=128,
            )
        except (APIError, APITimeoutError, APIConnectionError):
            logger.warning("ai.reflection_failed", provider=self.provider_name)
            return ""
        return (completion.choices[0].message.content or "").strip()

    async def classify_intent(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> str | None:
        """Classify a user message into an intent (structured JSON output)."""
        client = self._client_lazy()
        try:
            completion = await client.chat.completions.create(
                model=model or self._model,
                messages=messages,  # type: ignore[call-overload]
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=256,
            )
        except APITimeoutError as exc:
            raise AIProviderError(
                "Groq request timed out during intent classification.",
                category="timeout",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderError(
                "Network error contacting Groq for intent classification.",
                category="network",
                retryable=True,
            ) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            category = "quota" if status == 429 else "provider_error"
            retryable = status == 429
            raise AIProviderError(
                f"Groq API error during intent classification (status={status}).",
                category=category,
                retryable=retryable,
            ) from exc

        content = (completion.choices[0].message.content or "").strip()
        return content if content else None

    async def _json_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Shared JSON-object chat completion helper."""
        client = self._client_lazy()
        try:
            completion = await client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[call-overload]
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APITimeoutError as exc:
            raise AIProviderError(
                "Groq request timed out.",
                category="timeout",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderError(
                "Network error contacting Groq.",
                category="network",
                retryable=True,
            ) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            category = "quota" if status == 429 else "provider_error"
            retryable = status == 429
            raise AIProviderError(
                f"Groq API error (status={status}).",
                category=category,
                retryable=retryable,
            ) from exc

        content = _strip_code_fences(
            (completion.choices[0].message.content or "").strip()
        )
        if not content:
            raise AIValidationError("Groq returned an empty JSON response.")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIValidationError("Groq response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise AIValidationError("Groq JSON response was not an object.")
        return data

    async def analyze_longitudinal(
        self,
        memories: list[dict[str, Any]],
    ) -> LongitudinalAnalysisResult:
        if not memories:
            return LongitudinalAnalysisResult(insufficient_evidence=True)
        data = await self._json_completion(
            build_longitudinal_messages(memories),
            max_tokens=2048,
        )
        return LongitudinalAnalysisResult.from_dict(data)

    async def generate_progress_narrative(
        self,
        evidence: dict[str, Any],
    ) -> ProgressNarrative:
        if not evidence.get("memories"):
            return ProgressNarrative(insufficient_evidence=True)
        data = await self._json_completion(
            build_progress_narrative_messages(evidence),
            max_tokens=1024,
            temperature=0.2,
        )
        return ProgressNarrative.from_dict(data)

    async def generate_weekly_reflection(
        self,
        evidence: dict[str, Any],
    ) -> WeeklyReflectionContent:
        if not evidence.get("memories"):
            return WeeklyReflectionContent(insufficient_evidence=True)
        data = await self._json_completion(
            build_weekly_reflection_messages(evidence),
            max_tokens=1024,
            temperature=0.2,
        )
        return WeeklyReflectionContent.from_dict(data)

    async def answer_memory_query(
        self,
        query: str,
        memories: list[dict[str, Any]],
    ) -> MemoryQueryAnswer:
        if not memories:
            return MemoryQueryAnswer(
                answer=(
                    "I don't have any memories matching that yet. "
                    "Tell Memo what happened and I'll remember it."
                ),
                insufficient_evidence=True,
            )
        data = await self._json_completion(
            build_memory_query_messages(query, memories),
            max_tokens=768,
            temperature=0.1,
        )
        return MemoryQueryAnswer.from_dict(data)
