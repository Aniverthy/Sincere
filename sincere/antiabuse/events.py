"""Domain events for antiabuse (§14).

Consumes: ``SwipeRecorded`` (dwell-rule evaluation), ``AccountDeletionRequested``.
Emits: ``WarningIssued``, ``UserBanned`` (from ``service.py``).
"""

from __future__ import annotations

import logging

from sincere.antiabuse import repository as repo
from sincere.antiabuse import service
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.SWIPE_RECORDED)
async def on_swipe_recorded(event: DomainEvent) -> None:
    """§14: matching -> antiabuse. "Dwell-rule evaluation".

    Runs on the event rather than inline in ``POST /swipes`` because §19 budgets p95 < 150 ms
    for swipe writes and requires "event fan-out async" — evaluating a 100-swipe window on the
    request path would blow that budget.

    Right-swipes only: the FR-5.2 rule has no opinion about left-swipes, so evaluating on them
    would be wasted work on the hottest path in the product.
    """
    if event.payload.get("direction") != "right":
        return

    user_id = event.payload.get("user_id")
    if not user_id:
        return

    result = await service.evaluate_user(user_id)
    if result.get("tripped"):
        logger.info(
            "antiabuse.rule_tripped",
            extra={"user_id": user_id, "action": result.get("action")},
        )


@bus.on(Event.ACCOUNT_DELETION_REQUESTED)
async def on_account_deletion_requested(event: DomainEvent) -> None:
    """§6 cascade for antiabuse-owned data.

    Note the deliberate asymmetry with a ban: a *deleted* account's signals go, but a *banned*
    account keeps its identity embedding (§6) so re-signup is caught. Different rules, because
    deletion is a right and a ban is an enforcement.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    removed = await repo.purge_user(user_id)
    logger.info("antiabuse.signals_purged", extra={"user_id": user_id, "count": removed})
