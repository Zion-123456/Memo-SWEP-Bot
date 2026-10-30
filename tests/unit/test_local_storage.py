"""Unit tests for LocalStorageProvider."""

from pathlib import Path

import pytest

from app.storage.exceptions import FileNotFoundError, StorageError
from app.storage.local import LocalStorageProvider


@pytest.mark.asyncio
async def test_local_storage_store_read_delete(tmp_path: Path) -> None:
    provider = LocalStorageProvider(base_dir=tmp_path)

    # 1. Store
    data = b"Hello, Memo Memory Engine!"
    filename = "test_log.txt"
    storage_url = await provider.store(data, filename, "text/plain", subfolder="2025/08/05")

    assert storage_url.endswith("test_log.txt")
    assert "2025/08/05" in storage_url

    # 2. Read
    read_bytes = await provider.read(storage_url)
    assert read_bytes == data

    # 3. Delete
    deleted = await provider.delete(storage_url)
    assert deleted is True

    # 4. Read after delete raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        await provider.read(storage_url)


@pytest.mark.asyncio
async def test_local_storage_path_traversal_protection(tmp_path: Path) -> None:
    provider = LocalStorageProvider(base_dir=tmp_path)

    with pytest.raises(StorageError, match="outside storage root"):
        await provider.read("../../../etc/passwd")


@pytest.mark.asyncio
@pytest.mark.parametrize("subfolder", ["../outside", "nested/../../outside"])
async def test_store_rejects_traversal_before_writing(tmp_path: Path, subfolder: str) -> None:
    root = tmp_path / "uploads"
    provider = LocalStorageProvider(root)
    with pytest.raises(StorageError):
        await provider.store(b"private evidence", "test.txt", "text/plain", subfolder)
    assert list(root.iterdir()) == []
    assert not (tmp_path / "outside").exists()


@pytest.mark.asyncio
async def test_store_rejects_absolute_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    provider = LocalStorageProvider(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    for subfolder in (str(outside), "link"):
        with pytest.raises(StorageError):
            await provider.store(b"private evidence", "test.txt", "text/plain", subfolder)
    assert list(outside.iterdir()) == []
