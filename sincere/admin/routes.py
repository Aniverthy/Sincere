"""HTTP routes for admin (§7 Admin, FR-8).

Every route requires the ADMIN scope. §18: "Admin actions audited; threshold changes logged
with actor + before/after" — the audit writes happen in the services these routes call.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from sincere.admin import service
from sincere.admin.schemas import (
    MonetizationMetricsResponse,
    RegionsResponse,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueResponse,
    SystemHealthResponse,
    ThresholdPatchRequest,
    ThresholdResponse,
)
from sincere.shared.auth import Principal, Scope, require_scopes

router = APIRouter(prefix="/admin", tags=["admin"])

AdminPrincipal = Annotated[Principal, Depends(require_scopes(Scope.ADMIN))]


@router.get("/regions", response_model=RegionsResponse, summary="Per-region ratio health")
async def regions(_: AdminPrincipal) -> RegionsResponse:
    return await service.regions()


@router.get("/regions/{region}", summary="One hex: ratio, hysteresis state, queue depths")
async def region_detail(region: str, _: AdminPrincipal) -> dict[str, Any]:
    return await service.region_detail(region)


@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    summary="Ambiguous-band accounts awaiting a human decision",
)
async def review_queue(
    _: AdminPrincipal, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> ReviewQueueResponse:
    return await service.review_queue(limit)


@router.post(
    "/review/{flag_id}/decision",
    response_model=ReviewDecisionResponse,
    summary="Approve/reject with score-agreement logging (FR-8.2)",
)
async def review_decision(
    flag_id: str, payload: ReviewDecisionRequest, principal: AdminPrincipal
) -> ReviewDecisionResponse:
    return await service.decide_review(
        flag_id, principal.user_id, payload.decision, payload.note
    )


@router.get(
    "/metrics/monetization",
    response_model=MonetizationMetricsResponse,
    summary="Revenue and subscriber metrics",
)
async def monetization_metrics(_: AdminPrincipal) -> MonetizationMetricsResponse:
    return await service.monetization_metrics()


@router.get("/config/thresholds", response_model=ThresholdResponse, summary="Current thresholds")
async def get_thresholds(_: AdminPrincipal) -> ThresholdResponse:
    return await service.get_thresholds()


@router.patch(
    "/config/thresholds",
    response_model=ThresholdResponse,
    summary="Tune launch defaults without a redeploy (audited)",
)
async def patch_thresholds(
    payload: ThresholdPatchRequest, principal: AdminPrincipal
) -> ThresholdResponse:
    return await service.patch_thresholds(payload.changes, principal.user_id, payload.reason)


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="The §21 business-health metrics in one view",
)
async def system_health(_: AdminPrincipal) -> SystemHealthResponse:
    return await service.system_health()
