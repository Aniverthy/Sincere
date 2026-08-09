"""Rate limiting — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §18 names four limited surfaces: **OTP issuance, swipe
velocity, message velocity, bid frequency**. Each is a named bucket below so the limit and
its justification stay together.

Fixed-window counters in Redis. A sliding window would be more precise, but §18's purpose here
is abuse suppression rather than precise quota accounting, and the fixed window is one atomic
INCR instead of a sorted-set read-modify-write on every swipe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from sincere.shared import cache
from sincere.shared.auth import Principal, current_principal
from sincere.shared.config import get_settings
from sincere.shared.errors import RateLimitedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Limit:
    """A named rate-limit bucket."""

    bucket: str
    max_requests: int
    window_seconds: int
    reason: str


def _limits() -> dict[str, Limit]:
    settings = get_settings()
    return {
        "otp": Limit(
            "otp",
            settings.rate_limit_otp_per_hour,
            3600,
            "§18: OTP issuance — blocks SMS-cost abuse and phone-number enumeration",
        ),
        "swipe": Limit(
            "swipe",
            settings.rate_limit_swipes_per_minute,
            60,
            "§18: swipe velocity — a human cannot exceed this; a script can",
        ),
        "message": Limit(
            "message",
            settings.rate_limit_messages_per_minute,
            60,
            "§18: message velocity — spam suppression",
        ),
        "bid": Limit(
            "bid",
            settings.rate_limit_bids_per_minute,
            60,
            "§18: bid frequency — prevents auction-close flooding (§15a)",
        ),
    }


async def check(bucket: str, identifier: str) -> None:
    """Consume one unit from ``bucket`` for ``identifier``. Raises when exhausted."""
    limit = _limits().get(bucket)
    if limit is None:
        raise ValueError(f"Unknown rate-limit bucket: {bucket}")

    key = cache.Keys.rate_limit(bucket, identifier)
    try:
        count = await cache.incr_with_expiry(key, limit.window_seconds)
    except Exception:  # noqa: BLE001
        # Fail open. A Redis outage must not lock every user out of the product; §21 alerts
        # on Redis health separately.
        logger.warning("ratelimit.unavailable", extra={"bucket": bucket})
        return

    if count > limit.max_requests:
        ttl = await cache.get_redis().ttl(key)
        logger.info(
            "ratelimit.exceeded",
            extra={"bucket": bucket, "count": count, "max": limit.max_requests},
        )
        raise RateLimitedError(
            retry_after=max(int(ttl), 1),
            detail=f"Limit of {limit.max_requests} per {limit.window_seconds}s exceeded.",
        )


def rate_limit(bucket: str):
    """Per-user rate-limit dependency (§7:391 "per-user rate limits").

    Usage::

        @router.post("/swipes", dependencies=[Depends(rate_limit("swipe"))])
    """

    async def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> None:
        await check(bucket, principal.user_id)

    return dependency
