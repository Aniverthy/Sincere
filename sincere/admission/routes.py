"""HTTP routes for admission (§7 Queue, Waitlist, Auction)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from sincere.admission import service
from sincere.admission.schemas import (
    AuctionResultResponse,
    AuctionTodayResponse,
    BidRequest,
    PaidCheckoutRequest,
    PaidCheckoutResponse,
    QueueStatusResponse,
)
from sincere.shared import idempotency
from sincere.shared.auth import QUEUE_SCOPES, Principal, require_scopes
from sincere.shared.errors import ServiceUnavailableError
from sincere.shared.ratelimit import rate_limit

router = APIRouter(tags=["admission"])

QueuePrincipal = Annotated[Principal, Depends(require_scopes(*QUEUE_SCOPES))]


@router.get("/queue/status", response_model=QueueStatusResponse, summary="Tier, position, state")
async def queue_status(principal: QueuePrincipal) -> QueueStatusResponse:
    return await service.queue_status(principal.user_id)


@router.post(
    "/queue/paid/checkout",
    response_model=PaidCheckoutResponse,
    summary="Fixed-price paid entry (FR-2.8: never surge-priced)",
)
async def paid_checkout(
    payload: PaidCheckoutRequest, principal: QueuePrincipal
) -> PaidCheckoutResponse:
    # §7:391 requires an idempotency key on money-moving endpoints — a retried checkout on a
    # flaky mobile connection must not charge twice.
    endpoint = "queue.paid.checkout"
    replay = await idempotency.claim(payload.idempotency_key, endpoint, payload.model_dump())
    if replay is not None:
        return PaidCheckoutResponse(**replay)

    try:
        from sincere.monetization import api as monetization

        result = await monetization.start_queue_checkout(principal.user_id)
    except ImportError as exc:
        await idempotency.release(payload.idempotency_key, endpoint)
        raise ServiceUnavailableError(
            "Paid entry unavailable",
            "Paid queue entry is not enabled yet. Your free-queue place is unaffected.",
        ) from exc
    except Exception:
        await idempotency.release(payload.idempotency_key, endpoint)
        raise

    await idempotency.complete(payload.idempotency_key, endpoint, result)
    return PaidCheckoutResponse(**result)


@router.get(
    "/auction/today",
    response_model=AuctionTodayResponse,
    summary="Window, anonymized top bids, slots",
)
async def auction_today(principal: QueuePrincipal) -> AuctionTodayResponse:
    return await service.auction_today(principal.user_id)


@router.post(
    "/auction/bid",
    response_model=AuctionTodayResponse,
    summary="Ascending bid (FR-2.9)",
    dependencies=[Depends(rate_limit("bid"))],
)
async def place_bid(payload: BidRequest, principal: QueuePrincipal) -> AuctionTodayResponse:
    endpoint = "auction.bid"
    replay = await idempotency.claim(payload.idempotency_key, endpoint, payload.model_dump())
    if replay is not None:
        return AuctionTodayResponse(**replay)

    try:
        result = await service.place_bid(principal.user_id, payload.amount_paise)
    except Exception:
        await idempotency.release(payload.idempotency_key, endpoint)
        raise

    await idempotency.complete(
        payload.idempotency_key, endpoint, result.model_dump(mode="json")
    )
    return result


@router.get(
    "/auction/result",
    response_model=AuctionResultResponse,
    summary="Post-close outcome; losers are auto-refunded",
)
async def auction_result(principal: QueuePrincipal) -> AuctionResultResponse:
    return await service.auction_result(principal.user_id)
