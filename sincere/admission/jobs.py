"""Celery tasks owned by admission — three of the seven §15b jobs.

* ``close_auction`` — daily, at the fixed window end (FR-2.9). **Critical queue**: §21 pages
  on failure, because an unsettled auction means bidders charged but not admitted.
* ``recompute_all_ratios`` — hourly sweep, the §19 drift-correction backstop behind the
  event-maintained counters.
* ``flag_churn_risk`` — daily scan (§13: heuristic at launch, women prioritized).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _bootstrap() -> None:
    from sincere.shared import cache, db

    await db.connect()
    await cache.connect()


@celery_app.task(name="sincere.admission.jobs.close_auction", bind=True, max_retries=5)
def close_auction(self) -> dict[str, object]:
    """Settle every open auction whose window has ended (FR-2.9, §15a)."""
    return asyncio.run(_close_auction())


async def _close_auction() -> dict[str, object]:
    from sincere.admission import api as admission_api
    from sincere.admission import repository as repo

    await _bootstrap()
    now = datetime.now(UTC)
    results = []
    for stored in await repo.open_auctions(now):
        try:
            results.append(
                await admission_api.close_auction(stored["region"], stored["window_end"])
            )
        except Exception:
            # One region failing must not leave the others unsettled — §15's per-region
            # parallelizability applies to failure isolation too. Celery retries the task.
            logger.exception("auction.close_failed", extra={"region": stored["region"]})
            raise

    logger.info("auction.close_sweep", extra={"regions": len(results)})
    return {"settled": len(results), "results": results}


@celery_app.task(name="sincere.admission.jobs.recompute_all_ratios", bind=True)
def recompute_all_ratios(self) -> dict[str, int]:
    """§19: "hourly full recount as drift correction" behind the event-maintained counters."""
    return asyncio.run(_recompute_all_ratios())


async def _recompute_all_ratios() -> dict[str, int]:
    from sincere.admission import api as admission_api

    await _bootstrap()
    regions = await admission_api.list_regions()
    drifted = 0

    for region in regions:
        before, _ = await admission_api.get_region_state(region)
        after = await admission_api.recount_region(region)
        if (before.active_men, before.active_women) != (after.active_men, after.active_women):
            drifted += 1
            logger.warning(
                "admission.counter_drift_corrected",
                extra={
                    "region": region,
                    "before_men": before.active_men,
                    "before_women": before.active_women,
                    "after_men": after.active_men,
                    "after_women": after.active_women,
                },
            )
        # A recovered ratio should admit immediately, not wait for the next signup.
        await admission_api.drain_waitlist(region)

    logger.info("admission.ratio_sweep", extra={"regions": len(regions), "drifted": drifted})
    return {"regions": len(regions), "drifted": drifted}


@celery_app.task(name="sincere.admission.jobs.flag_churn_risk", bind=True)
def flag_churn_risk(self) -> dict[str, int]:
    """§13 churn-risk flagging — heuristic at launch, model candidate later.

    Signals: "declining sessions/matches/message frequency, growing response latency".
    §21 treats a spike in flagged women as a leading indicator of ratio trouble, because
    women going inactive is precisely what trips the FR-2.4 freeze.
    """
    return asyncio.run(_flag_churn_risk())


async def _flag_churn_risk() -> dict[str, int]:
    from sincere.identity import api as identity
    from sincere.shared.db import C, collection
    from sincere.shared.threshold_store import load as load_thresholds

    await _bootstrap()
    thresholds = await load_thresholds()

    # "At risk" = still nominally active, but has not swiped in over half the activity
    # window. Half rather than the full window because the point is to intervene *before*
    # they drop out of the ratio denominator, not to count them after.
    half_window = datetime.now(UTC) - timedelta(days=thresholds.active_window_days // 2)

    flagged_women = 0
    flagged_men = 0
    cursor = collection(C.USERS).find(
        {
            "status": "active",
            "activity.is_active_30d": True,
            "$or": [
                {"activity.last_swipe_at": {"$lt": half_window}},
                {"activity.last_swipe_at": None},
            ],
        }
    )
    async for user in cursor:
        await collection(C.USERS).update_one(
            {"_id": user["_id"]},
            {"$set": {"churn_risk": {"flagged_at": datetime.now(UTC), "reason": "swipe_lapse"}}},
        )
        if user.get("gender") == "female":
            flagged_women += 1
        else:
            flagged_men += 1

        # Re-evaluate FR-2.3 while we are here: a user past the full window is no longer
        # active and must leave the ratio denominators.
        await identity.recompute_active_flag(user["_id"], thresholds.active_window_days)

    logger.info(
        "admission.churn_risk_scan",
        extra={"flagged_women": flagged_women, "flagged_men": flagged_men},
    )
    return {"flagged_women": flagged_women, "flagged_men": flagged_men}
