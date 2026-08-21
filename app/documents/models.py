"""Result model for document text extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentExtractionResult:
    """Structured output of a document extraction operation.

    Attributes:
        text: The extracted and normalised text content.
            Empty string when ``has_text`` is ``False``.
        page_count: Number of pages in the document (0 if unknown).
        character_count: Length of the extracted text in characters.
        extraction_method: Name of the extractor that produced this result.
        has_text: Whether the document contained extractable text.
            ``False`` for scanned-image PDFs or unsupported formats.
        error: Optional error message if extraction partially failed.
        metadata: Additional metadata about the document.
    """

    text: str = ""
    page_count: int = 0
    character_count: int = 0
    extraction_method: str = ""
    has_text: bool = False
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
