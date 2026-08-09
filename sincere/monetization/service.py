"""Monetization business logic (FR-6.1-6.5).

The rules that shape this module, all **(DECIDED)**:

* FR-6.1 — two tiers, **both genders**.
* FR-6.2 — boosted profiles are **always labeled**, and boost **never touches the
  compatibility score**. It changes visibility position only.
* FR-6.3 — entry-tier visibility is shown **only to women holding a Pro subscription**.
* FR-6.4 — the free 15/day is **never revoked** for active users.
* FR-6.5 — GST place-of-supply is bookkeeping with **zero effect on queue or matching**.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sincere.identity import api as identity
from sincere.monetization import gst, providers
from sincere.monetization import repository as repo
from sincere.monetization.schemas import (
    CheckoutResponse,
    EntryTierResponse,
    PaymentPurpose,
    Plan,
    PlanFeature,
    PlansResponse,
    ProTier,
    SubscriptionResponse,
)
from sincere.shared.errors import (
    ConflictError,
    NotFoundError,
    PaymentRequiredError,
    ValidationError,
)
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FR-6.1 plans
# ---------------------------------------------------------------------------

async def list_plans() -> PlansResponse:
    """``GET /pro/plans``. Feature lists are the illustrative ones from FR-6.1."""
    thresholds = await load_thresholds()

    return PlansResponse(
        plans=[
            Plan(
                tier=ProTier.BASIC_PRO,
                name="Basic Pro",
                price_paise=thresholds.pro_basic_price_paise,
                daily_matches=thresholds.daily_match_count_basic_pro,
                features=[
                    PlanFeature(
                        label=f"{thresholds.daily_match_count_basic_pro} matches a day",
                        included=True,
                    ),
                    PlanFeature(label="Undo your last swipe", included=True),
                    PlanFeature(label="Advanced filters", included=True),
                    PlanFeature(label="See who liked you", included=False),
                    PlanFeature(label="Boosted visibility", included=False),
                ],
            ),
            Plan(
                tier=ProTier.PRO_PLUS,
                name="Pro Plus",
                price_paise=thresholds.pro_plus_price_paise,
                daily_matches=thresholds.daily_match_count_pro_plus,
                features=[
                    PlanFeature(
                        label=f"{thresholds.daily_match_count_pro_plus} matches a day",
                        included=True,
                    ),
                    PlanFeature(label="Undo your last swipe", included=True),
                    PlanFeature(label="Advanced filters", included=True),
                    PlanFeature(label="See who liked you", included=True),
                    PlanFeature(label="Boosted visibility (always labelled)", included=True),
                ],
            ),
        ],
        free_tier_daily_matches=thresholds.daily_match_count,
        # FR-6.4 (DECIDED). Said plainly because it is a differentiator, not fine print.
        free_tier_note=(
            f"{thresholds.daily_match_count} matches a day are free forever for active "
            "members. Pro adds volume and convenience — it never buys better compatibility."
        ),
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

async def start_subscription_checkout(
    user_id: str, tier: ProTier, billing_state: str
) -> CheckoutResponse:
    """``POST /pro/subscribe``."""
    if not gst.is_valid_state(billing_state):
        raise ValidationError(f"'{billing_state}' is not a valid GST state code.")

    thresholds = await load_thresholds()
    amount = (
        thresholds.pro_plus_price_paise
        if tier is ProTier.PRO_PLUS
        else thresholds.pro_basic_price_paise
    )

    existing = await repo.get_subscription(user_id)
    if existing and existing.get("status") == "active" and existing.get("tier") == str(tier):
        readable = tier.value.replace("_", " ")
        raise ConflictError("Already subscribed", f"You already have {readable}.")

    return await _checkout(
        user_id=user_id,
        purpose=PaymentPurpose.SUBSCRIPTION,
        amount_paise=amount,
        description=f"Sincère {tier.value}",
        metadata={"tier": str(tier), "billing_state": billing_state.upper()},
    )


async def start_queue_checkout(user_id: str) -> dict[str, Any]:
    """Paid queue entry (FR-2.8: **fixed price, no surge**).

    Called by the admission module through ``monetization.api``.
    """
    thresholds = await load_thresholds()
    user = await identity.get_user_summary(user_id)
    if user is None:
        raise NotFoundError("Account")
    if user["status"] != "waitlisted":
        raise ConflictError(
            "Not on the waitlist", "Paid entry is only for people waiting to join."
        )

    response = await _checkout(
        user_id=user_id,
        purpose=PaymentPurpose.QUEUE_ENTRY,
        amount_paise=thresholds.paid_queue_price_paise,
        description="Sincère priority entry",
        metadata={"region": user["h3_region"], "billing_state": gst.HOME_STATE_CODE},
    )
    return response.model_dump(mode="json")


async def _checkout(
    *, user_id: str, purpose: PaymentPurpose, amount_paise: int, description: str, metadata: dict
) -> CheckoutResponse:
    payment = await repo.create_payment(
        user_id=user_id, purpose=str(purpose), amount_paise=amount_paise, metadata=metadata
    )
    session = await providers.get_provider().create_checkout(
        order_id=payment["_id"],
        amount_paise=amount_paise,
        description=description,
        user_id=user_id,
    )
    return CheckoutResponse(
        payment_id=payment["_id"],
        amount_paise=amount_paise,
        checkout_url=session.checkout_url,
        expires_at=session.expires_at,
    )


# ---------------------------------------------------------------------------
# Webhook settlement (§18 signature-verified)
# ---------------------------------------------------------------------------

async def handle_webhook(payload: bytes, signature: str) -> dict[str, Any]:
    """``POST /webhooks/payments``.

    Returns a result dict; the route always replies 200 to a *verified* event so the
    aggregator stops retrying, and 400 to an unverified one.
    """
    event = providers.get_provider().verify_webhook(payload, signature)
    if event is None:
        raise ValidationError("Webhook signature verification failed.")

    payment = await repo.get_payment(event.order_id)
    if payment is None:
        logger.warning("payment.webhook_unknown_order", extra={"order_id": event.order_id})
        return {"status": "ignored", "reason": "unknown order"}

    settled = await repo.mark_paid(event.order_id, event.aggregator_ref)
    if settled is None:
        # Already settled — an aggregator redelivery. Idempotent by design (§7:391).
        return {"status": "duplicate", "payment_id": event.order_id}

    await issue_invoice(settled, event.aggregator_ref)

    await bus.emit(
        Event.PAYMENT_SUCCEEDED,
        {
            "payment_id": settled["_id"],
            "user_id": settled["user_id"],
            "purpose": settled["purpose"],
            "amount_paise": settled["amount_paise"],
            "metadata": settled.get("metadata", {}),
        },
    )
    logger.info(
        "payment.settled",
        extra={"payment_id": settled["_id"], "purpose": settled["purpose"]},
    )
    return {"status": "ok", "payment_id": settled["_id"]}


async def issue_invoice(payment: dict[str, Any], aggregator_ref: str) -> None:
    """FR-6.5 GST invoice. Bookkeeping only — nothing here touches queue or matching."""
    thresholds = await load_thresholds()
    state = (payment.get("metadata") or {}).get("billing_state") or gst.HOME_STATE_CODE

    breakdown = gst.compute(
        gross_paise=payment["amount_paise"],
        place_of_supply_state=state,
        rate=thresholds.gst_rate,
    )
    now = datetime.now(UTC)
    financial_year = gst.financial_year_for(now.month, now.year)
    sequence = await repo.next_invoice_sequence(financial_year)

    await repo.create_invoice(
        user_id=payment["user_id"],
        payment_id=payment["_id"],
        invoice_number=gst.invoice_number(sequence, financial_year),
        amount_paise=breakdown.total_paise,
        taxable_paise=breakdown.taxable_paise,
        cgst_paise=breakdown.cgst_paise,
        sgst_paise=breakdown.sgst_paise,
        igst_paise=breakdown.igst_paise,
        place_of_supply_state=breakdown.place_of_supply_state,
        aggregator_ref=aggregator_ref,
    )


async def activate_subscription(user_id: str, tier: str) -> None:
    """Turn a settled subscription payment into entitlement (FR-6.1)."""
    await repo.upsert_subscription(user_id=user_id, tier=tier)
    logger.info("subscription.activated", extra={"user_id": user_id, "tier": tier})


async def refund(payment_id: str) -> str | None:
    """Refund a settled payment — used for auction losers (§7 "auto-refunded")."""
    payment = await repo.get_payment(payment_id)
    if payment is None or payment["status"] != "succeeded":
        return None

    refund_ref = await providers.get_provider().refund(
        aggregator_ref=payment["aggregator_ref"], amount_paise=payment["amount_paise"]
    )
    await repo.mark_refunded(payment_id, refund_ref)
    logger.info("payment.refunded", extra={"payment_id": payment_id})
    return refund_ref


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------

async def subscription_status(user_id: str) -> SubscriptionResponse:
    thresholds = await load_thresholds()
    sub = await repo.get_subscription(user_id)

    if sub is None or sub.get("renews_at", datetime.now(UTC)) <= datetime.now(UTC):
        return SubscriptionResponse(
            tier=None,
            status="free",
            # FR-6.4: the free allowance stands regardless of subscription state.
            daily_matches=thresholds.daily_match_count,
        )

    tier = ProTier(sub["tier"])
    return SubscriptionResponse(
        tier=tier,
        status=sub.get("status", "active"),
        renews_at=sub.get("renews_at"),
        daily_matches=(
            thresholds.daily_match_count_pro_plus
            if tier is ProTier.PRO_PLUS
            else thresholds.daily_match_count_basic_pro
        ),
        boosted=tier is ProTier.PRO_PLUS,
    )


async def entry_tier_for(viewer_id: str, target_id: str) -> EntryTierResponse:
    """``GET /profiles/:id/entry-tier`` — FR-6.3 (DECIDED gate).

    "Entry-tier visibility (how a man entered: free/paid/auction) shown **only to women
    holding a Pro subscription**."

    Both halves of the gate are enforced: Pro subscription **and** the viewer being a woman.
    The doc flags this feature for reception monitoring post-launch, so the check is written
    to be easy to find and remove if it is pulled.
    """
    viewer = await identity.get_user_summary(viewer_id)
    if viewer is None:
        raise NotFoundError("Account")

    if viewer.get("gender") != "female":
        raise PaymentRequiredError(
            "Entry-tier visibility is available to women with a Pro subscription."
        )

    status = await subscription_status(viewer_id)
    if status.tier is None:
        raise PaymentRequiredError(
            "Entry-tier visibility requires a Pro subscription."
        )

    target = await identity.get_user_summary(target_id)
    if target is None:
        raise NotFoundError("Profile")

    return EntryTierResponse(
        user_id=target_id,
        entry_tier=target.get("entry_tier"),
        note=(
            "How this person joined. Paid and auction entry affect timing only — everyone is "
            "ranked the same way."  # FR-2.11, said plainly to pre-empt the wrong inference
        ),
    )
