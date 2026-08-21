"""Storage provider abstract interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageProvider(Protocol):
    """Abstract interface for file storage implementations.
    
    Application code must depend on this interface, never directly
    on local file system or specific cloud SDKs.
    """

    async def store(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        subfolder: str = "",
    ) -> str:
        """Store a binary payload and return its unique storage location/URL.

        Args:
            data: Raw file bytes.
            filename: Target file name.
            content_type: MIME type of the file.
            subfolder: Optional relative subfolder (e.g. "2025/08/05").

        Returns:
            The storage URL or file path reference.
        """
        ...

    async def delete(self, storage_url: str) -> bool:
        """Remove a file from storage by its URL/path reference.

        Args:
            storage_url: The reference returned by store().

        Returns:
            True if deleted, False if file was not found.
        """
        ...

    async def read(self, storage_url: str) -> bytes:
        """Retrieve binary file contents from storage.

        Args:
            storage_url: The reference returned by store().

        Returns:
            Raw file bytes.
        """
        ...
