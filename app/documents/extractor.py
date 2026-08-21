"""Abstract document text extractor interface.

Any document extraction backend (PyMuPDF, OCR, etc.) implements this Protocol.
Keeping the boundary here means the AI pipeline is decoupled from the
extraction implementation and OCR can be added later as a new extractor.
"""

from __future__ import annotations

from typing import Protocol

from app.documents.models import DocumentExtractionResult


class DocumentTextExtractor(Protocol):
    """Interface every document extraction backend must satisfy."""

    @property
    def extractor_name(self) -> str:
        """Stable name of the extractor (e.g. ``"pymupdf"``)."""
        ...

    async def extract(
        self,
        file_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
    ) -> DocumentExtractionResult:
        """Extract text from a document.

        Args:
            file_bytes: Raw document file bytes.
            filename: Original filename hint.
            mime_type: MIME type of the document.

        Returns:
            A :class:`DocumentExtractionResult` with the extracted text
            and metadata.

        Raises:
            DocumentExtractionError: On extraction failures.
            DocumentUnsupportedError: When the format is not supported.
        """
        ...
