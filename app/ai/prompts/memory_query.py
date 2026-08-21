"""Prompt for natural-language memory queries."""

from __future__ import annotations

import json
from typing import Any


def build_memory_query_messages(
    query: str,
    memories: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build chat messages for answering a question about stored memories."""
    memory_json = json.dumps(memories, ensure_ascii=False)
    system = (
        "You answer questions about a student's captured memories.\n\n"
        "STRICT RULES:\n"
        "- ONLY use information in the supplied memories.\n"
        "- NEVER invent experiences, dates, skills, or achievements.\n"
        "- If the memories don't contain enough information, say so clearly.\n"
        "- List evidence_event_ids for memories you referenced.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "insufficient_evidence": boolean,\n'
        '  "answer": string,\n'
        '  "evidence_event_ids": [string]\n'
        "}"
    )
    user = (
        f"Question: {query}\n\n"
        f"Relevant memories:\n{memory_json}\n\n"
        "Answer the question using only these memories."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
