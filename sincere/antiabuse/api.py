"""Public interface of the antiabuse module (§3 rule 2)."""

from __future__ import annotations

from typing import Any

from sincere.antiabuse import repository as _repo
from sincere.antiabuse import service as _service


async def evaluate_user(user_id: str) -> dict[str, Any]:
    """Run the FR-5.2 dwell rule and escalate if it trips."""
    return await _service.evaluate_user(user_id)


async def pending_warning(user_id: str) -> dict[str, Any] | None:
    """The unacknowledged warning interstitial the client should render (§4)."""
    return await _service.pending_warning(user_id)


async def acknowledge_warning(user_id: str) -> None:
    return await _service.acknowledge_warning(user_id)


async def record_device_signal(
    *, user_id: str, fingerprint: str | None, ip: str | None, event_type: str
) -> None:
    """FR-5.4 device/behavioural signal capture."""
    await _service.record_device_signal(
        user_id=user_id, fingerprint=fingerprint, ip=ip, event_type=event_type
    )


async def warning_ledger(user_id: str) -> dict[str, Any] | None:
    """Escalation state, for the FR-8.1 admin dashboard."""
    return await _repo.get_ledger(user_id)


async def purge_user(user_id: str) -> int:
    """Deletion cascade (§6)."""
    return await _repo.purge_user(user_id)


__all__ = [
    "acknowledge_warning",
    "evaluate_user",
    "pending_warning",
    "purge_user",
    "record_device_signal",
    "warning_ledger",
]
