"""Celery tasks owned by matching — the nightly daily-15 batch (§15b).

§15:660 requires the batch be "per-region parallelizable"; §19 says "per-region parallel
Celery tasks; per-user pool capped (geo-query limit) before scoring; user-level feature
vectors cached". Both are why the entrypoint fans out one task per region rather than looping
every user in a single task.
"""

from __future__ import annotations

import asyncio
import logging

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    from sincere.shared import cache, db

    await db.connect()
    await cache.connect()


@celery_app.task(name="sincere.matching.jobs.generate_daily_batches", bind=True)
def generate_daily_batches(self) -> dict[str, int]:
    """Fan out one batch task per region (§15b, §19).

    §2 requires the batch complete "before delivery time for all users in a region", which is
    what the fan-out buys: regions run concurrently across the worker pool.
    """
    return asyncio.run(_fan_out())


async def _fan_out() -> dict[str, int]:
    from sincere.admission import api as admission

    await _bootstrap()
    regions = await admission.list_regions()
    for region in regions:
        generate_region_batches.delay(region)

    logger.info("matching.batch_fan_out", extra={"regions": len(regions)})
    return {"regions": len(regions)}


@celery_app.task(name="sincere.matching.jobs.generate_region_batches", bind=True, max_retries=3)
def generate_region_batches(self, region: str) -> dict[str, int]:
    """Generate every active user's daily list in one region. Idempotent (§15)."""
    return asyncio.run(_generate_region(region))


async def _generate_region(region: str) -> dict[str, int]:
    from sincere.matching import api as matching_api

    await _bootstrap()
    user_ids = await matching_api.active_user_ids_in_region(region)

    generated = 0
    empty = 0
    for user_id in user_ids:
        try:
            count = await matching_api.generate_batch(user_id)
        except Exception:
            # One user's bad data must not abort a whole region's batch — the rest of the
            # region still needs its lists before delivery time (§2).
            logger.exception("matching.batch_failed", extra={"user_id": user_id})
            continue
        if count:
            generated += 1
        else:
            empty += 1

    logger.info(
        "matching.region_batch_complete",
        extra={"region": region, "users": len(user_ids), "generated": generated, "empty": empty},
    )
    return {"users": len(user_ids), "generated": generated, "empty": empty}
