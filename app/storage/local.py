"""Local file system implementation of StorageProvider."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
import aiofiles.os
import structlog

from app.storage.exceptions import FileNotFoundError, StorageError

logger = structlog.get_logger(__name__)


class LocalStorageProvider:
    """Stores files on the local filesystem relative to a base directory."""

    def __init__(self, base_dir: str | Path = "./data/uploads") -> None:
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def store(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        subfolder: str = "",
    ) -> str:
        """Save file bytes locally under base_dir/subfolder/{uuid}_{filename}."""
        try:
            target_dir = self._base_dir / subfolder if subfolder else self._base_dir
            await aiofiles.os.makedirs(target_dir, exist_ok=True)

            unique_filename = f"{uuid.uuid4().hex}_{Path(filename).name}"
            file_path = target_dir / unique_filename

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)

            # Store relative path for portability across environments
            rel_path = file_path.relative_to(self._base_dir).as_posix()
            logger.info("storage.file_saved", relative_path=rel_path, bytes=len(data))
            return rel_path

        except Exception as exc:
            logger.error("storage.store_failed", error=str(exc), filename=filename)
            raise StorageError(f"Failed to store file '{filename}' locally.", details=str(exc)) from exc

    async def delete(self, storage_url: str) -> bool:
        """Delete local file by relative path."""
        try:
            file_path = (self._base_dir / storage_url).resolve()

            if not file_path.is_relative_to(self._base_dir):
                raise StorageError("Access denied: path outside storage root.")

            if not file_path.exists():
                return False

            await aiofiles.os.remove(file_path)
            logger.info("storage.file_deleted", relative_path=storage_url)
            return True

        except Exception as exc:
            if isinstance(exc, StorageError):
                raise
            logger.error("storage.delete_failed", error=str(exc), relative_path=storage_url)
            raise StorageError(f"Failed to delete file '{storage_url}'.", details=str(exc)) from exc

    async def read(self, storage_url: str) -> bytes:
        """Read file bytes from local storage."""
        try:
            file_path = (self._base_dir / storage_url).resolve()

            if not file_path.is_relative_to(self._base_dir):
                raise StorageError("Access denied: path outside storage root.")

            if not file_path.exists():
                raise FileNotFoundError(f"File '{storage_url}' not found.")

            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()

        except (FileNotFoundError, StorageError):
            raise
        except Exception as exc:
            logger.error("storage.read_failed", error=str(exc), relative_path=storage_url)
            raise StorageError(f"Failed to read file '{storage_url}'.", details=str(exc)) from exc
