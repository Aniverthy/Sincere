"""Celery tasks owned by admin — the retention cleanup (§15b) and the outbox sweeper.

§15b's retention job is the compliance-critical one: "Daily: 30-day grace hard-deletes; 90-day
chat purge post-unmatch (honoring investigation holds); 90-day device-signal purge."

§21: "Retention-cleanup job success — **Any** failure alerts — legally-mandated deletions."
§15:660: "a silently skipped auction close or retention purge is a business/legal incident,
not just a bug."

So this task is deliberately structured to run **every** stage even when one fails, and to
raise at the end if any stage did. Aborting on the first failure would silently skip the
remaining legally-mandated deletions.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    from sincere.shared import cache, db

    await db.connect()
    await cache.connect()


@celery_app.task(name="sincere.admin.jobs.retention_cleanup", bind=True, max_retries=5)
def retention_cleanup(self) -> dict[str, Any]:
    """Run every §15b retention stage. Raises if any stage failed."""
    return asyncio.run(_retention_cleanup())


async def _retention_cleanup() -> dict[str, Any]:
    from sincere.antiabuse import api as antiabuse
    from sincere.chat import api as chat
    from sincere.identity import api as identity
    from sincere.matching import api as matching
    from sincere.shared.audit import AuditAction, record
    from sincere.shared.db import C, collection
    from sincere.shared.threshold_store import load as load_thresholds

    await _bootstrap()
    thresholds = await load_thresholds()
    now = datetime.now(UTC)

    results: dict[str, Any] = {}
    failures: list[str] = []

    async def stage(name: str, coro) -> None:
        try:
            results[name] = await coro
        except Exception as exc:
            logger.exception("retention.stage_failed", extra={"stage": name})
            failures.append(f"{name}: {exc}")
            results[name] = {"error": str(exc)}

    # --- Stage 1: 30-day grace-period hard deletes (§6) ---
    async def grace_deletes() -> dict[str, int]:
        deleted = 0
        cursor = collection(C.USERS).find(
            {"status": "grace_period", "hard_delete_after": {"$lte": now}}
        )
        async for user in cursor:
            user_id = user["_id"]
            # Order matters: purge the dependent modules' data before the account row goes,
            # or their cascade queries lose the user they key on.
            await matching.purge_user(user_id)
            await chat.purge_user_messages(user_id)
            await antiabuse.purge_user(user_id)
            # identity.hard_delete_user removes profile, photos, captures and (unless the
            # account is banned) the embedding. §18: payment records are NOT touched — they
            # are retained 5-7 years and decoupled from the cascade.
            await identity.hard_delete_user(user_id)
            deleted += 1
        return {"accounts": deleted}

    await stage("grace_period_deletes", grace_deletes())

    # --- Stage 2: 90-day post-unmatch message purge, honouring holds (§8, §18) ---
    async def message_purge() -> dict[str, int]:
        purged_matches = 0
        purged_messages = 0
        for match in await matching.matches_needing_purge(now):
            purged_messages += await chat.purge_match_messages(match["_id"])
            purged_matches += 1
        return {"matches": purged_matches, "messages": purged_messages}

    await stage("message_purge", message_purge())

    # --- Stage 3: 90-day device-signal window (§8) ---
    async def device_signals() -> dict[str, int]:
        """Enforced by a TTL index; this verifies it rather than duplicating it.

        A TTL that silently stops working looks exactly like success, which is the failure
        mode §21's "any failure alerts" is guarding against.
        """
        from datetime import timedelta

        cutoff = now - timedelta(days=thresholds.device_signal_retention_days + 1)
        overdue = await collection(C.DEVICE_SIGNALS).count_documents(
            {"created_at": {"$lt": cutoff}}
        )
        if overdue:
            raise RuntimeError(
                f"{overdue} device signals are past the "
                f"{thresholds.device_signal_retention_days}-day window — the TTL index is "
                "not purging (§18 compliance failure)"
            )
        return {"overdue": 0}

    await stage("device_signal_ttl", device_signals())

    # --- Stage 4: expired verification captures (§8: 30-day soft delete) ---
    async def captures() -> dict[str, int]:
        from sincere.shared import storage

        purged = 0
        cursor = collection(C.VERIFICATION_CAPTURES).find({"hard_delete_after": {"$lte": now}})
        async for capture in cursor:
            try:
                await storage.get_storage().delete(capture["object_key"])
            except Exception as exc:  # noqa: BLE001 — a missing object should not block the row
                logger.warning("retention.object_missing", extra={"error": str(exc)})
            await collection(C.VERIFICATION_CAPTURES).delete_one({"_id": capture["_id"]})
            purged += 1
        return {"captures": purged}

    await stage("verification_captures", captures())

    await record(AuditAction.HARD_DELETE_EXECUTED, context={"retention_cleanup": results})

    if failures:
        # §21 pages on this. Raising *after* every stage ran means one broken stage does not
        # cancel the others' legally-mandated deletions.
        logger.error("retention.cleanup_incomplete", extra={"failures": failures})
        raise RuntimeError(f"Retention cleanup incomplete: {'; '.join(failures)}")

    logger.info("retention.cleanup_complete", extra=results)
    return results


@celery_app.task(name="sincere.admin.jobs.sweep_outbox", bind=True)
def sweep_outbox(self) -> dict[str, int]:
    """Re-dispatch outbox events whose handlers failed (§14 at-least-once)."""
    return asyncio.run(_sweep())


async def _sweep() -> dict[str, int]:
    from sincere.shared.events import replay_pending

    await _bootstrap()
    replayed = await replay_pending()
    return {"replayed": replayed}
