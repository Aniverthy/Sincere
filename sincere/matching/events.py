"""Domain events for matching (§14).

Emits: ``SwipeRecorded``, ``MatchFormed``, ``Unmatched`` (from ``service.py``).
Consumes: ``UserActivated``, ``MessageSent``, ``UserBanned``, ``AccountDeletionRequested``.
"""

from __future__ import annotations

import logging

from sincere.matching import api as matching_api
from sincere.shared import cache
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.USER_ACTIVATED)
async def on_user_activated(event: DomainEvent) -> None:
    """§14: admission -> matching. "Include in next scoring batch; start freshness boost".

    Generating immediately rather than waiting for the nightly job matters for the product:
    someone admitted at noon should not stare at an empty Home screen until 3am.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    count = await matching_api.generate_batch(user_id)
    logger.info("matching.batch_on_activation", extra={"user_id": user_id, "count": count})


@bus.on(Event.MESSAGE_SENT)
async def on_message_sent(event: DomainEvent) -> None:
    """§14: chat -> matching. "Engagement aggregates" feeding the §12 ``engagement_score``."""
    match_id = event.payload.get("match_id")
    if not match_id:
        return

    await matching_api.update_engagement(
        match_id,
        msg_count=int(event.payload.get("msg_count", 0)),
        last_msg_at=event.payload["sent_at"],
        avg_latency_s=event.payload.get("avg_response_latency_s"),
    )


@bus.on(Event.USER_BANNED)
async def on_user_banned(event: DomainEvent) -> None:
    """A banned user leaves every candidate pool.

    The pool query already filters on ``status: active``, so this only clears the *cached*
    batches that were generated before the ban — without it a banned profile would keep
    appearing in other people's Home screens until the next nightly run.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return
    await cache.invalidate(cache.Keys.user_features(user_id))


@bus.on(Event.ACCOUNT_DELETION_REQUESTED)
async def on_account_deletion_requested(event: DomainEvent) -> None:
    """§6: "immediate hide + removal from all pools/queues".

    Swipes and batches are purged by the retention job at hard-delete time; what must happen
    *immediately* is that the user stops appearing to others, which the ``status`` change plus
    this cache invalidation accomplish.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return
    await cache.invalidate(cache.Keys.user_features(user_id))
    logger.info("matching.hidden_for_deletion", extra={"user_id": user_id})
