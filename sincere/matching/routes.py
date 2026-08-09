"""HTTP routes for matching (§7 Matching & Swipes)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from sincere.matching import service
from sincere.matching.schemas import (
    DailyBatchResponse,
    MatchListResponse,
    SwipeRequest,
    SwipeResponse,
    UnmatchResponse,
)
from sincere.shared.auth import MATCHING_SCOPES, Principal, require_scopes
from sincere.shared.ratelimit import rate_limit

router = APIRouter(tags=["matching"])

# §5: only an ACTIVE token reaches these routes. A waitlisted man cannot see the daily 15,
# which §24 asserts under "Security".
ActivePrincipal = Annotated[Principal, Depends(require_scopes(*MATCHING_SCOPES))]


@router.get(
    "/matches/daily",
    response_model=DailyBatchResponse,
    summary="Today's precomputed 15 (30/40+ for Pro); includes boosted flags",
)
async def daily(principal: ActivePrincipal) -> DailyBatchResponse:
    return await service.daily_batch(principal.user_id)


@router.post(
    "/swipes",
    response_model=SwipeResponse,
    summary="Record a swipe with dwell time",
    dependencies=[Depends(rate_limit("swipe"))],
)
async def swipe(payload: SwipeRequest, principal: ActivePrincipal) -> SwipeResponse:
    return await service.record_swipe(
        principal.user_id, payload.target_id, payload.direction, payload.dwell_ms
    )


@router.get("/matches", response_model=MatchListResponse, summary="Active matches")
async def matches(principal: ActivePrincipal) -> MatchListResponse:
    return await service.list_matches(principal.user_id)


@router.delete(
    "/matches/{match_id}",
    response_model=UnmatchResponse,
    summary="Unmatch — starts the 90-day message-retention clock",
)
async def unmatch(match_id: str, principal: ActivePrincipal) -> UnmatchResponse:
    return await service.unmatch(principal.user_id, match_id)
