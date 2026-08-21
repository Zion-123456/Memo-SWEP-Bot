"""Unit tests for GroqProvider — fully mocked, no live API calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from groq import APIConnectionError, APIError, APITimeoutError

from app.ai.exceptions import AIValidationError, AIProviderError
from app.ai.groq import GroqProvider, _strip_code_fences
from app.ai.models import MemoryAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_completion(content: str) -> MagicMock:
    """Build a mock Groq chat completion response with the given content."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_provider(captured_completions=None) -> tuple[GroqProvider, MagicMock]:
    """Create a GroqProvider with a fully mocked client."""
    provider = GroqProvider(
        api_key="test-key-not-real",
        model="openai/gpt-oss-120b",
    )
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = (
        captured_completions if captured_completions else AsyncMock()
    )
    mock_client.audio = MagicMock()
    mock_client.audio.transcriptions = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock()
    provider._client = mock_client
    return provider, mock_client


def _valid_analysis_json() -> str:
    return json.dumps({
        "summary": "Wired a three-phase motor starter.",
        "activities": ["motor wiring"],
        "skills": ["electrical"],
        "tools": ["multimeter"],
        "problems": ["starter tripping"],
        "solutions": ["replaced overload relay"],
        "lessons": ["verify voltage first"],
        "entities": ["motor", "starter"],
        "confidence": 0.85,
    })


# ---------------------------------------------------------------------------
# Constructor / properties
# ---------------------------------------------------------------------------


def test_provider_requires_api_key() -> None:
    """Empty API key raises ValueError."""
    with pytest.raises(ValueError, match="API key"):
        GroqProvider(api_key="")


def test_provider_name_and_model() -> None:
    provider = GroqProvider(api_key="key", model="custom-model")
    assert provider.provider_name == "groq"
    assert provider.default_model == "custom-model"
    assert provider.transcription_model == "whisper-large-v3"


# ---------------------------------------------------------------------------
# _strip_code_fences
# ---------------------------------------------------------------------------


def test_strip_code_fences_removes_backticks() -> None:
    fenced = f"```json\n{_valid_analysis_json()}\n```"
    assert _strip_code_fences(fenced) == _valid_analysis_json()


def test_strip_code_fences_no_fences() -> None:
    content = '{"summary": "test"}'
    assert _strip_code_fences(content) == content


# ---------------------------------------------------------------------------
# analyze_memory — success paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_memory_success() -> None:
    """Valid JSON response is parsed into MemoryAnalysis."""
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion(_valid_analysis_json())
    )

    analysis = await provider.analyze_memory("Today I wired a motor.")

    assert isinstance(analysis, MemoryAnalysis)
    assert analysis.summary == "Wired a three-phase motor starter."
    assert analysis.activities == ["motor wiring"]
    assert analysis.skills == ["electrical"]
    assert analysis.confidence == 0.85
    assert analysis.model_used == "openai/gpt-oss-120b"
    assert analysis.processed_at is not None


@pytest.mark.asyncio
async def test_analyze_memory_empty_memory_returns_default() -> None:
    """Empty/blank memory returns a default MemoryAnalysis without calling the API."""
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock()

    analysis = await provider.analyze_memory("")
    assert analysis.summary is None
    assert analysis.activities == []
    mock_client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_memory_strips_code_fences() -> None:
    """Code-fenced JSON responses are handled."""
    provider, mock_client = _make_provider()
    fenced = f"```json\n{_valid_analysis_json()}\n```"
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion(fenced)
    )

    analysis = await provider.analyze_memory("Test memory")
    assert analysis.summary == "Wired a three-phase motor starter."


@pytest.mark.asyncio
async def test_analyze_memory_no_key_leakage_in_error() -> None:
    """No API key or raw memory appears in raised exceptions."""
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(message="connection refused", request=MagicMock())
    )

    with pytest.raises(AIProviderError) as exc_info:
        await provider.analyze_memory("SECRET_API_KEY_12345")

    assert "test-key-not-real" not in str(exc_info.value)
    assert "GROQ_API_KEY" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# analyze_memory — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_memory_timeout_raises_provider_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APITimeoutError(request=MagicMock())
    )

    with pytest.raises(AIProviderError) as exc_info:
        await provider.analyze_memory("Test memory")

    assert exc_info.value.retryable is True
    assert exc_info.value.category == "timeout"


