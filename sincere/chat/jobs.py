"""Celery tasks owned by chat — the 90-day post-unmatch message purge (§8, §15b).

§15b: "90-day chat purge post-unmatch (**honoring investigation holds**)". §21: "Any failure
alerts — legally-mandated deletions". This runs on the critical queue for that reason.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sincere.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sincere.chat.jobs.purge_unmatched_messages", bind=True, max_retries=5)
def purge_unmatched_messages(self) -> dict[str, int]:
    """Delete messages from conversations whose 90-day clock has expired."""
    return asyncio.run(_purge())


async def _purge() -> dict[str, int]:
    from sincere.chat import api as chat_api
    from sincere.matching import api as matching
    from sincere.shared import cache, db
    from sincere.shared.audit import AuditAction, record

    await db.connect()
    await cache.connect()

    now = datetime.now(UTC)
    due = await matching.matches_needing_purge(now)

    purged_messages = 0
    purged_matches = 0
    for match in due:
        # purge_match_messages leaves held messages behind, so a conversation under
        # investigation reports fewer deletions than it has messages — that is correct.
        deleted = await chat_api.purge_match_messages(match["_id"])
        purged_messages += deleted
        purged_matches += 1

    if purged_matches:
        await record(
            AuditAction.MESSAGES_PURGED,
            context={"matches": purged_matches, "messages": purged_messages},
        )

    logger.info(
        "retention.messages_purged",
        extra={"matches": purged_matches, "messages": purged_messages},
    )
    return {"matches": purged_matches, "messages": purged_messages}
