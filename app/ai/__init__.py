"""AI Memory Intelligence Layer for Memo (Sprint 3).

This package contains:

* :class:`app.ai.provider.AIProvider` – the abstract interface any AI backend
  must implement (Groq is the MVP implementation).
* :class:`app.ai.groq.GroqProvider` – the concrete Groq provider.
* :class:`app.ai.models.MemoryAnalysis` – the structured, validated output of
  memory analysis.
* :mod:`app.ai.prompts` – dedicated, versionable prompt definitions kept out of
  handlers/services so they can be tuned independently.

Design notes
------------
* No credentials are accepted, logged, or exposed by anything in this package.
* The provider interface is intentionally small and backend-agnostic so Groq can
  be swapped for any other provider later.
"""

from __future__ import annotations

from app.ai.groq import GroqProvider
from app.ai.models import MemoryAnalysis
from app.ai.provider import AIProvider

__all__ = ["AIProvider", "GroqProvider", "MemoryAnalysis"]
