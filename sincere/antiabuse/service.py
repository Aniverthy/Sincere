"""Anti-abuse business logic (FR-5.1-5.4).

A **separate track from identity's bot-risk routing** by design (FR-5.3, §3): bot-risk decides
whether an account is real at signup; this decides whether a real account is behaving. They
never share a threshold or a ledger.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sincere.antiabuse import detection
from sincere.antiabuse import repository as repo
from sincere.identity import api as identity
from sincere.matching import api as matching
from sincere.shared.audit import AuditAction, record
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)


async def evaluate_user(user_id: str) -> dict[str, Any]:
    """Run the FR-5.2 dwell rule for one user and escalate if it trips.

    Idempotent within an occasion window: a second trip inside
    ``warning_separate_occasion_hours`` records no new warning (FR-5.3), so the outbox
    replaying a ``SwipeRecorded`` event cannot manufacture a ban.
    """
    thresholds = await load_thresholds()

    swipes = await matching.recent_swipes(user_id, thresholds.dwell_window_swipes)
    verdict = detection.evaluate_window(
        swipes,
        dwell_threshold_ms=thresholds.dwell_threshold_ms,
        dwell_ratio=thresholds.dwell_ratio,
        min_swipes=thresholds.dwell_min_swipes_to_evaluate,
    )

    if not verdict.tripped:
        return {"tripped": False, "evaluated": verdict.evaluated, "ratio": verdict.ratio}

    ledger = await repo.get_ledger(user_id)
    last_at = ledger.get("last_warning_at") if ledger else None
    count = int((ledger or {}).get("warning_count", 0))

    if not detection.is_separate_occasion(
        last_at, datetime.now(UTC), thresholds.warning_separate_occasion_hours
    ):
        logger.debug("antiabuse.same_occasion_suppressed", extra={"user_id": user_id})
        return {"tripped": True, "action": "suppressed_same_occasion", "warning_count": count}

    action = detection.next_action(count, thresholds.warnings_before_ban)
    occasion_no = count + 1

    await repo.record_warning(
        user_id=user_id,
        occasion_no=occasion_no,
        ratio=verdict.ratio,
        reason=verdict.reason,
    )

    await bus.emit(
        Event.WARNING_ISSUED,
        {
            "user_id": user_id,
            "occasion_no": occasion_no,
            "at": datetime.now(UTC).isoformat(),
            "reason": verdict.reason,
        },
    )
    await record(
        AuditAction.WARNING_ISSUED,
        subject_id=user_id,
        context={
            "occasion_no": occasion_no,
            "ratio": verdict.ratio,
            "fast_right_swipes": verdict.fast_right_swipes,
            "right_swipes": verdict.right_swipes,
        },
    )

    if action == "ban":
        await ban_user(user_id, reason=verdict.reason, occasion_no=occasion_no)
        return {"tripped": True, "action": "ban", "warning_count": occasion_no}

    logger.info(
        "antiabuse.warning_issued",
        extra={"user_id": user_id, "occasion_no": occasion_no, "ratio": verdict.ratio},
    )
    return {
        "tripped": True,
        "action": "warn",
        "warning_count": occasion_no,
        "message": detection.warning_message(occasion_no, thresholds.warnings_before_ban),
    }


async def ban_user(user_id: str, *, reason: str, occasion_no: int) -> None:
    """FR-5.3 terminal step.

    §6: the ban is a terminal lifecycle node and **the user's embedding is retained** so a
    re-signup trips the FR-1.4 duplicate check. identity honours that in ``hard_delete``.
    """
    await repo.mark_banned(user_id, reason=reason)
    await identity.mark_banned(user_id)

    await bus.emit(
        Event.USER_BANNED,
        {"user_id": user_id, "reason": reason, "occasion_no": occasion_no},
    )
    await record(
        AuditAction.USER_BANNED,
        subject_id=user_id,
        context={"reason": reason, "occasion_no": occasion_no, "track": "dwell_time_abuse"},
    )
    logger.warning("antiabuse.user_banned", extra={"user_id": user_id, "reason": reason})


async def pending_warning(user_id: str) -> dict[str, Any] | None:
    """The warning the client should show as an interstitial, if any (§4).

    Acknowledgement is required so a warning cannot be missed — FR-5.3's escalation is only
    fair if the user actually saw the earlier steps.
    """
    thresholds = await load_thresholds()
    ledger = await repo.get_ledger(user_id)
    if not ledger or ledger.get("acknowledged_through", 0) >= ledger.get("warning_count", 0):
        return None

    occasion_no = int(ledger["warning_count"])
    return {
        "occasion_no": occasion_no,
        "of": thresholds.warnings_before_ban,
        "message": detection.warning_message(occasion_no, thresholds.warnings_before_ban),
        "issued_at": ledger.get("last_warning_at"),
    }


async def acknowledge_warning(user_id: str) -> None:
    await repo.acknowledge(user_id)


async def record_device_signal(
    *, user_id: str, fingerprint: str | None, ip: str | None, event_type: str
) -> None:
    """FR-5.4 behavioural/device signals. TTL-purged after 90 days (§8)."""
    await repo.record_device_signal(
        user_id=user_id, fingerprint=fingerprint, ip=ip, event_type=event_type
    )
