"""Redis cache — cross-cutting plumbing only, no business logic.

Key namespaces and TTLs implement the TECHNICAL_IMPLEMENTATION_PLAN.md §16 table verbatim.
Keeping the key builders here (rather than as string literals across modules) means the
invalidation rules in §16 are auditable in one place.

Redis also carries two non-cache responsibilities the docs assign to it:
* live auction state — a sorted set by bid amount (§15a, §16)
* WebSocket presence for cross-replica chat fan-out (§16, §20)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

import redis.asyncio as aioredis

from sincere.shared.config import get_settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


# ---------------------------------------------------------------------------
# Key namespaces (§16)
# ---------------------------------------------------------------------------

class Keys:
    """Cache key builders. One per §16 row, plus the two Redis-native structures."""

    @staticmethod
    def daily_batch(user_id: str, batch_date: str) -> str:
        """§16: "the single hottest read; precomputed by design". TTL until next batch."""
        return f"batch:{user_id}:{batch_date}"

    @staticmethod
    def region_ratio(h3_cell: str) -> str:
        """§16: per-hex ratio counters + hysteresis state. Event-invalidated, hourly backstop."""
        return f"ratio:{h3_cell}"

    @staticmethod
    def auction_bids(h3_cell: str, window_date: str) -> str:
        """§15a/§16: live auction sorted set (member=user_id, score=bid). Settled at close."""
        return f"auction:{h3_cell}:{window_date}"

    @staticmethod
    def auction_meta(h3_cell: str, window_date: str) -> str:
        return f"auction:meta:{h3_cell}:{window_date}"

    @staticmethod
    def refresh_family(family_id: str) -> str:
        """§16: session/token metadata + refresh-reuse detection. TTL = token lifetime."""
        return f"refresh:family:{family_id}"

    @staticmethod
    def user_features(user_id: str) -> str:
        """§16: tag vector, prompt embedding, liked-centroid.

        This is what makes nightly scoring O(pool) rather than O(pool^2) (§11 step 2).
        Invalidated on profile edit and on a new like.
        """
        return f"features:{user_id}"

    @staticmethod
    def rate_limit(bucket: str, identifier: str) -> str:
        """§16/§18: rolling-window rate-limit counters."""
        return f"ratelimit:{bucket}:{identifier}"

    @staticmethod
    def presence(match_id: str) -> str:
        """§16: match -> connected sockets, for chat routing across API replicas."""
        return f"presence:{match_id}"

    @staticmethod
    def chat_channel(match_id: str) -> str:
        """Redis pub/sub channel for cross-replica message fan-out (§20)."""
        return f"chat:{match_id}"

    @staticmethod
    def thresholds() -> str:
        """§2: admin-applied threshold overrides, so a change takes effect without redeploy."""
        return "config:thresholds"


#: TTLs in seconds. ``None`` means the entry is explicitly invalidated, never expired.
TTL: Final[dict[str, int | None]] = {
    "daily_batch": 60 * 60 * 30,   # slightly over a day, so a late batch never leaves a gap
    "region_ratio": 60 * 60,       # hourly recompute is the §19 drift-correction backstop
    "user_features": 60 * 60 * 24,
    "thresholds": 60,              # short — an admin change should propagate within a minute
}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def connect() -> aioredis.Redis:
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    _client = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True, health_check_interval=30
    )
    await _client.ping()
    logger.info("redis.connected")
    return _client


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


def get_redis() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis not connected — call sincere.shared.cache.connect() first")
    return _client


# ---------------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------------

async def get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("cache.corrupt_entry", extra={"key": key})
        await get_redis().delete(key)
        return None


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    payload = json.dumps(value, default=str)
    if ttl:
        await get_redis().set(key, payload, ex=ttl)
    else:
        await get_redis().set(key, payload)


async def invalidate(*keys: str) -> None:
    if keys:
        await get_redis().delete(*keys)


async def incr_with_expiry(key: str, ttl: int) -> int:
    """Atomic increment that sets the TTL on first write. Backs the rate limiter."""
    pipe = get_redis().pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl, nx=True)
    result = await pipe.execute()
    return int(result[0])
