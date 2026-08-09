"""MongoDB access for chat.

§3 rule 1: this module owns ``messages``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sincere.shared.db import C, collection


async def insert_message(
    *, match_id: str, sender_id: str, body: str, client_id: str | None
) -> dict[str, Any]:
    doc = {
        "_id": str(uuid4()),
        "match_id": match_id,
        "sender_id": sender_id,
        "body": body,
        "client_id": client_id,
        "sent_at": datetime.now(UTC),
        "delivered_at": None,
        "read_at": None,
        # §8/§18: set when a harassment report pauses the retention clock.
        "retention_hold": False,
    }
    await collection(C.MESSAGES).insert_one(doc)
    return doc


async def list_messages(
    match_id: str, *, after: datetime | None, limit: int
) -> list[dict[str, Any]]:
    """History, or the reconnect delta when ``after`` is supplied (§4).

    Ascending by ``sent_at`` so the client can append without re-sorting, and so the
    ``match_id + sent_at`` index (§8) serves the query directly.
    """
    query: dict[str, Any] = {"match_id": match_id}
    if after is not None:
        query["sent_at"] = {"$gt": after}

    cursor = collection(C.MESSAGES).find(query).sort("sent_at", 1).limit(limit)
    return [doc async for doc in cursor]


async def count_messages(match_id: str) -> int:
    return await collection(C.MESSAGES).count_documents({"match_id": match_id})


async def mark_delivered(message_ids: list[str]) -> None:
    if not message_ids:
        return
    await collection(C.MESSAGES).update_many(
        {"_id": {"$in": message_ids}, "delivered_at": None},
        {"$set": {"delivered_at": datetime.now(UTC)}},
    )


async def mark_read(match_id: str, reader_id: str) -> int:
    """Mark the other participant's messages read. Returns how many changed."""
    result = await collection(C.MESSAGES).update_many(
        {"match_id": match_id, "sender_id": {"$ne": reader_id}, "read_at": None},
        {"$set": {"read_at": datetime.now(UTC)}},
    )
    return int(result.modified_count)


async def apply_retention_hold(match_id: str) -> int:
    """§18: a harassment investigation **pauses** the 90-day retention clock.

    Applied per message rather than per match so the hold survives even if the match document
    is later purged — the evidence is the messages.
    """
    result = await collection(C.MESSAGES).update_many(
        {"match_id": match_id}, {"$set": {"retention_hold": True}}
    )
    return int(result.modified_count)


async def purge_match_messages(match_id: str) -> int:
    """90-day post-unmatch purge (§8, §15b).

    **Honours investigation holds**: messages under a retention hold are deliberately left
    behind. §15b calls this out explicitly, and deleting evidence mid-investigation would be
    the worst possible bug in this system.
    """
    result = await collection(C.MESSAGES).delete_many(
        {"match_id": match_id, "retention_hold": {"$ne": True}}
    )
    return int(result.deleted_count)


async def purge_user_messages(user_id: str) -> int:
    """Deletion cascade (§6). Held messages survive for the same reason as above."""
    result = await collection(C.MESSAGES).delete_many(
        {"sender_id": user_id, "retention_hold": {"$ne": True}}
    )
    return int(result.deleted_count)


async def response_latency_stats(match_id: str, limit: int = 50) -> tuple[int, float | None]:
    """``(message_count, avg_response_latency_s)`` feeding the §12 ``engagement_score``.

    "Response latency" is measured only across *speaker changes* — the gap between one
    person's message and the other's reply. Consecutive messages from the same person are not
    replies, and counting them would report a chatty monologue as a fast conversation.
    """
    cursor = collection(C.MESSAGES).find({"match_id": match_id}).sort("sent_at", 1)
    messages = [doc async for doc in cursor]

    total = len(messages)
    if total < 2:
        return total, None

    from itertools import pairwise

    gaps: list[float] = []
    for previous, current in pairwise(messages):
        if previous["sender_id"] != current["sender_id"]:
            gaps.append((current["sent_at"] - previous["sent_at"]).total_seconds())

    recent = gaps[-limit:]
    return total, (sum(recent) / len(recent) if recent else None)


async def messages_in_window(match_id: str, since: datetime) -> int:
    """FR-4.3's We-Met trigger: total messages within a rolling window."""
    return await collection(C.MESSAGES).count_documents(
        {"match_id": match_id, "sent_at": {"$gte": since}}
    )
