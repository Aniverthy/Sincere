"""Admin/ops business logic (FR-8.1, FR-8.2).

admin is a **pure consumer**: it reads through other modules' ``api.py`` and owns only
``config_thresholds``. The import-linter contract "admin is a consumer — no module may import
admin at all" enforces the direction of that dependency.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sincere.admin.schemas import (
    MonetizationMetricsResponse,
    RegionsResponse,
    RegionSummary,
    ReviewDecisionResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    SystemHealthResponse,
    ThresholdResponse,
)
from sincere.admission import api as admission
from sincere.feedback_ml import api as feedback_ml
from sincere.identity import api as identity
from sincere.monetization import api as monetization
from sincere.shared import threshold_store
from sincere.shared.db import C, collection

logger = logging.getLogger(__name__)

#: §21: "Review-queue depth vs. founder capacity — sustained excess triggers the
#: vendor-transition roadmap item." §25 phase 2 has the founder reviewing borderline cases
#: personally, so this is a real operational ceiling, not a guess.
FOUNDER_DAILY_REVIEW_CAPACITY = 50


async def regions() -> RegionsResponse:
    """``GET /admin/regions`` — FR-8.1 ratio health across every hex."""
    summaries: list[RegionSummary] = []
    for region in await admission.list_regions():
        health = await admission.region_health(region)
        summaries.append(RegionSummary(**{k: health[k] for k in RegionSummary.model_fields}))

    # Frozen regions first: a frozen hex is the thing an operator needs to see (§21 alerts on
    # "regions frozen > N days").
    summaries.sort(key=lambda s: (s.admission_state != "frozen", s.region))

    return RegionsResponse(
        regions=summaries,
        total_regions=len(summaries),
        frozen_regions=sum(1 for s in summaries if s.admission_state == "frozen"),
    )


async def region_detail(region: str) -> dict[str, Any]:
    """``GET /admin/regions/:h3``."""
    return await admission.region_health(region)


async def review_queue(limit: int = 50) -> ReviewQueueResponse:
    """``GET /admin/review-queue`` (FR-8.1)."""
    flags = await identity.list_review_queue(limit)
    now = datetime.now(UTC)

    items = [
        ReviewQueueItem(
            flag_id=flag["_id"],
            user_id=flag["user_id"],
            composite_score=flag["composite_score"],
            band=flag["band"],
            signals=flag.get("signals", {}),
            created_at=flag["created_at"],
            waiting_hours=round((now - flag["created_at"]).total_seconds() / 3600, 1),
        )
        for flag in flags
    ]

    depth = len(items)
    warning = None
    if depth > FOUNDER_DAILY_REVIEW_CAPACITY:
        warning = (
            f"{depth} accounts are waiting, above the {FOUNDER_DAILY_REVIEW_CAPACITY}/day "
            "in-house review capacity. §25 lists a third-party moderation vendor as the "
            "scale-triggered response."
        )
        logger.warning("admin.review_queue_over_capacity", extra={"depth": depth})

    return ReviewQueueResponse(
        items=items,
        depth=depth,
        oldest_waiting_hours=max((i.waiting_hours for i in items), default=None),
        capacity_warning=warning,
    )


async def decide_review(
    flag_id: str, reviewer_id: str, decision: str, note: str | None
) -> ReviewDecisionResponse:
    """``POST /admin/review/:flagId/decision`` (FR-8.2).

    identity derives the score-agreement flag rather than accepting it from the reviewer —
    FR-1.7's retuning loop would be worthless if a reviewer could label their own agreement.
    """
    result = await identity.decide_review(
        flag_id=flag_id, reviewer_id=reviewer_id, decision=decision, note=note
    )
    return ReviewDecisionResponse(
        flag_id=result["flag_id"],
        decision=result["decision"],
        agreed_with_score=result["agreed_with_score"],
        message=(
            "Approved — the account enters the admission flow."
            if decision == "approve"
            else "Rejected."
        ),
    )


async def monetization_metrics() -> MonetizationMetricsResponse:
    """``GET /admin/metrics/monetization`` (FR-8.1)."""
    metrics = await monetization.monetization_metrics()
    return MonetizationMetricsResponse(**metrics)


async def get_thresholds() -> ThresholdResponse:
    current = await threshold_store.load()
    return ThresholdResponse(
        thresholds=current.model_dump(mode="json"),
        message="Launch defaults with any admin overrides applied.",
    )


async def patch_thresholds(
    changes: dict[str, Any], actor_id: str, reason: str | None
) -> ThresholdResponse:
    """``PATCH /admin/config/thresholds`` — §2 tunable without redeploy, §18 audited.

    Validation happens inside :func:`threshold_store.apply`, so a change violating a §12
    weight-sum or the FR-2.4 band invariant is rejected before it can reach production.
    """
    updated = await threshold_store.apply(changes, actor_id=actor_id, reason=reason)
    return ThresholdResponse(
        thresholds=updated.model_dump(mode="json"),
        changed=sorted(changes),
        message=(
            f"{len(changes)} threshold(s) updated and audited. The change is live across all "
            "replicas within a minute — no redeploy needed."
        ),
    )


async def system_health() -> SystemHealthResponse:
    """The §21 business-health metrics in one view."""
    region_list = await regions()
    queue = await review_queue(limit=500)
    model = await feedback_ml.model_info()

    outbox_pending = await collection(C.OUTBOX).count_documents(
        {"status": {"$in": ["pending", "failed"]}}
    )
    since = datetime.now(UTC) - timedelta(hours=24)
    audit_24h = await collection(C.AUDIT_LOG).count_documents({"at": {"$gte": since}})

    return SystemHealthResponse(
        regions_total=region_list.total_regions,
        regions_frozen=region_list.frozen_regions,
        review_queue_depth=queue.depth,
        wemet_labels=await feedback_ml.label_count(),
        model_version=model["version"],
        outbox_pending=outbox_pending,
        audit_entries_24h=audit_24h,
    )
