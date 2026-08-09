"""MongoDB access for monetization.

§3 rule 1: this module owns ``subscriptions``, ``payments`` and ``invoices``.

§18: payment records are retained 5-7 years per financial regulation and are **decoupled from
the account-deletion cascade** — so there is deliberately no ``purge_user`` here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sincere.shared.db import C, collection

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

async def create_payment(
    *, user_id: str, purpose: str, amount_paise: int, metadata: dict[str, Any]
) -> dict[str, Any]:
    doc = {
        "_id": str(uuid4()),
        "user_id": user_id,
        "purpose": purpose,
        "amount_paise": amount_paise,
        "status": "pending",
        "aggregator_ref": None,
        "metadata": metadata,
        "created_at": datetime.now(UTC),
        "settled_at": None,
    }
    await collection(C.PAYMENTS).insert_one(doc)
    return doc


async def get_payment(payment_id: str) -> dict[str, Any] | None:
    return await collection(C.PAYMENTS).find_one({"_id": payment_id})


async def mark_paid(payment_id: str, aggregator_ref: str) -> dict[str, Any] | None:
    """Settle a payment. Filtering on ``status: pending`` makes webhook replay a no-op —
    aggregators redeliver, and §7:391's idempotency requirement applies here too."""
    return await collection(C.PAYMENTS).find_one_and_update(
        {"_id": payment_id, "status": "pending"},
        {
            "$set": {
                "status": "succeeded",
                "aggregator_ref": aggregator_ref,
                "settled_at": datetime.now(UTC),
            }
        },
        return_document=True,
    )


async def mark_refunded(payment_id: str, refund_ref: str) -> None:
    await collection(C.PAYMENTS).update_one(
        {"_id": payment_id},
        {
            "$set": {
                "status": "refunded",
                "refund_ref": refund_ref,
                "refunded_at": datetime.now(UTC),
            }
        },
    )


async def find_payment_by_ref(aggregator_ref: str) -> dict[str, Any] | None:
    return await collection(C.PAYMENTS).find_one({"aggregator_ref": aggregator_ref})


# ---------------------------------------------------------------------------
# Subscriptions (FR-6.1)
# ---------------------------------------------------------------------------

async def upsert_subscription(
    *, user_id: str, tier: str, period_days: int = 30
) -> dict[str, Any]:
    now = datetime.now(UTC)
    renews_at = now + timedelta(days=period_days)
    await collection(C.SUBSCRIPTIONS).update_one(
        {"user_id": user_id},
        {
            "$set": {
                "tier": tier,
                "status": "active",
                "renews_at": renews_at,
                "updated_at": now,
            },
            "$setOnInsert": {"_id": str(uuid4()), "created_at": now},
        },
        upsert=True,
    )
    doc = await collection(C.SUBSCRIPTIONS).find_one({"user_id": user_id})
    assert doc is not None
    return doc


async def get_subscription(user_id: str) -> dict[str, Any] | None:
    return await collection(C.SUBSCRIPTIONS).find_one({"user_id": user_id})


async def cancel_subscription(user_id: str) -> None:
    """Cancel at period end, not immediately — the user paid for the current period."""
    await collection(C.SUBSCRIPTIONS).update_one(
        {"user_id": user_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(UTC)}},
    )


async def active_subscriptions(user_ids: list[str]) -> dict[str, str]:
    """``{user_id: tier}`` for the currently-entitled subset. Batched for FR-6.2 labelling."""
    now = datetime.now(UTC)
    cursor = collection(C.SUBSCRIPTIONS).find(
        {
            "user_id": {"$in": user_ids},
            "status": {"$in": ["active", "cancelled"]},
            "renews_at": {"$gt": now},
        }
    )
    return {doc["user_id"]: doc["tier"] async for doc in cursor}


async def expired_subscriptions(now: datetime) -> list[dict[str, Any]]:
    cursor = collection(C.SUBSCRIPTIONS).find(
        {"status": {"$in": ["active", "cancelled"]}, "renews_at": {"$lte": now}}
    )
    return [doc async for doc in cursor]


async def mark_expired(user_id: str) -> None:
    await collection(C.SUBSCRIPTIONS).update_one(
        {"user_id": user_id}, {"$set": {"status": "expired"}}
    )


# ---------------------------------------------------------------------------
# Invoices (FR-6.5)
# ---------------------------------------------------------------------------

async def next_invoice_sequence(financial_year: str) -> int:
    """GST invoice numbers must be sequential within a financial year.

    Uses an atomic counter document so two concurrent checkouts cannot be issued the same
    number — a duplicate invoice number is a compliance defect.
    """
    doc = await collection(C.INVOICES).find_one_and_update(
        {"_id": f"__counter__{financial_year}"},
        {"$inc": {"sequence": 1}},
        upsert=True,
        return_document=True,
    )
    return int(doc.get("sequence", 1))


async def create_invoice(
    *,
    user_id: str,
    payment_id: str,
    invoice_number: str,
    amount_paise: int,
    taxable_paise: int,
    cgst_paise: int,
    sgst_paise: int,
    igst_paise: int,
    place_of_supply_state: str,
    aggregator_ref: str | None,
) -> dict[str, Any]:
    doc = {
        "_id": str(uuid4()),
        "user_id": user_id,
        "payment_id": payment_id,
        "invoice_number": invoice_number,
        "amount": amount_paise,
        "taxable_paise": taxable_paise,
        "gst": {
            "place_of_supply_state": place_of_supply_state,
            "cgst": cgst_paise,
            "sgst": sgst_paise,
            "igst": igst_paise,
        },
        "aggregator_ref": aggregator_ref,
        "created_at": datetime.now(UTC),
    }
    await collection(C.INVOICES).insert_one(doc)
    return doc


async def list_invoices(user_id: str) -> list[dict[str, Any]]:
    cursor = collection(C.INVOICES).find({"user_id": user_id}).sort("created_at", -1)
    return [doc async for doc in cursor]


# ---------------------------------------------------------------------------
# Boosted visibility (FR-6.2)
# ---------------------------------------------------------------------------

async def boosted_user_ids(user_ids: list[str]) -> set[str]:
    """Which of these users currently hold boosted visibility.

    FR-6.1 gives boosted visibility to Pro Plus. FR-6.2 then requires those profiles be
    **labeled** wherever they appear.
    """
    tiers = await active_subscriptions(user_ids)
    return {uid for uid, tier in tiers.items() if tier == "pro_plus"}
