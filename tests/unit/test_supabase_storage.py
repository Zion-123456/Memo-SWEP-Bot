import httpx
import pytest

from app.storage.exceptions import StorageError
from app.storage.supabase import SupabaseStorageProvider


@pytest.mark.asyncio
async def test_private_upload_is_retrievable_after_provider_restart():
    objects = {}

    def remote(request):
        assert request.headers["authorization"] == "Bearer synthetic-storage-key"
        path = request.url.path
        if "/bucket/" in path:
            return httpx.Response(200, json={"public": False})
        if request.method == "POST":
            objects[path.split("/object/private/", 1)[1]] = request.content
            return httpx.Response(200, json={"Key": "stored"})
        if request.method == "GET":
            key = path.split("/object/authenticated/private/", 1)[1]
            return httpx.Response(200, content=objects[key])
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(remote)) as client:
        original = SupabaseStorageProvider(
            "https://existing.supabase.co",
            "private",
            "synthetic-storage-key",
            client=client,
        )
        await original.check_private_bucket()
        path = await original.store(
            b"private original", "../voice.ogg", "audio/ogg", "drafts/owner"
        )
        assert path.startswith("supabase:private/")
        assert "http" not in path
        restarted = SupabaseStorageProvider(
            "https://existing.supabase.co",
            "private",
            "synthetic-storage-key",
            client=client,
        )
        assert await restarted.read(path) == b"private original"


@pytest.mark.asyncio
async def test_public_bucket_is_rejected():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"public": True})
        )
    ) as client:
        storage = SupabaseStorageProvider(
            "https://existing.supabase.co", "private", "synthetic-key", client=client
        )
        with pytest.raises(StorageError, match="private"):
            await storage.check_private_bucket()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["supabase:private/../outside", "supabase:other/path", "/etc/passwd"]
)
async def test_storage_path_escape_and_wrong_bucket_are_rejected(path):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: pytest.fail("No request permitted")
        )
    ) as client:
        storage = SupabaseStorageProvider(
            "https://existing.supabase.co", "private", "synthetic-key", client=client
        )
        with pytest.raises(StorageError):
            await storage.read(path)


@pytest.mark.asyncio
async def test_upload_failure_does_not_expose_service_credential():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, text="synthetic-private-key")
        )
    ) as client:
        storage = SupabaseStorageProvider(
            "https://existing.supabase.co",
            "private",
            "synthetic-private-key",
            client=client,
        )
        with pytest.raises(StorageError) as caught:
            await storage.store(b"data", "file.txt", "text/plain")
        assert "synthetic-private-key" not in str(caught.value)
