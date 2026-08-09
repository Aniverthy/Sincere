"""Public interface of the matching module (§3 rule 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sincere.matching import repository as _repo
from sincere.matching import service as _service


async def get_match(match_id: str) -> dict[str, Any] | None:
    """Match record, for chat to authorize a conversation."""
    return await _repo.get_match(match_id)


async def is_participant(match_id: str, user_id: str) -> bool:
    """Chat's authorization check: only the two matched users may read or write a thread."""
    match = await _repo.get_match(match_id)
    return match is not None and user_id in match.get("users", [])


async def is_active_match(match_id: str) -> bool:
    match = await _repo.get_match(match_id)
    return match is not None and match.get("status") == "active"


async def update_engagement(
    match_id: str, *, msg_count: int, last_msg_at: datetime, avg_latency_s: float | None
) -> None:
    """§14: chat -> matching. Engagement aggregates feed the §12 ``engagement_score``."""
    await _repo.update_engagement(
        match_id, msg_count=msg_count, last_msg_at=last_msg_at, avg_latency_s=avg_latency_s
    )


async def swipe_counts(user_id: str) -> tuple[int, int]:
    """``(swipes, matches)`` — the FR-3.4 graduation inputs."""
    return await _repo.count_swipes(user_id), await _repo.count_matches(user_id)


async def recent_swipes(user_id: str, limit: int) -> list[dict[str, Any]]:
    """Rolling window for the FR-5.2 dwell rule. Antiabuse owns the evaluation."""
    return await _repo.recent_swipes(user_id, limit)


async def generate_batch(user_id: str) -> int:
    """Build one user's daily list (§11). Used by the nightly job and on-demand."""
    return await _service.generate_batch(user_id)


async def active_user_ids_in_region(region: str) -> list[str]:
    """Everyone the nightly batch must cover in a region (§15b per-region parallelism)."""
    return await _repo.active_user_ids_in_region(region)


async def purge_user(user_id: str) -> dict[str, int]:
    """Deletion cascade (§6) for matching-owned data."""
    return await _repo.purge_user(user_id)


async def matches_needing_purge(now: datetime) -> list[dict[str, Any]]:
    """Unmatched conversations past their 90-day retention date (§8, §15b)."""
    from sincere.shared.db import C, collection

    cursor = collection(C.MATCHES).find(
        {"status": "unmatched", "messages_purge_after": {"$lte": now}}
    )
    return [doc async for doc in cursor]


__all__ = [
    "active_user_ids_in_region",
    "generate_batch",
    "get_match",
    "is_active_match",
    "is_participant",
    "matches_needing_purge",
    "purge_user",
    "recent_swipes",
    "swipe_counts",
    "update_engagement",
]
