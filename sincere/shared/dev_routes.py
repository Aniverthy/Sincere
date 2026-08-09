"""Development-only object-storage endpoints.

In production, §4's pre-signed URLs point straight at S3-compatible storage and the bytes
never touch the API — that is both a §19 performance property and a §18 minimization one.

In development ``OBJECT_STORAGE_BUCKET`` is unset, so :class:`~sincere.shared.storage.LocalBackend`
stands in and its "pre-signed" URLs need something to actually accept the upload. These routes
are that something. They are mounted **only when the environment is not production** (see
``sincere.main``), so there is no path by which they can serve real user data.

Deliberately unauthenticated, exactly like the S3 pre-signed URLs they emulate: the object key
contains a UUID and is issued to an authenticated caller, which is the same security model.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from sincere.shared.storage import LocalBackend, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev/storage", tags=["dev"], include_in_schema=False)

#: Refuse anything larger than a short liveness video. Without a ceiling, a dev machine can be
#: filled by a single request.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _local() -> LocalBackend:
    backend = get_storage()
    if not isinstance(backend, LocalBackend):
        raise RuntimeError("dev storage routes are only valid with the local backend")
    return backend


@router.put("/{object_key:path}", status_code=status.HTTP_200_OK)
async def upload(object_key: str, request: Request) -> dict[str, object]:
    """Accept a PUT to a locally "pre-signed" URL, mirroring S3's semantics."""
    body = await request.body()
    if len(body) > MAX_UPLOAD_BYTES:
        return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)  # type: ignore[return-value]

    path = _local().path_for(object_key)
    path.write_bytes(body)

    logger.info("dev_storage.uploaded", extra={"object_key": object_key, "bytes": len(body)})
    return {"object_key": object_key, "bytes": len(body)}


@router.post("/{object_key:path}", status_code=status.HTTP_200_OK)
async def upload_multipart(object_key: str, request: Request) -> dict[str, object]:
    """Same, for clients that send multipart POST instead of a raw PUT.

    ``expo-file-system``'s upload helper defaults to multipart, so supporting both keeps the
    client free to use whichever transfer mode is reliable on a given platform.
    """
    form = await request.form()
    for value in form.values():
        if hasattr(value, "read"):
            body = await value.read()  # type: ignore[union-attr]
            _local().path_for(object_key).write_bytes(body)
            logger.info(
                "dev_storage.uploaded_multipart",
                extra={"object_key": object_key, "bytes": len(body)},
            )
            return {"object_key": object_key, "bytes": len(body)}

    body = await request.body()
    _local().path_for(object_key).write_bytes(body)
    return {"object_key": object_key, "bytes": len(body)}


@router.get("/{object_key:path}")
async def download(object_key: str) -> Response:
    """Serve a stored object, so profile photos render in the client during development."""
    path = _local().path_for(object_key)
    if not path.exists():
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    suffix = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".heic": "image/heic",
        ".mp4": "video/mp4",
    }.get(suffix, "application/octet-stream")

    return Response(content=path.read_bytes(), media_type=media_type)
