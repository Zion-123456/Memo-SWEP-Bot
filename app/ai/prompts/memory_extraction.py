"""Memory extraction prompt.

Given a student's raw memory text, instruct the model to extract structured,
factual information. The system prompt enforces the product principle:

    CAPTURE -> PRESERVE RAW INPUT -> AI PROCESSING -> STRUCTURED MEMORY

The raw user text is the source of truth; the AI may only organise, not invent.
"""

from __future__ import annotations

from typing import Any

# Output schema the model must return. Kept minimal and stable so the
# :class:`~app.ai.models.MemoryAnalysis` validator can rely on it.
_MEMORY_SCHEMA = (
    '{"summary":"<string|null>",'
    '"activities":["..."],'
    '"skills":["..."],'
    '"tools":["..."],'
    '"projects":["..."],'
    '"people":["..."],'
    '"problems":["..."],'
    '"solutions":["..."],'
    '"lessons":["..."],'
    '"entities":["..."],'
    '"confidence":0.0}'
)

EXTRACTION_SYSTEM_PROMPT = f"""You are Memo, an AI memory intelligence assistant.
Your task is to extract structured information from a student's raw memory text.

RULES (strictly enforced — never violate these):
1. Extract ONLY information explicitly stated in the memory.
2. NEVER invent, fabricate, infer, or assume details. This includes but is not
   limited to: company names, model numbers, voltages, sensor types, machinery
   specifications, dates not present, personal identifiers, and technical
   procedures not mentioned by the student.
3. Preserve the student's exact technical terminology and wording.
4. If a field has no supporting information in the memory, return null (scalars)
   or an empty list (arrays) — never guess.
5. "problems" = what was wrong. "solutions" = what fixed it. "lessons" = what
   the student learned. Keep each entry grounded in the text.
6. "confidence" is YOUR self-rated confidence that the extraction is faithful
   to the memory, on a 0.0-1.0 scale.
7. Return ONLY a single JSON object matching this schema (no markdown, no
   extra keys, no commentary):
{_MEMORY_SCHEMA}"""


def build_extraction_messages(memory: str) -> list[dict[str, Any]]:
    """Build the chat message list for memory extraction.

    Args:
        memory: The student's raw memory text.

    Returns:
        A list of ``{"role": ..., "content": ...}`` messages.
    """
    user_content = (
        "Extract structured information from this student memory. "
        "Return ONLY valid JSON matching the schema in the system prompt. "
        "Do not invent anything.\n\n"
        f"MEMORY:\n\"\"\"\n{memory}\n\"\"\""
    )
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_extraction_prompt(memory: str) -> str:
    """Backwards-friendly single-prompt form (system + user joined)."""
    messages = build_extraction_messages(memory)
    return "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
