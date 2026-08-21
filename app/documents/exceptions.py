"""Exceptions for the document extraction layer."""

from __future__ import annotations


class DocumentExtractionError(Exception):
    """Base exception for document extraction failures.

    Raised when a document cannot be processed for any reason.
    The original file is never deleted — this error only affects
    the derived text extraction step.
    """


class DocumentUnsupportedError(DocumentExtractionError):
    """Raised when a document type is not supported for text extraction.

    e.g. a scanned-image PDF, or a binary format with no text layer.
    """