@pytest.mark.asyncio
async def test_analyze_memory_connection_error_raises_provider_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(message="connection error", request=MagicMock())
    )

    with pytest.raises(AIProviderError) as exc_info:
        await provider.analyze_memory("Test memory")

    assert exc_info.value.retryable is True
    assert exc_info.value.category == "network"


@pytest.mark.asyncio
async def test_analyze_memory_api_error_raises_provider_error() -> None:
    provider, mock_client = _make_provider()
    err = APIError(
        message="rate limited",
        request=MagicMock(),
        body={},
    )
    err.status_code = 429
    mock_client.chat.completions.create = AsyncMock(side_effect=err)

    with pytest.raises(AIProviderError) as exc_info:
        await provider.analyze_memory("Test memory")

    assert exc_info.value.category == "quota"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_analyze_memory_invalid_json_raises_validation_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("not valid json {")
    )

    with pytest.raises(AIValidationError, match="not valid JSON"):
        await provider.analyze_memory("Test memory")


@pytest.mark.asyncio
async def test_analyze_memory_empty_response_raises_validation_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("")
    )

    with pytest.raises(AIValidationError, match="empty"):
        await provider.analyze_memory("Test memory")


@pytest.mark.asyncio
async def test_analyze_memory_non_object_json_raises_validation_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion('["not", "an", "object"]')
    )

    with pytest.raises(AIValidationError, match="not an object"):
        await provider.analyze_memory("Test memory")


# ---------------------------------------------------------------------------
# transcribe_audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_audio_success() -> None:
    provider, mock_client = _make_provider()
    mock_transcription = MagicMock()
    mock_transcription.text = "Today I worked on the conveyor motor."
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

    transcript = await provider.transcribe_audio(
        b"fake-audio", filename="voice.ogg", mime_type="audio/ogg"
    )

    assert transcript == "Today I worked on the conveyor motor."
    mock_client.audio.transcriptions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_audio_empty_bytes_returns_empty() -> None:
    provider, mock_client = _make_provider()
    transcript = await provider.transcribe_audio(b"", filename="voice.ogg", mime_type="audio/ogg")
    assert transcript == ""
    mock_client.audio.transcriptions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcribe_audio_timeout_raises_provider_error() -> None:
    provider, mock_client = _make_provider()
    mock_client.audio.transcriptions.create = AsyncMock(
             side_effect=APITimeoutError(request=MagicMock())
    )

    with pytest.raises(AIProviderError) as exc_info:
        await provider.transcribe_audio(b"audio", filename="v.ogg", mime_type="audio/ogg")

    assert exc_info.value.retryable is True
    assert exc_info.value.category == "timeout"


@pytest.mark.asyncio
async def test_transcribe_audio_api_error_raises_provider_error() -> None:
    provider, mock_client = _make_provider()
    err = APIError(
        message="bad request",
        request=MagicMock(),
        body={},
    )
    err.status_code = 400
    mock_client.audio.transcriptions.create = AsyncMock(side_effect=err)

    with pytest.raises(AIProviderError) as exc_info:
        await provider.transcribe_audio(b"audio", filename="v.ogg", mime_type="audio/ogg")

    assert exc_info.value.category == "provider_error"


# ---------------------------------------------------------------------------
# generate_reflection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_reflection_success() -> None:
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("Great work on the motor wiring today!")
    )

    analysis = MemoryAnalysis(summary="Wired a motor", skills=["electrical"])
    insight = await provider.generate_reflection("raw memory", analysis)

    assert insight == "Great work on the motor wiring today!"


@pytest.mark.asyncio
async def test_generate_reflection_empty_analysis_returns_empty() -> None:
    provider, mock_client = _make_provider()
    insight = await provider.generate_reflection("raw", {})
    assert insight == ""
    mock_client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_reflection_api_error_returns_empty() -> None:
    """Reflection failures are non-fatal — returns empty string."""
    provider, mock_client = _make_provider()
    mock_client.chat.completions.create = AsyncMock(
         side_effect=APIError("oops", request=MagicMock(), body=None)
    )

    insight = await provider.generate_reflection("raw", {"summary": "test"})
    assert insight == ""
