"""Public interface of the monetization module (§3 rule 2)."""

from __future__ import annotations

from typing import Any

from sincere.monetization import repository as _repo
from sincere.monetization import service as _service


async def get_tier(user_id: str) -> str | None:
    """Current Pro tier, or ``None`` for a free user. Drives the FR-6.1 daily allowance."""
    status = await _service.subscription_status(user_id)
    return str(status.tier) if status.tier else None


async def boosted_user_ids(user_ids: list[str]) -> set[str]:
    """Which of these profiles hold boosted visibility (FR-6.1 Pro Plus).

    Matching calls this so every delivered candidate carries a ``boosted`` flag — FR-6.2
    makes the label mandatory wherever a boosted profile appears.
    """
    return await _repo.boosted_user_ids(user_ids)


async def start_queue_checkout(user_id: str) -> dict[str, Any]:
    """Paid queue entry (FR-2.8). Called by admission."""
    return await _service.start_queue_checkout(user_id)


async def charge_auction_winner(user_id: str, amount_paise: int, region: str) -> str:
    """Charge a winning bidder at auction close (§15a).

    Creates a settled payment record and its GST invoice. The bid was already committed
    during the window, so this records the charge rather than asking for consent again.
    """
    payment = await _repo.create_payment(
        user_id=user_id,
        purpose="auction",
        amount_paise=amount_paise,
        metadata={"region": region, "billing_state": "KA"},
    )
    settled = await _repo.mark_paid(payment["_id"], f"auction_{payment['_id']}")
    if settled:
        await _service.issue_invoice(settled, settled["aggregator_ref"])
    return payment["_id"]


async def refund_payment(payment_id: str) -> str | None:
    """Refund a settled payment — auction losers are auto-refunded (§7)."""
    return await _service.refund(payment_id)


async def activate_subscription(user_id: str, tier: str) -> None:
    await _service.activate_subscription(user_id, tier)


async def monetization_metrics() -> dict[str, Any]:
    """FR-8.1: "monetization metrics" for the admin dashboard."""
    from sincere.shared.db import C, collection

    pipeline = [
        {"$match": {"status": "succeeded"}},
        {
            "$group": {
                "_id": "$purpose",
                "count": {"$sum": 1},
                "gross_paise": {"$sum": "$amount_paise"},
            }
        },
    ]
    by_purpose = {
        doc["_id"]: {"count": doc["count"], "gross_paise": doc["gross_paise"]}
        async for doc in collection(C.PAYMENTS).aggregate(pipeline)
    }

    subscribers = {
        tier: await collection(C.SUBSCRIPTIONS).count_documents(
            {"tier": tier, "status": "active"}
        )
        for tier in ("basic_pro", "pro_plus")
    }
    refunded = await collection(C.PAYMENTS).count_documents({"status": "refunded"})

    return {
        "by_purpose": by_purpose,
        "active_subscribers": subscribers,
        "refunded_payments": refunded,
        "gross_paise": sum(v["gross_paise"] for v in by_purpose.values()),
    }


__all__ = [
    "activate_subscription",
    "boosted_user_ids",
    "charge_auction_winner",
    "get_tier",
    "monetization_metrics",
    "refund_payment",
    "start_queue_checkout",
]
