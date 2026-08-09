"""Domain events for chat (§14).

Consumes: ``MatchFormed``, ``Unmatched``, ``HarassmentReported``, ``AccountDeletionRequested``.
Emits: ``MessageSent``, ``HarassmentReported`` (from ``service.py``).
"""

from __future__ import annotations

import logging

from sincere.chat import repository as repo
from sincere.chat import service
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.MATCH_FORMED)
async def on_match_formed(event: DomainEvent) -> None:
    """§14: matching -> chat. "Open conversation"."""
    match_id = event.payload.get("match_id")
    users = event.payload.get("users") or []
    if not match_id or not users:
        return
    await service.open_conversation(match_id, users)
    logger.info("chat.conversation_opened", extra={"match_id": match_id})


@bus.on(Event.UNMATCHED)
async def on_unmatched(event: DomainEvent) -> None:
    """§14: matching -> chat. "Start the 90-day message-retention clock".

    The clock itself lives on the match document (``messages_purge_after``), which matching
    owns and already set. Nothing is deleted here — the retention job does that on the due
    date, and only for messages without an investigation hold.
    """
    match_id = event.payload.get("match_id")
    if match_id:
        logger.info("chat.retention_clock_started", extra={"match_id": match_id})


@bus.on(Event.HARASSMENT_REPORTED)
async def on_harassment_reported(event: DomainEvent) -> None:
    """§14: chat -> chat, admin. "Retention hold; surface to review".

    Re-applying the hold here as well as in ``service.report`` is deliberate: the outbox may
    replay this event, and re-holding already-held messages is a no-op, whereas a *missed*
    hold destroys evidence when the purge runs.
    """
    match_id = event.payload.get("match_id")
    if not match_id:
        return
    held = await repo.apply_retention_hold(match_id)
    logger.info("chat.retention_hold", extra={"match_id": match_id, "messages": held})


@bus.on(Event.ACCOUNT_DELETION_REQUESTED)
async def on_account_deletion_requested(event: DomainEvent) -> None:
    """§6 cascade.

    Messages are purged at *hard delete*, not at deletion request — the account is restorable
    for 30 days and a restored user should find their conversations intact. What happens now
    is only that the user stops appearing; the retention job handles the rest.
    """
    user_id = event.payload.get("user_id")
    if user_id:
        logger.info("chat.deletion_scheduled", extra={"user_id": user_id})
