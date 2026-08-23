"""Groq implementation of the :class:`~app.ai.provider.AIProvider` interface.

API key is accepted only via constructor and is never logged or returned to
clients. Groq remains an implementation detail behind the AIProvider boundary.
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
        if self._client is None:
            self._client = AsyncGroq(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def analyze_memory(self, memory: str) -> MemoryAnalysis:
        if not memory or not memory.strip():
            return MemoryAnalysis(
                model_used=self._model,
                processed_at=datetime.now(UTC).isoformat(),
            )
        messages = build_extraction_messages(memory)
        data = await self._json_completion(
            messages, max_tokens=_RESPONSE_MAX_TOKENS, temperature=0.1
        )
        analysis = MemoryAnalysis.from_dict(data)
        analysis.model_used = self._model or None
        analysis.processed_at = datetime.now(UTC).isoformat()
        logger.debug("ai.analyzed", provider=self.provider_name, model=self._model)
        return analysis

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> str:
        if not audio_bytes:
            return ""
        client = self._client_lazy()
        try:
            transcription = await client.audio.transcriptions.create(
                model=self._transcription_model,
                file=(filename, audio_bytes, mime_type),
            )
        except APITimeoutError as exc:
            raise AIProviderError("Groq transcription request timed out.", category="timeout", retryable=True) from exc
        except APIConnectionError as exc:
            raise AIProviderError("Network error contacting Groq for transcription.", category="network", retryable=True) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            raise AIProviderError(
                f"Groq API error during transcription (status={status}).",
                category="quota" if status == 429 else "provider_error",
                retryable=status == 429,
            ) from exc
        return (getattr(transcription, "text", "") or "").strip()

    async def generate_reflection(self, memory: str, analysis: dict[str, Any]) -> str:
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
        data = await self._json_completion(messages, max_tokens=256, temperature=0.1, model=model)
        return json.dumps(data, ensure_ascii=False)

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate a validated JSON object for domain workflows such as SWEP."""
        return await self._json_completion(messages, max_tokens=max_tokens, temperature=temperature)

    async def _json_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> dict[str, Any]:
        client = self._client_lazy()
        try:
            completion = await client.chat.completions.create(
                model=model or self._model,
                messages=messages,  # type: ignore[call-overload]
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APITimeoutError as exc:
            raise AIProviderError("Groq request timed out.", category="timeout", retryable=True) from exc
        except APIConnectionError as exc:
            raise AIProviderError("Network error contacting Groq.", category="network", retryable=True) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            raise AIProviderError(
                f"Groq API error (status={status}).",
                category="quota" if status == 429 else "provider_error",
                retryable=status == 429,
            ) from exc
        content = _strip_code_fences((completion.choices[0].message.content or "").strip())
        if not content:
            raise AIValidationError("Groq returned an empty JSON response.")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIValidationError("Groq response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise AIValidationError("Groq JSON response was not an object.")
        return data

    async def analyze_longitudinal(self, memories: list[dict[str, Any]]) -> LongitudinalAnalysisResult:
        if not memories:
            return LongitudinalAnalysisResult(insufficient_evidence=True)
        return LongitudinalAnalysisResult.from_dict(await self._json_completion(build_longitudinal_messages(memories), max_tokens=2048))

    async def generate_progress_narrative(self, evidence: dict[str, Any]) -> ProgressNarrative:
        if not evidence.get("memories"):
            return ProgressNarrative(insufficient_evidence=True)
        return ProgressNarrative.from_dict(await self._json_completion(build_progress_narrative_messages(evidence), max_tokens=1024, temperature=0.2))

    async def generate_weekly_reflection(self, evidence: dict[str, Any]) -> WeeklyReflectionContent:
        if not evidence.get("memories"):
            return WeeklyReflectionContent(insufficient_evidence=True)
        return WeeklyReflectionContent.from_dict(await self._json_completion(build_weekly_reflection_messages(evidence), max_tokens=1024, temperature=0.2))

    async def answer_memory_query(self, query: str, memories: list[dict[str, Any]]) -> MemoryQueryAnswer:
        if not memories:
            return MemoryQueryAnswer(
                answer="I don't have any memories matching that yet. Tell Memo what happened and I'll remember it.",
                insufficient_evidence=True,
            )
        return MemoryQueryAnswer.from_dict(await self._json_completion(build_memory_query_messages(query, memories), max_tokens=1024, temperature=0.2))
