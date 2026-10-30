"""Private Supabase Storage; credentials and authenticated URLs stay server-side."""

import uuid
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

import httpx

from app.storage.exceptions import FileNotFoundError, StorageError

MAX_BYTES = 20 * 1024 * 1024


class SupabaseStorageProvider:
    def __init__(self, url, bucket, key, *, client=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Use the existing Supabase project's HTTPS base URL.")
        if not bucket or any(
            c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in bucket
        ):
            raise ValueError("Invalid private bucket name")
        if not key:
            raise ValueError("A server-side storage credential is required")
        self.url, self.bucket = url.rstrip("/"), bucket
        self.client = client or httpx.AsyncClient(timeout=30)
        self.owns_client = client is None
        self.headers = {"Authorization": "Bearer " + key, "apikey": key}

    def _path(self, path):
        prefix = f"supabase:{self.bucket}/"
        if not path.startswith(prefix):
            raise StorageError("Legacy file requires a reviewed storage migration.")
        value = path[len(prefix) :]
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or any(part in (".", "..", "") for part in value.split("/"))
        ):
            raise StorageError("Invalid private object path")
        return quote(value, safe="/")

    async def check_private_bucket(self):
        try:
            response = await self.client.get(
                f"{self.url}/storage/v1/bucket/{self.bucket}", headers=self.headers
            )
            if (
                response.status_code != 200
                or response.json().get("public") is not False
            ):
                raise StorageError("The configured bucket must exist and be private.")
        except StorageError:
            raise
        except Exception:
            raise StorageError("Private storage readiness check failed") from None

    async def store(self, data, filename, content_type, subfolder=""):
        if len(data) > MAX_BYTES:
            raise StorageError("File exceeds the 20 MB limit")
        if subfolder and (
            subfolder.startswith("/")
            or "\\" in subfolder
            or any(p in (".", "..", "") for p in subfolder.split("/"))
        ):
            raise StorageError("Invalid private object path")
        safe_name = PurePosixPath(filename.replace("\\", "/")).name or "attachment"
        path = (
            f"supabase:{self.bucket}/"
            + (subfolder + "/" if subfolder else "")
            + uuid.uuid4().hex
            + "_"
            + safe_name[:200]
        )
        try:
            response = await self.client.post(
                f"{self.url}/storage/v1/object/{self.bucket}/{self._path(path)}",
                headers={
                    **self.headers,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                content=data,
            )
            if response.status_code not in (200, 201):
                raise StorageError("Private upload failed")
            return path
        except StorageError:
            raise
        except Exception:
            raise StorageError("Private upload failed") from None

    async def read(self, path):
        encoded = self._path(path)
        try:
            response = await self.client.get(
                f"{self.url}/storage/v1/object/authenticated/{self.bucket}/{encoded}",
                headers=self.headers,
            )
            if response.status_code == 404:
                raise FileNotFoundError("Private attachment not found")
            if response.status_code != 200 or len(response.content) > MAX_BYTES:
                raise StorageError("Private download failed")
            return response.content
        except (StorageError, FileNotFoundError):
            raise
        except Exception:
            raise StorageError("Private download failed") from None

    async def delete(self, path):
        self._path(path)
        prefix = f"supabase:{self.bucket}/"
        try:
            response = await self.client.request(
                "DELETE",
                f"{self.url}/storage/v1/object/{self.bucket}",
                headers=self.headers,
                json={"prefixes": [path[len(prefix) :]]},
            )
            if response.status_code not in (200, 204):
                raise StorageError("Private deletion failed")
            return True
        except StorageError:
            raise
        except Exception:
            raise StorageError("Private deletion failed") from None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()
