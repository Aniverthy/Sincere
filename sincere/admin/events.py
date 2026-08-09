"""Domain events for admin (§14).

Consumes: ``HarassmentReported`` — §14's row reads "chat -> chat, **admin**. Retention hold;
**surface to review**".

admin emits nothing. It is an observer of the system, not a participant in it.
"""

from __future__ import annotations

import logging

from sincere.shared.audit import AuditAction, record
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.HARASSMENT_REPORTED)
async def on_harassment_reported(event: DomainEvent) -> None:
    """Surface a report to the ops review trail.

    The retention hold itself is chat's responsibility (it owns ``messages``); admin's job is
    to make sure the report is visible and permanently recorded. §22 lists harassment
    investigations among the things whose handling must be reconstructable after the fact.
    """
    match_id = event.payload.get("match_id")
    reporter_id = event.payload.get("reporter_id")
    if not match_id:
        return

    await record(
        AuditAction.RETENTION_HOLD_APPLIED,
        actor_id=reporter_id,
        context={
            "match_id": match_id,
            "reason": event.payload.get("reason"),
            "source": "harassment_report",
        },
    )
    logger.warning(
        "admin.harassment_report_surfaced",
        extra={"match_id": match_id, "needs_review": True},
    )
