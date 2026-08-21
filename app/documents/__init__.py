"""Document text extraction abstraction for Memo (Sprint 3.1).

Provides a backend-agnostic interface for extracting text from document
attachments (PDFs, DOCX, etc.) so the AI pipeline can analyse them.

Current implementation uses PyMuPDF (fitz) for text-based PDFs.
Scanned-image PDFs return ``has_text=False`` rather than crashing.
OCR can be plugged in later as an alternative :class:`DocumentTextExtractor`.
"""

from __future__ import annotations

from app.documents.exceptions import DocumentExtractionError
from app.documents.extractor import DocumentTextExtractor
from app.documents.models import DocumentExtractionResult
from app.documents.pdf import PdfTextExtractor

__all__ = [
    "DocumentExtractionError",
    "DocumentExtractionResult",
    "DocumentTextExtractor",
    "PdfTextExtractor",
]
