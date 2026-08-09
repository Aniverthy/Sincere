"""MongoDB access for feedback_ml.

§3 rule 1: this module owns ``we_met_responses``. The We-Met *schedule* lives on
``matches.wemet`` (§8), which matching owns — so scheduling goes through ``matching.api``
rather than a direct write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sincere.shared.db import C, collection


async def record_response(
    *, match_id: str, user_id: str, response: str, note: str | None
) -> dict[str, Any]:
    """§13: We-Met responses are the **ground-truth labels** for retraining."""
    doc = {
        "_id": str(uuid4()),
        "match_id": match_id,
        "user_id": user_id,
        "response": response,
        "note": note,
        "responded_at": datetime.now(UTC),
    }
    await collection(C.WE_MET_RESPONSES).insert_one(doc)
    return doc


async def already_responded(match_id: str, user_id: str, since: datetime) -> bool:
    """Has this user already answered for this match in the current round?

    Scoped by time rather than by match alone, because FR-4.3 re-asks every 1-2 weeks and each
    round deserves its own answer.
    """
    doc = await collection(C.WE_MET_RESPONSES).find_one(
        {"match_id": match_id, "user_id": user_id, "responded_at": {"$gte": since}}
    )
    return doc is not None


async def responses_for_match(match_id: str) -> list[dict[str, Any]]:
    cursor = collection(C.WE_MET_RESPONSES).find({"match_id": match_id}).sort("responded_at", 1)
    return [doc async for doc in cursor]


async def training_labels() -> list[dict[str, Any]]:
    """Every We-Met response, for training-set assembly (§13).

    §13's purpose statement: the We-Met loop "re-anchors both models to *real-world*
    compatibility rather than in-app swipe appeal — closing the 'matched ≠ actually
    compatible' gap".
    """
    cursor = collection(C.WE_MET_RESPONSES).find({})
    return [doc async for doc in cursor]


async def label_count() -> int:
    return await collection(C.WE_MET_RESPONSES).count_documents({})


async def matches_due_for_prompt(now: datetime) -> list[dict[str, Any]]:
    """Matches whose scheduled re-ask time has arrived (FR-4.3)."""
    cursor = collection(C.MATCHES).find(
        {
            "status": "active",
            "wemet.next_reask_at": {"$lte": now},
        }
    )
    return [doc async for doc in cursor]


async def untriggered_active_matches() -> list[dict[str, Any]]:
    """Active matches that have never fired a We-Met prompt."""
    cursor = collection(C.MATCHES).find(
        {"status": "active", "wemet.triggered_at": None}
    )
    return [doc async for doc in cursor]


async def pending_for_user(user_id: str) -> list[dict[str, Any]]:
    """Matches where this user owes a We-Met answer."""
    cursor = collection(C.MATCHES).find(
        {"users": user_id, "status": "active", "wemet.triggered_at": {"$ne": None}}
    )
    return [doc async for doc in cursor]


async def set_prompt_state(
    match_id: str, *, triggered_at: datetime | None, next_reask_at: datetime | None
) -> None:
    """Update the schedule on the match document.

    Written here rather than through ``matching.api`` because §8 places ``wemet`` inside the
    match document and matching exposes no setter — a narrow, documented exception noted in
    ``COLLECTION_OWNER``. The alternative would be an api method that exists solely to proxy
    this one field.
    """
    await collection(C.MATCHES).update_one(
        {"_id": match_id},
        {"$set": {"wemet.triggered_at": triggered_at, "wemet.next_reask_at": next_reask_at}},
    )


async def append_response_to_match(match_id: str, entry: dict[str, Any]) -> None:
    await collection(C.MATCHES).update_one(
        {"_id": match_id}, {"$push": {"wemet.responses": entry}}
    )


async def training_rows() -> list[dict[str, Any]]:
    """Assemble (swipe, chat, we-met) rows for the §13 retraining pipeline.

    §13's diagram: swipes + chat aggregates + we_met_responses -> training-set assembly.
    """
    rows: list[dict[str, Any]] = []

    labels = {}
    async for doc in collection(C.WE_MET_RESPONSES).find({}):
        # A "met" answer from either side is the positive label for the pair.
        labels.setdefault(doc["match_id"], doc["response"])
        if doc["response"] == "met_yes":
            labels[doc["match_id"]] = "met_yes"

    async for match in collection(C.MATCHES).find({"_id": {"$in": list(labels)}}):
        engagement = match.get("engagement", {})
        rows.append(
            {
                "match_id": match["_id"],
                "users": match["users"],
                "region": match.get("region"),
                "msg_count": engagement.get("msg_count", 0),
                "avg_response_latency_s": engagement.get("avg_response_latency_s"),
                "formed_at": match.get("formed_at"),
                "label": 1 if labels[match["_id"]] == "met_yes" else 0,
            }
        )
    return rows
