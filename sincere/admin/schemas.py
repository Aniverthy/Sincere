"""Request/response models for admin (§7 Admin, FR-8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RegionSummary(BaseModel):
    region: str
    admission_state: str
    active_men: int
    active_women: int
    ratio: float | None
    ceiling: int
    slots_available: int
    waitlist_size: int
    frozen_since: datetime | None = None


class RegionsResponse(BaseModel):
    """``GET /admin/regions`` — FR-8.1 per-region ratio health."""

    regions: list[RegionSummary]
    total_regions: int
    frozen_regions: int


class ReviewQueueItem(BaseModel):
    flag_id: str
    user_id: str
    composite_score: float
    band: str
    signals: dict[str, Any]
    created_at: datetime
    waiting_hours: float


class ReviewQueueResponse(BaseModel):
    """``GET /admin/review-queue`` — the ambiguous band awaiting a human (FR-1.6)."""

    items: list[ReviewQueueItem]
    depth: int
    oldest_waiting_hours: float | None = None
    #: §21 alerts when depth outgrows founder capacity — surfaced so ops sees it before the alert.
    capacity_warning: str | None = None


class ReviewDecisionRequest(BaseModel):
    """``POST /admin/review/:flagId/decision``."""

    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1_000)


class ReviewDecisionResponse(BaseModel):
    flag_id: str
    decision: str
    #: FR-1.7: agreement with the automated score, derived not self-reported.
    agreed_with_score: bool
    message: str


class MonetizationMetricsResponse(BaseModel):
    """``GET /admin/metrics/monetization`` (FR-8.1)."""

    gross_paise: int
    by_purpose: dict[str, dict[str, int]]
    active_subscribers: dict[str, int]
    refunded_payments: int


class ThresholdPatchRequest(BaseModel):
    """``PATCH /admin/config/thresholds`` — audited (§18, §23:809)."""

    changes: dict[str, Any] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)


class ThresholdResponse(BaseModel):
    thresholds: dict[str, Any]
    changed: list[str] = Field(default_factory=list)
    message: str


class SystemHealthResponse(BaseModel):
    """A single ops view of the §21 business-health metrics."""

    regions_total: int
    regions_frozen: int
    review_queue_depth: int
    wemet_labels: int
    model_version: str
    outbox_pending: int
    audit_entries_24h: int
