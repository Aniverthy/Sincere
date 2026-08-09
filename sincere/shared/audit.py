"""Audit log — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §22 requires an **append-only audit log in a separate
store/collection**, and §2 (Auditability) states the reason plainly: "fairness claims must be
defensible". Six categories are named:

* admission decisions — **with the ratio inputs as they stood at decision time**
* review decisions — with score agreement (feeds threshold retuning, FR-1.7)
* warnings and bans
* deletion-cascade steps
* threshold config changes — with actor and before/after (§18)
* auction settlements

Append-only is enforced by convention plus the absence of any update or delete helper in this
module. There is deliberately no ``update_audit`` function.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditAction(StrEnum):
    """The auditable actions of §22."""

    # Admission (recorded with the ratio inputs at decision time)
    ADMISSION_GRANTED = "admission.granted"
    ADMISSION_WAITLISTED = "admission.waitlisted"
    ADMISSION_FROZEN = "admission.frozen"
    ADMISSION_RESUMED = "admission.resumed"

    # Identity review (FR-1.7 — agreement logging feeds threshold retuning)
    REVIEW_DECISION = "review.decision"
    VERIFICATION_AUTO_APPROVED = "verification.auto_approved"
    VERIFICATION_AUTO_REJECTED = "verification.auto_rejected"
    VERIFICATION_QUEUED_FOR_REVIEW = "verification.queued_for_review"

    # Anti-abuse
    WARNING_ISSUED = "antiabuse.warning_issued"
    USER_BANNED = "antiabuse.user_banned"

    # Retention & deletion cascade (§6)
    DELETION_REQUESTED = "retention.deletion_requested"
    DELETION_RESTORED = "retention.restored"
    HARD_DELETE_EXECUTED = "retention.hard_delete_executed"
    MESSAGES_PURGED = "retention.messages_purged"
    RETENTION_HOLD_APPLIED = "retention.hold_applied"

    # Config (§18: actor + before/after)
    THRESHOLD_CHANGED = "config.threshold_changed"

    # Auction settlement (§15a)
    AUCTION_SETTLED = "auction.settled"
    AUCTION_REFUNDED = "auction.refunded"


async def record(
    action: AuditAction,
    *,
    actor_id: str | None = None,
    subject_id: str | None = None,
    region: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Append one immutable audit entry. Returns its id.

    ``context`` is where decision *inputs* belong — §22 requires admission decisions to carry
    "the ratio inputs at decision time" so a fairness claim can be reconstructed later, not
    merely asserted.

    Audit writes are best-effort with respect to the caller: a failure is logged at ERROR and
    re-raised only in production, where a missing audit record is itself a compliance problem.
    """
    entry: dict[str, Any] = {
        "_id": str(uuid4()),
        "action": str(action),
        "at": datetime.now(UTC),
        "actor_id": actor_id,
        "subject_id": subject_id,
        "region": region,
        "before": before,
        "after": after,
        "context": context or {},
    }

    from sincere.shared.config import get_settings
    from sincere.shared.db import C, collection

    try:
        await collection(C.AUDIT_LOG).insert_one(entry)
    except Exception:
        logger.exception("audit.write_failed", extra={"action": str(action)})
        if get_settings().environment == "production":
            raise
    return entry["_id"]


async def record_admission_decision(
    *,
    user_id: str,
    region: str,
    granted: bool,
    tier: str | None,
    active_men: int,
    active_women: int,
    ceiling: float,
    admission_state: str,
) -> str:
    """Convenience wrapper carrying the full ratio snapshot demanded by §22."""
    return await record(
        AuditAction.ADMISSION_GRANTED if granted else AuditAction.ADMISSION_WAITLISTED,
        subject_id=user_id,
        region=region,
        context={
            "tier": tier,
            "active_men": active_men,
            "active_women": active_women,
            "ceiling": ceiling,
            "admission_state": admission_state,
            "ratio": (active_men / active_women) if active_women else None,
        },
    )
