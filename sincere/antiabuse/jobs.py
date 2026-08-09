"""Celery tasks owned by antiabuse.

The 90-day device-signal purge (§8, §15b) is enforced by a **TTL index** rather than a job —
see ``sincere/shared/db.py``. This task exists as the audit-visible confirmation that the TTL
is actually working, because §21 alerts on retention-job success and a silently broken TTL
would otherwise look like success.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sincere.antiabuse.jobs.verify_signal_retention", bind=True)
def verify_signal_retention(self) -> dict[str, int]:
    """Confirm no device signal has outlived the §8 90-day window."""
    return asyncio.run(_verify())


async def _verify() -> dict[str, int]:
    from sincere.shared import cache, db
    from sincere.shared.db import C, collection
    from sincere.shared.threshold_store import load as load_thresholds

    await db.connect()
    await cache.connect()
    thresholds = await load_thresholds()

    # A day of slack: MongoDB's TTL monitor runs every 60s, so documents can briefly outlive
    # their expiry. Anything older than window+1day means the index is not doing its job.
    cutoff = datetime.now(UTC) - timedelta(days=thresholds.device_signal_retention_days + 1)
    overdue = await collection(C.DEVICE_SIGNALS).count_documents({"created_at": {"$lt": cutoff}})

    if overdue:
        logger.error(
            "retention.device_signals_overdue — the TTL index is not purging. §18 requires a "
            "90-day rolling window; this is a compliance failure, not a performance issue.",
            extra={"overdue": overdue, "cutoff": cutoff.isoformat()},
        )
    else:
        logger.info("retention.device_signals_ok")

    return {"overdue": overdue}
