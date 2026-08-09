"""MongoDB access for antiabuse.

§3 rule 1: this module owns ``device_signals``. The warning ledger lives on ``users.warnings``
(§8), which identity owns — so warnings are *reported* via the ``WarningIssued`` event and
identity does the write. This module keeps its own ledger document for the escalation state
it needs to reason about (occasion timing, acknowledgement).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sincere.shared.db import C, collection

#: Escalation state per user. Stored in ``device_signals`` under a reserved event type so the
#: module owns its own collection rather than reaching into another module's (§3 rule 1).
LEDGER_EVENT = "__warning_ledger__"


async def get_ledger(user_id: str) -> dict[str, Any] | None:
    return await collection(C.DEVICE_SIGNALS).find_one(
        {"user_id": user_id, "event_type": LEDGER_EVENT}
    )


async def record_warning(
    *, user_id: str, occasion_no: int, ratio: float, reason: str
) -> None:
    now = datetime.now(UTC)
    await collection(C.DEVICE_SIGNALS).update_one(
        {"user_id": user_id, "event_type": LEDGER_EVENT},
        {
            "$set": {
                "warning_count": occasion_no,
                "last_warning_at": now,
                "last_ratio": ratio,
                "last_reason": reason,
                # Refreshed so the 90-day TTL measures from the most recent warning, not the
                # first — an escalating pattern must not age out mid-escalation.
                "created_at": now,
            },
            "$push": {
                "history": {"occasion_no": occasion_no, "at": now, "ratio": ratio, "reason": reason}
            },
            "$setOnInsert": {"_id": str(uuid4()), "acknowledged_through": 0},
        },
        upsert=True,
    )


async def acknowledge(user_id: str) -> None:
    ledger = await get_ledger(user_id)
    if ledger is None:
        return
    await collection(C.DEVICE_SIGNALS).update_one(
        {"_id": ledger["_id"]},
        {"$set": {"acknowledged_through": ledger.get("warning_count", 0)}},
    )


async def mark_banned(user_id: str, *, reason: str) -> None:
    await collection(C.DEVICE_SIGNALS).update_one(
        {"user_id": user_id, "event_type": LEDGER_EVENT},
        {
            "$set": {
                "banned": True,
                "banned_at": datetime.now(UTC),
                "ban_reason": reason,
                "created_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )


async def record_device_signal(
    *, user_id: str, fingerprint: str | None, ip: str | None, event_type: str
) -> None:
    """FR-5.4. TTL index on ``created_at`` enforces the §8 90-day rolling window."""
    await collection(C.DEVICE_SIGNALS).insert_one(
        {
            "_id": str(uuid4()),
            "user_id": user_id,
            "fingerprint": fingerprint,
            "ip": ip,
            "event_type": event_type,
            "created_at": datetime.now(UTC),
        }
    )


async def purge_user(user_id: str) -> int:
    """Deletion cascade (§6)."""
    result = await collection(C.DEVICE_SIGNALS).delete_many({"user_id": user_id})
    return int(result.deleted_count)
