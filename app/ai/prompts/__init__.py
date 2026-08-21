"""Prompt definitions for the AI Memory Intelligence Layer.

Prompts are kept as versionable, importable constants in dedicated modules so
they can be tuned, audited, and tested independently of handlers/services.
"""

from __future__ import annotations

from app.ai.prompts.memory_extraction import build_extraction_messages
from app.ai.prompts.memory_reflection import build_reflection_messages

__all__ = ["build_extraction_messages", "build_reflection_messages"]
