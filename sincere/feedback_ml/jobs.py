"""Celery tasks owned by feedback_ml — two of the seven §15b jobs.

* ``schedule_wemet_prompts`` — "continuous trigger checks + 1-2-week re-ask timers" (FR-4.3)
* ``retrain_models`` — "weekly/monthly" batch retraining, holdout-gated (FR-4.4, §13)
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


@celery_app.task(name="sincere.feedback_ml.jobs.schedule_wemet_prompts", bind=True)
def schedule_wemet_prompts(self) -> dict[str, int]:
    """FR-4.3 prompt scheduler. Idempotent — a match already prompted is skipped."""
    return asyncio.run(_schedule())


async def _schedule() -> dict[str, int]:
    from sincere.feedback_ml import api as feedback_api

    await _bootstrap()
    return await feedback_api.run_scheduler()


@celery_app.task(name="sincere.feedback_ml.jobs.retrain_models", bind=True, max_retries=2)
def retrain_models(self) -> dict[str, object]:
    """§13 batch retrain.

    A failed holdout is **not** a task failure — §13 says "Keep current model", which is a
    successful outcome of the gate doing its job. Only an actual error retries.
    """
    return asyncio.run(_retrain())


async def _retrain() -> dict[str, object]:
    from sincere.feedback_ml import api as feedback_api

    await _bootstrap()
    result = await feedback_api.retrain()

    if result.get("promoted"):
        logger.info("training.job_promoted", extra=result)
    else:
        logger.info("training.job_kept_current_model", extra=result)
    return result
