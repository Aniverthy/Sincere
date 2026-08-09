"""Celery tasks owned by monetization — subscription expiry.

Not one of the seven §15b jobs, but required by FR-6.1: a subscription that has passed its
renewal date must stop granting entitlement, or Pro would be permanent after one payment.

FR-6.4 is the guardrail here: expiry drops the user to the **free tier**, which still carries
15 matches a day. Expiry never removes access to the product.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sincere.monetization.jobs.expire_subscriptions", bind=True)
def expire_subscriptions(self) -> dict[str, int]:
    return asyncio.run(_expire())


async def _expire() -> dict[str, int]:
    from sincere.monetization import repository as repo
    from sincere.shared import cache, db

    await db.connect()
    await cache.connect()

    expired = 0
    for sub in await repo.expired_subscriptions(datetime.now(UTC)):
        await repo.mark_expired(sub["user_id"])
        expired += 1

    if expired:
        logger.info("subscription.expired_batch", extra={"count": expired})
    return {"expired": expired}
