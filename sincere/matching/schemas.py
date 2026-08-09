"""Request/response models for matching (§7 Matching & Swipes)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field


class SwipeDirection(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class MatchStatus(StrEnum):
    ACTIVE = "active"
    UNMATCHED = "unmatched"


class DailyCandidate(BaseModel):
    """One profile in the daily batch."""

    user_id: str
    name: str | None = None
    age: int | None = None
    bio: str | None = None
    prompts: list[dict[str, str]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    photos: list[dict[str, Any]] = Field(default_factory=list)
    distance_km: float | None = None

    boosted: bool = False
    """FR-6.2 (DECIDED): when true the client MUST render a "Boosted" label."""

    #: Never populated here. FR-6.3 gates entry-tier visibility behind a Pro subscription,
    #: and monetization owns that check — see ``GET /profiles/:id/entry-tier``.
    entry_tier: None = None


class DailyBatchResponse(BaseModel):
    """``GET /matches/daily`` — today's precomputed 15 (30/40+ for Pro)."""

    batch_date: str
    candidates: list[DailyCandidate]
    total: int
    remaining: int
    generated_at: datetime | None = None
    message: str | None = None


class SwipeRequest(BaseModel):
    """``POST /swipes``."""

    target_id: str
    direction: SwipeDirection

    dwell_ms: Annotated[int, Field(ge=0, le=3_600_000)]
    """Client-measured time the profile was visible before the swipe (§4).

    §18: "client-reported ``dwell_ms`` is cross-checked server-side (profile-payload fetch
    time vs. swipe time) since **the client is untrusted**." The antiabuse module performs
    that cross-check; this field is the claim, not the truth.
    """


class SwipeResponse(BaseModel):
    matched: bool
    match_id: str | None = None
    remaining_today: int = 0
    #: Populated when the swipe tripped an FR-5 warning, so the client can show the
    #: interstitial (§4). Never a silent penalty.
    warning: dict[str, Any] | None = None


class MatchSummary(BaseModel):
    match_id: str
    user_id: str
    name: str | None = None
    photo_url: str | None = None
    formed_at: datetime
    last_message_at: datetime | None = None
    message_count: int = 0
    unread: bool = False


class MatchListResponse(BaseModel):
    matches: list[MatchSummary]
    total: int


class UnmatchResponse(BaseModel):
    match_id: str
    unmatched_at: datetime
    messages_purge_after: datetime
    message: str
