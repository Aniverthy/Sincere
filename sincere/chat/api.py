"""Public interface of the chat module (§3 rule 2)."""

from __future__ import annotations

from datetime import datetime

from sincere.chat import repository as _repo
from sincere.chat import service as _service


async def engagement_stats(match_id: str) -> tuple[int, float | None]:
    """``(message_count, avg_response_latency_s)`` — the §12 ``engagement_score`` inputs."""
    return await _service.engagement_for(match_id)


async def messages_in_window(match_id: str, since: datetime) -> int:
    """FR-4.3: total messages within a rolling window, for the We-Met trigger."""
    return await _repo.messages_in_window(match_id, since)


async def message_count(match_id: str) -> int:
    return await _repo.count_messages(match_id)


async def apply_retention_hold(match_id: str) -> int:
    """§18: pause a conversation's retention clock for an investigation."""
    return await _repo.apply_retention_hold(match_id)


async def purge_match_messages(match_id: str) -> int:
    """90-day post-unmatch purge (§8, §15b). **Honours investigation holds.**"""
    return await _repo.purge_match_messages(match_id)


async def purge_user_messages(user_id: str) -> int:
    """Deletion cascade (§6). Held messages survive."""
    return await _repo.purge_user_messages(user_id)


async def open_conversation(match_id: str, users: list[str]) -> None:
    """Called by the ``MatchFormed`` reaction (§14)."""
    await _service.open_conversation(match_id, users)


__all__ = [
    "apply_retention_hold",
    "engagement_stats",
    "message_count",
    "messages_in_window",
    "open_conversation",
    "purge_match_messages",
    "purge_user_messages",
]
