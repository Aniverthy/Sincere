"""HTTP routes for monetization (§7 Monetization)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from sincere.monetization import repository as repo
from sincere.monetization import service
from sincere.monetization.schemas import (
    CheckoutResponse,
    EntryTierResponse,
    InvoiceLine,
    InvoiceListResponse,
    PlansResponse,
    SubscribeRequest,
    SubscriptionResponse,
)
from sincere.shared import idempotency
from sincere.shared.auth import PROFILE_SCOPES, Principal, current_principal, require_scopes

router = APIRouter(tags=["monetization"])

AnyPrincipal = Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))]


@router.get("/pro/plans", response_model=PlansResponse, summary="Basic Pro / Pro Plus")
async def plans() -> PlansResponse:
    return await service.list_plans()


@router.post(
    "/pro/subscribe",
    response_model=CheckoutResponse,
    summary="Start a Pro subscription checkout",
)
async def subscribe(payload: SubscribeRequest, principal: AnyPrincipal) -> CheckoutResponse:
    endpoint = "pro.subscribe"
    replay = await idempotency.claim(payload.idempotency_key, endpoint, payload.model_dump())
    if replay is not None:
        return CheckoutResponse(**replay)

    try:
        result = await service.start_subscription_checkout(
            principal.user_id, payload.tier, payload.billing_state
        )
    except Exception:
        await idempotency.release(payload.idempotency_key, endpoint)
        raise

    await idempotency.complete(
        payload.idempotency_key, endpoint, result.model_dump(mode="json")
    )
    return result


@router.get("/pro/subscription", response_model=SubscriptionResponse, summary="Current tier")
async def subscription(principal: AnyPrincipal) -> SubscriptionResponse:
    return await service.subscription_status(principal.user_id)


@router.delete(
    "/pro/subscription",
    response_model=SubscriptionResponse,
    summary="Cancel at period end (FR-6.4: the free 15/day is never revoked)",
)
async def cancel(principal: AnyPrincipal) -> SubscriptionResponse:
    await repo.cancel_subscription(principal.user_id)
    return await service.subscription_status(principal.user_id)


@router.get(
    "/profiles/{user_id}/entry-tier",
    response_model=EntryTierResponse,
    summary="How a man entered — Pro-subscribed women only (FR-6.3)",
)
async def entry_tier(
    user_id: str, principal: Annotated[Principal, Depends(current_principal)]
) -> EntryTierResponse:
    return await service.entry_tier_for(principal.user_id, user_id)


@router.get("/pro/invoices", response_model=InvoiceListResponse, summary="GST invoices")
async def invoices(principal: AnyPrincipal) -> InvoiceListResponse:
    docs = await repo.list_invoices(principal.user_id)
    return InvoiceListResponse(
        invoices=[
            InvoiceLine(
                invoice_number=doc["invoice_number"],
                amount_paise=doc["amount"],
                taxable_paise=doc.get("taxable_paise", 0),
                cgst_paise=doc["gst"]["cgst"],
                sgst_paise=doc["gst"]["sgst"],
                igst_paise=doc["gst"]["igst"],
                place_of_supply_state=doc["gst"]["place_of_supply_state"],
                created_at=doc["created_at"],
            )
            for doc in docs
            if not str(doc.get("_id", "")).startswith("__counter__")
        ]
    )


@router.post(
    "/webhooks/payments",
    status_code=status.HTTP_200_OK,
    summary="Aggregator webhook (signature-verified)",
)
async def payment_webhook(
    request: Request,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    x_razorpay_signature: Annotated[str | None, Header(alias="X-Razorpay-Signature")] = None,
) -> dict[str, object]:
    """§18: signature-verified. Unauthenticated by necessity — the aggregator has no token —
    which is exactly why the signature is the only thing standing between a forged callback
    and free queue entry."""
    body = await request.body()
    signature = x_razorpay_signature or x_signature or ""
    return await service.handle_webhook(body, signature)
