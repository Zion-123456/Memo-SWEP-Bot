"""Custom exceptions for the storage layer."""

from __future__ import annotations


class StorageError(Exception):
    """Base exception for file storage failures."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class StorageDownloadError(StorageError):
    """Raised when downloading media from an external provider (e.g. Telegram) fails."""


class FileNotFoundError(StorageError):
    """Raised when requested file is missing in storage."""
