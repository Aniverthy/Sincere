"""Object storage — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §4: the liveness capture "uploads short video to a pre-signed
object-storage URL", and §5 has the API hand the client "randomized prompt sequence + pre-signed
upload URL". Profile photos follow the same path and are served via CDN (§16).

The bytes never transit the API. That is a §19 performance choice and a §18 data-minimization
one — the API process never holds a liveness video in memory.

A local filesystem backend stands in when object storage is unconfigured, so the full signup
flow is runnable in development without cloud credentials.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sincere.shared.config import get_settings

logger = logging.getLogger(__name__)

Purpose = Literal["liveness", "profile_photo"]

#: Where the dev-only storage routes are mounted (see ``sincere.shared.dev_routes``).
DEV_STORAGE_PREFIX = "/v1/dev/storage"


def absolutize(url: str, base_url: str) -> str:
    """Turn a backend-relative storage URL into one a mobile client can actually call.

    S3 returns absolute URLs already, so this is a no-op for the production backend. The local
    backend cannot know the host the client reached it on — localhost on the dev machine, a LAN
    IP from a phone — so the value is resolved per-request instead of configured.
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{base_url.rstrip('/')}{url}"

#: Prefix per purpose. Retention jobs (§15b) scan by prefix, so these are load-bearing.
PREFIXES: dict[Purpose, str] = {
    "liveness": "verification-captures",
    "profile_photo": "profile-photos",
}


@dataclass(slots=True, frozen=True)
class PresignedUpload:
    """What the client needs to upload directly to storage."""

    object_key: str
    upload_url: str
    fields: dict[str, str]
    expires_at: datetime
    method: str = "PUT"


def build_object_key(purpose: Purpose, user_id: str, extension: str) -> str:
    """Key layout: ``<prefix>/<user_id>/<uuid>.<ext>``.

    User-scoped so the deletion cascade (§6) can purge everything for an account by prefix
    rather than by tracking individual keys.
    """
    clean = extension.lstrip(".").lower()
    return f"{PREFIXES[purpose]}/{user_id}/{uuid.uuid4().hex}.{clean}"


class StorageBackend:
    """Interface. §3's adapter discipline applies to storage as much as to payments."""

    async def presign_upload(
        self, object_key: str, content_type: str
    ) -> PresignedUpload:  # pragma: no cover - interface
        raise NotImplementedError

    async def presign_download(self, object_key: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def delete(self, object_key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def delete_prefix(self, prefix: str) -> int:  # pragma: no cover
        """Used by the deletion cascade (§6) to purge an account's objects."""
        raise NotImplementedError

    async def read(self, object_key: str) -> bytes:  # pragma: no cover
        """Read raw bytes. Only the embedding pipeline uses this, and it discards the
        buffer immediately after producing the vector (§9, §18)."""
        raise NotImplementedError


class S3Backend(StorageBackend):
    """S3-compatible backend (AWS S3, R2, MinIO) — the *(assumed)* production choice."""

    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        self._bucket = settings.object_storage_bucket
        self._ttl = settings.presigned_url_ttl
        self._client = boto3.client(
            "s3",
            region_name=settings.object_storage_region,
            endpoint_url=settings.object_storage_endpoint,
            aws_access_key_id=settings.object_storage_key,
            aws_secret_access_key=settings.object_storage_secret,
        )

    async def presign_upload(self, object_key: str, content_type: str) -> PresignedUpload:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=self._ttl,
        )
        from datetime import timedelta

        return PresignedUpload(
            object_key=object_key,
            upload_url=url,
            fields={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl),
        )

    async def presign_download(self, object_key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=self._ttl,
        )

    async def delete(self, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    async def delete_prefix(self, prefix: str) -> int:
        paginator = self._client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
                deleted += len(objects)
        return deleted

    async def read(self, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        return response["Body"].read()


class LocalBackend(StorageBackend):
    """Filesystem backend for development. Never selected in production."""

    def __init__(self, root: str = ".storage") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "storage.local_backend — object storage is unconfigured; uploads go to %s. "
            "Never use this outside development.",
            self._root.resolve(),
        )

    def path_for(self, object_key: str) -> Path:
        """Filesystem location for an object key, creating the parent directory.

        Public because the dev-storage routes need it to accept and serve uploads.
        """
        path = self._root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def presign_upload(self, object_key: str, content_type: str) -> PresignedUpload:
        from datetime import timedelta

        self.path_for(object_key)
        return PresignedUpload(
            object_key=object_key,
            # Relative on purpose: the route absolutizes it against the request's own host,
            # so a phone on the LAN gets the dev machine's address rather than "localhost".
            upload_url=f"{DEV_STORAGE_PREFIX}/{object_key}",
            fields={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=get_settings().presigned_url_ttl),
        )

    async def presign_download(self, object_key: str) -> str:
        return f"{DEV_STORAGE_PREFIX}/{object_key}"

    async def delete(self, object_key: str) -> None:
        self.path_for(object_key).unlink(missing_ok=True)

    async def delete_prefix(self, prefix: str) -> int:
        target = self._root / prefix
        if not target.exists():
            return 0
        count = sum(1 for p in target.rglob("*") if p.is_file())
        for path in sorted(target.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        target.rmdir()
        return count

    async def read(self, object_key: str) -> bytes:
        return self.path_for(object_key).read_bytes()


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        settings = get_settings()
        _backend = S3Backend() if settings.object_storage_bucket else LocalBackend()
    return _backend
