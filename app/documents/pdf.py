"""PDF text extraction using PyMuPDF (fitz).

PyMuPDF is a lightweight, local, high-performance PDF library that works
for text-based PDFs. Scanned-image PDFs return ``has_text=False`` rather
than crashing.

The extractor runs ``fitz.open`` in a thread via ``asyncio.to_thread`` so
it never blocks the event loop.
"""

from __future__ import annotations

import asyncio
import re

import structlog

from app.documents.exceptions import DocumentExtractionError, DocumentUnsupportedError
from app.documents.models import DocumentExtractionResult

logger = structlog.get_logger(__name__)

try:
    import pymupdf as fitz
except ImportError:
    fitz = None  # type: ignore[assignment]


_MAX_CHARACTERS_DEFAULT = 100_000


class PdfTextExtractor:
    """Extract text from PDF documents using PyMuPDF."""

    def __init__(self, max_characters: int = _MAX_CHARACTERS_DEFAULT) -> None:
        if fitz is None:
            raise ImportError(
                "PyMuPDF (pymupdf) is required for PDF extraction. "
                "Install it with: pip install pymupdf"
            )
        self._max_characters = max_characters

    @property
    def extractor_name(self) -> str:
        return "pymupdf"

    async def extract(
        self,
        file_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> DocumentExtractionResult:
        """Extract text from a PDF document.

        Args:
            file_bytes: Raw PDF file bytes.
            filename: Original filename hint.
            mime_type: MIME type (expected ``application/pdf``).

        Returns:
            A :class:`DocumentExtractionResult` with extracted text.

        Raises:
            DocumentUnsupportedError: If the file is not a valid PDF or
                contains no extractable text (e.g. scanned image PDF).
            DocumentExtractionError: On unexpected extraction errors.
        """
        if not file_bytes:
            return DocumentExtractionResult(
                text="",
                page_count=0,
                character_count=0,
                extraction_method=self.extractor_name,
                has_text=False,
            )

        try:
            result = await asyncio.to_thread(self._extract_sync, file_bytes, filename)
        except fitz.FileDataError as exc:
            raise DocumentUnsupportedError(
                f"Invalid or corrupted PDF: {filename}."
            ) from exc
        except DocumentUnsupportedError:
            raise
        except Exception as exc:
            logger.warning(
                "document.extraction_failed",
                filename=filename,
                error_type=type(exc).__name__,
            )
            raise DocumentExtractionError(
                f"Failed to extract text from PDF: {filename}."
            ) from exc

        return result

    def _extract_sync(
        self, file_bytes: bytes, filename: str
    ) -> DocumentExtractionResult:
        """Synchronous PDF extraction — runs in a thread."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
        page_count = doc.page_count
        texts: list[str] = []
        total_chars = 0

        for page in doc:  # type: ignore[attr-defined]
            page_text = page.get_text()
            if page_text:
                texts.append(page_text)
                total_chars += len(page_text)

        doc.close()  # type: ignore[no-untyped-call]

        raw_text = "\n".join(texts)
        normalized = self._normalize_text(raw_text)
        char_count = len(normalized)

        has_text = char_count > 0
        truncated = False
        if char_count > self._max_characters:
            normalized = normalized[: self._max_characters]
            truncated = True

        if not has_text:
            logger.info(
                "document.no_extractable_text",
                filename=filename,
                page_count=page_count,
            )

        return DocumentExtractionResult(
            text=normalized,
            page_count=page_count,
            character_count=char_count,
            extraction_method=self.extractor_name,
            has_text=has_text,
            error=(None if has_text else "No extractable text (scanned image PDF?)"),
            metadata={
                "filename": filename,
                "truncated": truncated,
            },
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize whitespace from extracted PDF text.

        Preserves paragraph breaks while collapsing excessive blank lines.
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        normalized_lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in lines]
        result = "\n".join(normalized_lines)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()
