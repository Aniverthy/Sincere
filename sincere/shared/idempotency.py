"""Idempotency keys — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §7:391 and §18 require idempotency keys on **payment and bid
endpoints**. A mobile client on a flaky network will retry a checkout; without this, the retry
charges twice.

Semantics: the first request for a key claims it and stores the response. A replay returns the
stored response verbatim. A replay arriving while the original is still in flight gets 409 —
returning a partial result would be worse than asking the client to wait.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from sincere.shared.db import C, collection
from sincere.shared.errors import ConflictError

logger = logging.getLogger(__name__)

#: How long a key stays claimed. Long enough to cover any realistic client retry window.
RETENTION_HOURS = 24


def fingerprint(payload: Any) -> str:
    """Hash of the request body, so the same key with a *different* body is caught."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def claim(key: str, endpoint: str, payload: Any) -> dict[str, Any] | None:
    """Claim ``key`` for ``endpoint``.

    Returns ``None`` when the caller owns the claim and should perform the operation.
    Returns the stored response dict when this is a completed replay.
    Raises :class:`ConflictError` when the original request is still in flight, or when the
    key is being reused with a different body.
    """
    now = datetime.now(UTC)
    body_hash = fingerprint(payload)

    try:
        await collection(C.IDEMPOTENCY_KEYS).insert_one(
            {
                "key": key,
                "endpoint": endpoint,
                "body_hash": body_hash,
                "status": "in_progress",
                "response": None,
                "created_at": now,
                "expires_at": now + timedelta(hours=RETENTION_HOURS),
            }
        )
        return None
    except DuplicateKeyError:
        pass

    existing = await collection(C.IDEMPOTENCY_KEYS).find_one({"key": key, "endpoint": endpoint})
    if existing is None:
        # Raced with the TTL sweeper between insert and read. Treat as a fresh claim.
        return None

    if existing["body_hash"] != body_hash:
        raise ConflictError(
            "Idempotency key reused",
            "This idempotency key was already used with a different request body.",
        )

    if existing["status"] == "in_progress":
        raise ConflictError(
            "Request in progress",
            "A request with this idempotency key is still being processed. Retry shortly.",
        )

    logger.info("idempotency.replay", extra={"endpoint": endpoint})
    return existing.get("response")


async def complete(key: str, endpoint: str, response: dict[str, Any]) -> None:
    """Store the response so a later replay can return it verbatim."""
    await collection(C.IDEMPOTENCY_KEYS).update_one(
        {"key": key, "endpoint": endpoint},
        {"$set": {"status": "completed", "response": response, "completed_at": datetime.now(UTC)}},
    )


async def release(key: str, endpoint: str) -> None:
    """Drop a claim after a failed operation, so the client's retry can proceed."""
    await collection(C.IDEMPOTENCY_KEYS).delete_one({"key": key, "endpoint": endpoint})
