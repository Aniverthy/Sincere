"""Public interface of the admission module.

Other modules may import ONLY from this file (§3 rule 2).
"""

from __future__ import annotations

from typing import Any

from sincere.admission import repository as _repo
from sincere.admission import service as _service
from sincere.admission.ratio import AdmissionState, RatioSnapshot
from sincere.admission.schemas import QueueTier


async def get_region_state(region: str) -> tuple[RatioSnapshot, AdmissionState]:
    """Ratio counts and hysteresis state for a hex. Read-only."""
    snapshot, state, _ = await _service.snapshot_for(region)
    return snapshot, state


async def region_health(region: str) -> dict[str, Any]:
    """FR-8.1 dashboard view of one region."""
    return (await _service.region_health(region)).model_dump(mode="json")


async def list_regions() -> list[str]:
    return await _repo.list_regions()


async def admit_or_waitlist(user_id: str) -> str:
    """Run the FR-2.4/2.5 admission gate. Returns ``"active"`` or ``"waitlisted"``."""
    return await _service.admit_or_waitlist(user_id)


async def drain_waitlist(region: str) -> dict[str, int]:
    """Admit as many waitlisted men as the ceiling allows (FR-2.7)."""
    return await _service.drain_waitlist(region)


async def recount_region(region: str) -> RatioSnapshot:
    """§19 drift correction — authoritative recount from ``users``."""
    return await _service.recount_region(region)


async def promote_to_paid_tier(user_id: str, region: str) -> None:
    """Called by monetization on ``PaymentSucceeded`` for a queue purchase (FR-2.8).

    Moves the user into the paid tier of the waitlist. It does **not** admit him directly:
    FR-2.7 says the paid tier draws from the same ratio ceiling as the others, so paying buys
    a better queue, never a bypass of FR-2.4.
    """
    await _repo.promote_tier(region, user_id, str(QueueTier.PAID))


async def remove_from_queues(user_id: str, region: str | None) -> None:
    """Deletion cascade (§6): remove the user from every queue immediately."""
    if region:
        await _repo.remove_from_waitlist(region, user_id)
        return
    for known_region in await _repo.list_regions():
        await _repo.remove_from_waitlist(known_region, user_id)


async def adjust_active_count(region: str, gender: str, delta: int) -> None:
    """Event-maintained ratio counters (§19). Used when a user goes (in)active."""
    await _repo.adjust_count(region, gender=gender, delta=delta)


async def close_auction(region: str, window_end: Any) -> dict[str, Any]:
    """Settle a region's auction (§15a). Idempotent."""
    return await _service.close_auction(region, window_end)


__all__ = [
    "AdmissionState",
    "QueueTier",
    "RatioSnapshot",
    "adjust_active_count",
    "admit_or_waitlist",
    "close_auction",
    "drain_waitlist",
    "get_region_state",
    "list_regions",
    "promote_to_paid_tier",
    "recount_region",
    "region_health",
    "remove_from_queues",
]
