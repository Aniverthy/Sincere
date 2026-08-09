"""MongoDB access for admission.

§3 rule 1: this module owns ``queues`` and ``auctions``. The ``queues`` document is keyed by
the H3 cell itself (§8: "one doc per H3 region"), so region lookups need no secondary index.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sincere.admission.ratio import AdmissionState
from sincere.shared.db import C, collection


async def get_queue(region: str) -> dict[str, Any] | None:
    return await collection(C.QUEUES).find_one({"_id": region})


async def ensure_queue(region: str, splits: dict[str, float]) -> dict[str, Any]:
    """Create the per-hex queue document on first use (FR-2.2).

    Upsert rather than insert: a region's first two signups can race, and §15's idempotency
    requirement applies to request paths as much as to jobs.
    """
    await collection(C.QUEUES).update_one(
        {"_id": region},
        {
            "$setOnInsert": {
                "active_men": 0,
                "active_women": 0,
                "admission_state": str(AdmissionState.OPEN),
                "frozen_since": None,
                "waitlist": [],
                "slot_split": splits,
                "created_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )
    queue = await get_queue(region)
    assert queue is not None
    return queue


async def set_counts(region: str, *, active_men: int, active_women: int) -> None:
    """Write authoritative counts. Used by the hourly full recount (§19 drift correction)."""
    await collection(C.QUEUES).update_one(
        {"_id": region},
        {"$set": {"active_men": active_men, "active_women": active_women}},
    )


async def adjust_count(region: str, *, gender: str, delta: int) -> dict[str, Any] | None:
    """Event-maintained counter increment (§19: "counter-maintained, not recounted")."""
    field = "active_men" if gender == "male" else "active_women"
    return await collection(C.QUEUES).find_one_and_update(
        {"_id": region}, {"$inc": {field: delta}}, return_document=True
    )


async def set_admission_state(region: str, state: AdmissionState) -> None:
    updates: dict[str, Any] = {"admission_state": str(state)}
    updates["frozen_since"] = datetime.now(UTC) if state is AdmissionState.FROZEN else None
    await collection(C.QUEUES).update_one({"_id": region}, {"$set": updates})


# ---------------------------------------------------------------------------
# Waitlist (FR-2.10)
# ---------------------------------------------------------------------------

async def add_to_waitlist(
    region: str, *, user_id: str, tier: str, engagement_priority: float
) -> None:
    """Idempotent: the filter refuses to add a user already on this waitlist."""
    await collection(C.QUEUES).update_one(
        {"_id": region, "waitlist.user_id": {"$ne": user_id}},
        {
            "$push": {
                "waitlist": {
                    "user_id": user_id,
                    "tier": tier,
                    "joined_at": datetime.now(UTC),
                    "engagement_priority": engagement_priority,
                }
            }
        },
    )


async def remove_from_waitlist(region: str, user_id: str) -> None:
    await collection(C.QUEUES).update_one(
        {"_id": region}, {"$pull": {"waitlist": {"user_id": user_id}}}
    )


async def update_waitlist_priority(region: str, user_id: str, priority: float) -> None:
    await collection(C.QUEUES).update_one(
        {"_id": region, "waitlist.user_id": user_id},
        {"$set": {"waitlist.$.engagement_priority": priority}},
    )


async def promote_tier(region: str, user_id: str, tier: str) -> None:
    """Move a waitlisted user into the paid tier after a successful payment (FR-2.8)."""
    await collection(C.QUEUES).update_one(
        {"_id": region, "waitlist.user_id": user_id},
        {"$set": {"waitlist.$.tier": tier}},
    )


async def list_regions() -> list[str]:
    return await collection(C.QUEUES).distinct("_id")


async def all_queues() -> list[dict[str, Any]]:
    return [doc async for doc in collection(C.QUEUES).find({})]


# ---------------------------------------------------------------------------
# Auctions (FR-2.9, §15a)
# ---------------------------------------------------------------------------

async def upsert_auction(
    *, region: str, window_start: datetime, window_end: datetime, slots: int, min_bid: int
) -> dict[str, Any]:
    await collection(C.AUCTIONS).update_one(
        {"region": region, "window_end": window_end},
        {
            "$setOnInsert": {
                "window_start": window_start,
                "slots": slots,
                "min_bid_paise": min_bid,
                "status": "open",
                "bids": [],
                "winners": [],
                "clearing_bid_paise": None,
                "settled_at": None,
                "created_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )
    doc = await collection(C.AUCTIONS).find_one({"region": region, "window_end": window_end})
    assert doc is not None
    return doc


async def get_auction(region: str, window_end: datetime) -> dict[str, Any] | None:
    return await collection(C.AUCTIONS).find_one({"region": region, "window_end": window_end})


async def latest_settled_auction(region: str) -> dict[str, Any] | None:
    cursor = (
        collection(C.AUCTIONS)
        .find({"region": region, "status": "settled"})
        .sort("window_end", -1)
    )
    async for doc in cursor:
        return doc
    return None


async def settle_auction(
    *,
    region: str,
    window_end: datetime,
    winners: list[dict[str, Any]],
    clearing_bid: int | None,
    losers: list[dict[str, Any]],
) -> None:
    """Write the settlement (§15a: "settlement writes to MongoDB at close").

    The filter includes ``status: open`` so a re-run of the close job cannot settle twice —
    §15's idempotency requirement, and the reason a duplicate charge cannot happen.
    """
    await collection(C.AUCTIONS).update_one(
        {"region": region, "window_end": window_end, "status": "open"},
        {
            "$set": {
                "status": "settled",
                "winners": winners,
                "losers": losers,
                "clearing_bid_paise": clearing_bid,
                "settled_at": datetime.now(UTC),
            }
        },
    )


async def open_auctions(now: datetime) -> list[dict[str, Any]]:
    cursor = collection(C.AUCTIONS).find({"status": "open", "window_end": {"$lte": now}})
    return [doc async for doc in cursor]
