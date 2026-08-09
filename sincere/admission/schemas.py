"""Request/response models for admission (§7 Queue, Waitlist, Auction)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from sincere.admission.ratio import AdmissionState


class QueueTier(StrEnum):
    """FR-2.7's three tiers. All draw from the same ratio ceiling."""

    FREE = "free"
    PAID = "paid"
    AUCTION = "auction"


class AuctionStatus(StrEnum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    SETTLING = "settling"
    SETTLED = "settled"


class QueueStatusResponse(BaseModel):
    """``GET /queue/status`` — tier, position, region admission state."""

    region: str
    admission_state: AdmissionState
    tier: QueueTier | None = None
    position: int | None = None
    waitlist_size: int = 0
    slots_available: int = 0
    active_men: int = 0
    active_women: int = 0
    estimated_days: float | None = None
    #: FR-2.11 — surfaced so the client can say it plainly rather than let users assume.
    paid_entry_affects_ranking: bool = False
    message: str


class PaidCheckoutRequest(BaseModel):
    """``POST /queue/paid/checkout``. FR-2.8: fixed price, never surge."""

    idempotency_key: str = Field(min_length=8, max_length=128)


class PaidCheckoutResponse(BaseModel):
    payment_id: str
    amount_paise: int
    checkout_url: str
    expires_at: datetime


class BidRequest(BaseModel):
    """``POST /auction/bid`` — ascending only (FR-2.9)."""

    amount_paise: Annotated[int, Field(gt=0)]
    idempotency_key: str = Field(min_length=8, max_length=128)


class AuctionBidView(BaseModel):
    """§7: "current top bids (**anonymized**)". No user ids ever leave this endpoint."""

    rank: int
    amount_paise: int
    is_you: bool = False


class AuctionTodayResponse(BaseModel):
    """``GET /auction/today``."""

    region: str
    status: AuctionStatus
    window_start: datetime
    window_end: datetime
    slots: int
    min_bid_paise: int
    #: The bid a new entrant must beat to be in a winning position right now.
    standing_requirement_paise: int
    top_bids: list[AuctionBidView] = Field(default_factory=list)
    your_bid_paise: int | None = None
    your_rank: int | None = None


class AuctionResultResponse(BaseModel):
    """``GET /auction/result`` — losers are auto-refunded (§7)."""

    region: str
    settled_at: datetime | None = None
    slots: int
    you_won: bool = False
    your_bid_paise: int | None = None
    clearing_bid_paise: int | None = None
    refund_status: str | None = None
    message: str


class RegionHealthResponse(BaseModel):
    """FR-8.1 admin view of one hex."""

    region: str
    admission_state: AdmissionState
    active_men: int
    active_women: int
    ratio: float | None
    ceiling: int
    slots_available: int
    waitlist_size: int
    waitlist_by_tier: dict[str, int] = Field(default_factory=dict)
    frozen_since: datetime | None = None
