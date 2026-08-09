"""MongoDB access for matching.

§3 rule 1: this module owns ``swipes``, ``matches`` and ``daily_batches``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

from sincere.shared.db import C, collection

# ---------------------------------------------------------------------------
# Candidate pool (§11 step 1)
# ---------------------------------------------------------------------------

async def candidate_pool(
    *,
    user_id: str,
    location: dict[str, Any],
    radius_km: int,
    opposite_gender: str,
    exclude_ids: set[str],
    active_since: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    """``$geoNear`` pool query (§11 step 1).

    Filters, in the order §11 lists them: within the user's radius, active, verified,
    opposite pool, not already swiped, not currently matched.

    **Bidirectional radius** (§11: "Both directions' radius preferences are respected — each
    candidate must also have the user inside *their* radius") is applied by the caller after
    distance is known, because a candidate's own radius is a per-document value that
    ``$geoNear`` cannot express as a static filter.

    **Discoverability vs. the FR-2.3 ratio definition.** "Active" here means *admitted and
    recently present* — ``status: active`` plus a login inside the window. It deliberately
    does NOT use ``activity.is_active_30d``, which FR-2.3 defines as "logged in **AND** made
    ≥1 swipe". That flag is the right basis for counting the admission ratio, and the wrong
    basis for a candidate pool: a newly admitted user has not swiped yet, so filtering on it
    would make every new member invisible to everyone, which means nobody can swipe them,
    which means they never become visible. A brand-new region would stay permanently empty.
    """
    pipeline: list[dict[str, Any]] = [
        {
            "$geoNear": {
                "near": location,
                "distanceField": "distance_m",
                "maxDistance": radius_km * 1000,
                "spherical": True,
                "query": {
                    "_id": {"$nin": list(exclude_ids | {user_id})},
                    "gender": opposite_gender,
                    "status": "active",
                    "activity.last_login_at": {"$gte": active_since},
                },
            }
        },
        {"$limit": limit},
        {
            "$project": {
                "gender": 1,
                "profile": 1,
                "radius_km": 1,
                "h3_region": 1,
                "created_at": 1,
                "distance_m": 1,
                "graduation": 1,
            }
        },
    ]
    return [doc async for doc in collection(C.USERS).aggregate(pipeline)]


async def swiped_target_ids(user_id: str) -> set[str]:
    """Everyone this user has already swiped — the "no repeats" guarantee (§24 simulation)."""
    targets = await collection(C.SWIPES).distinct("target_id", {"user_id": user_id})
    return set(targets)


async def matched_user_ids(user_id: str) -> set[str]:
    cursor = collection(C.MATCHES).find({"users": user_id}, {"users": 1})
    ids: set[str] = set()
    async for doc in cursor:
        ids.update(uid for uid in doc["users"] if uid != user_id)
    return ids


# ---------------------------------------------------------------------------
# Swipes
# ---------------------------------------------------------------------------

async def record_swipe(
    *, user_id: str, target_id: str, direction: str, dwell_ms: int, server_dwell_ms: int | None
) -> bool:
    """Insert a swipe. Returns False when it is a duplicate (unique index on the pair).

    The duplicate case is not an error: a client retry after a dropped response must not
    create a second swipe, and the unique index is what makes ``POST /swipes`` idempotent
    without an explicit idempotency key.
    """
    try:
        await collection(C.SWIPES).insert_one(
            {
                "_id": str(uuid4()),
                "user_id": user_id,
                "target_id": target_id,
                "direction": direction,
                "dwell_ms": dwell_ms,
                # §18: kept alongside the claim so the cross-check is auditable after the fact.
                "server_dwell_ms": server_dwell_ms,
                "created_at": datetime.now(UTC),
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def has_liked(user_id: str, target_id: str) -> bool:
    """Did ``user_id`` right-swipe ``target_id``? This is the match test."""
    doc = await collection(C.SWIPES).find_one(
        {"user_id": user_id, "target_id": target_id, "direction": "right"}
    )
    return doc is not None


async def count_swipes(user_id: str) -> int:
    return await collection(C.SWIPES).count_documents({"user_id": user_id})


async def recent_swipes(user_id: str, limit: int) -> list[dict[str, Any]]:
    """Rolling window for the FR-5.2 dwell rule."""
    cursor = (
        collection(C.SWIPES).find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    )
    return [doc async for doc in cursor]


async def liked_target_ids(user_id: str, limit: int = 100) -> list[str]:
    """Right-swiped targets, for the FR-3.6 liked-profile centroid."""
    cursor = (
        collection(C.SWIPES)
        .find({"user_id": user_id, "direction": "right"}, {"target_id": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [doc["target_id"] async for doc in cursor]


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

async def create_match(user_a: str, user_b: str, region: str | None) -> dict[str, Any]:
    match = {
        "_id": str(uuid4()),
        "users": sorted([user_a, user_b]),
        "region": region,
        "formed_at": datetime.now(UTC),
        "status": "active",
        "engagement": {"msg_count": 0, "last_msg_at": None, "avg_response_latency_s": None},
        "wemet": {"triggered_at": None, "responses": [], "next_reask_at": None},
        "unmatched_at": None,
        "messages_purge_after": None,
    }
    await collection(C.MATCHES).insert_one(match)
    return match


async def get_match(match_id: str) -> dict[str, Any] | None:
    return await collection(C.MATCHES).find_one({"_id": match_id})


async def find_match_between(user_a: str, user_b: str) -> dict[str, Any] | None:
    return await collection(C.MATCHES).find_one({"users": {"$all": [user_a, user_b]}})


async def list_matches(user_id: str) -> list[dict[str, Any]]:
    cursor = (
        collection(C.MATCHES)
        .find({"users": user_id, "status": "active"})
        .sort("formed_at", -1)
    )
    return [doc async for doc in cursor]


async def count_matches(user_id: str) -> int:
    return await collection(C.MATCHES).count_documents({"users": user_id, "status": "active"})


async def unmatch(match_id: str, retention_days: int) -> dict[str, Any] | None:
    """§8: unmatching starts the 90-day message-retention clock (DECIDED)."""
    now = datetime.now(UTC)
    return await collection(C.MATCHES).find_one_and_update(
        {"_id": match_id, "status": "active"},
        {
            "$set": {
                "status": "unmatched",
                "unmatched_at": now,
                "messages_purge_after": now + timedelta(days=retention_days),
            }
        },
        return_document=True,
    )


async def update_engagement(
    match_id: str, *, msg_count: int, last_msg_at: datetime, avg_latency_s: float | None
) -> None:
    """Written by the chat module's ``MessageSent`` reaction, via ``matching.api``."""
    await collection(C.MATCHES).update_one(
        {"_id": match_id},
        {
            "$set": {
                "engagement.msg_count": msg_count,
                "engagement.last_msg_at": last_msg_at,
                "engagement.avg_response_latency_s": avg_latency_s,
            }
        },
    )


# ---------------------------------------------------------------------------
# Daily batches (§11 step 7)
# ---------------------------------------------------------------------------

async def store_batch(
    *, user_id: str, region: str | None, batch_date: str, entries: list[dict[str, Any]]
) -> None:
    """Persist the ordered daily list. Upsert makes batch re-runs idempotent (§15)."""
    await collection(C.DAILY_BATCHES).update_one(
        {"user_id": user_id, "batch_date": batch_date},
        {
            "$set": {
                "region": region,
                "entries": entries,
                "generated_at": datetime.now(UTC),
                "consumed": [],
            }
        },
        upsert=True,
    )


async def get_batch(user_id: str, batch_date: str) -> dict[str, Any] | None:
    return await collection(C.DAILY_BATCHES).find_one(
        {"user_id": user_id, "batch_date": batch_date}
    )


async def mark_consumed(user_id: str, batch_date: str, target_id: str) -> None:
    await collection(C.DAILY_BATCHES).update_one(
        {"user_id": user_id, "batch_date": batch_date},
        {"$addToSet": {"consumed": target_id}},
    )


async def active_user_ids_in_region(region: str) -> list[str]:
    """Everyone the nightly batch must generate for, in one region (§15b, per-region parallel)."""
    return await collection(C.USERS).distinct(
        "_id", {"h3_region": region, "status": "active", "activity.is_active_30d": True}
    )


async def purge_user(user_id: str) -> dict[str, int]:
    """Deletion cascade (§6) for matching-owned data."""
    swipes = await collection(C.SWIPES).delete_many(
        {"$or": [{"user_id": user_id}, {"target_id": user_id}]}
    )
    batches = await collection(C.DAILY_BATCHES).delete_many({"user_id": user_id})
    return {"swipes": swipes.deleted_count, "batches": batches.deleted_count}
