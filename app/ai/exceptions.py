"""Exception hierarchy for the AI Memory Intelligence Layer."""

from __future__ import annotations


class AIError(Exception):
    """Base exception for all AI-layer errors."""


class AINotConfiguredError(AIError):
    """Raised when AI processing is requested but AI is not configured/enabled."""


class AIProviderError(AIError):
    """Raised when a call to the AI provider fails.

    Args:
        message: Human-readable description (no API keys, no raw memory).
        category: Observability category, e.g. ``"timeout"``, ``"quota"``,
            ``"provider_error"``, ``"network"``.
        retryable: Whether the failure is worth retrying automatically.
    """

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        retryable: bool = True,
    ) -> None:
        self.category = category
        self.retryable = retryable
        super().__init__(message)


class AIValidationError(AIError):
    """Raised when a provider response cannot be parsed into ``MemoryAnalysis``."""
