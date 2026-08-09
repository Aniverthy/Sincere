"""Domain events emitted and consumed by identity (§14).

Emits: ``UserVerified``, ``AccountDeletionRequested``.
Consumes: ``WarningIssued``, ``UserBanned`` (ledger update — §14's identity row).

Handlers must be idempotent: the outbox replays on failure (§14 at-least-once).
"""

from __future__ import annotations

import logging

from sincere.identity import repository as repo
from sincere.identity.schemas import UserStatus
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.WARNING_ISSUED)
async def on_warning_issued(event: DomainEvent) -> None:
    """§14: antiabuse -> identity, "ledger update".

    The warning ledger lives on ``users.warnings`` (§8), which identity owns, so antiabuse
    reports the warning as an event rather than writing another module's collection
    (§3 rule 1).

    Idempotent through ``occasion_no``: replaying the same warning does not add a second entry,
    which matters because three entries mean a ban (FR-5.3).
    """
    user_id = event.payload.get("user_id")
    occasion_no = event.payload.get("occasion_no")
    issued_at = event.payload.get("at")
    if not user_id or occasion_no is None:
        return

    from sincere.shared.db import C, collection

    result = await collection(C.USERS).update_one(
        {"_id": user_id, "warnings.occasion_no": {"$ne": occasion_no}},
        {"$push": {"warnings": {"at": issued_at, "occasion_no": occasion_no}}},
    )
    if result.modified_count:
        logger.info(
            "identity.warning_recorded",
            extra={"user_id": user_id, "occasion_no": occasion_no},
        )


@bus.on(Event.USER_BANNED)
async def on_user_banned(event: DomainEvent) -> None:
    """§14: antiabuse -> identity. Set the terminal status and revoke every session.

    §6: the ban is a terminal lifecycle node, and the user's embedding is deliberately
    retained so a re-signup trips the FR-1.4 duplicate check.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    user = await repo.get_user(user_id)
    if user is None or user["status"] == str(UserStatus.BANNED):
        return  # idempotent

    await repo.set_status(user_id, UserStatus.BANNED)
    await repo.revoke_all_user_tokens(user_id)
    logger.info("identity.user_banned", extra={"user_id": user_id})
