"""Celery tasks owned by identity.

The retention-cleanup job in §15b is orchestrated by admin, but the identity-owned steps of
the §6 deletion cascade live here — the module that owns the data owns its deletion.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sincere.identity.jobs.purge_expired_captures", bind=True, max_retries=3)
def purge_expired_captures(self) -> dict[str, int]:
    """§8: verification captures are soft-deleted for 30 days, then hard-deleted.

    §21 alerts on ANY failure of a retention job — these deletions are legally mandated,
    so a silent skip is a compliance incident.
    """
    return asyncio.run(_purge_expired_captures())


async def _purge_expired_captures() -> dict[str, int]:
    from sincere.shared import cache, db, storage
    from sincere.shared.audit import AuditAction, record
    from sincere.shared.db import C, collection

    await db.connect()
    await cache.connect()

    now = datetime.now(UTC)
    purged = 0
    cursor = collection(C.VERIFICATION_CAPTURES).find({"hard_delete_after": {"$lte": now}})
    async for capture in cursor:
        try:
            await storage.get_storage().delete(capture["object_key"])
        except Exception as exc:  # noqa: BLE001 — a missing object should not block the row
            logger.warning("retention.object_delete_failed", extra={"error": str(exc)})
        await collection(C.VERIFICATION_CAPTURES).delete_one({"_id": capture["_id"]})
        purged += 1

    if purged:
        await record(
            AuditAction.HARD_DELETE_EXECUTED,
            context={"kind": "verification_captures", "count": purged},
        )
    logger.info("retention.captures_purged", extra={"count": purged})
    return {"purged": purged}


@celery_app.task(name="sincere.identity.jobs.execute_grace_period_deletions", bind=True)
def execute_grace_period_deletions(self) -> dict[str, int]:
    """§6: hard-delete accounts whose 30-day grace period has elapsed."""
    return asyncio.run(_execute_grace_period_deletions())


async def _execute_grace_period_deletions() -> dict[str, int]:
    from sincere.identity import api as identity_api
    from sincere.shared import cache, db
    from sincere.shared.db import C, collection

    await db.connect()
    await cache.connect()

    now = datetime.now(UTC)
    deleted = 0
    cursor = collection(C.USERS).find(
        {"status": "grace_period", "hard_delete_after": {"$lte": now}}
    )
    async for user in cursor:
        await identity_api.hard_delete_user(user["_id"])
        deleted += 1

    logger.info("retention.accounts_hard_deleted", extra={"count": deleted})
    return {"deleted": deleted}
