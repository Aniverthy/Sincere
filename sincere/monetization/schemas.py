"""Request/response models for monetization (§7 Monetization)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProTier(StrEnum):
    """FR-6.1 (DECIDED): two tiers, available to **both genders**."""

    BASIC_PRO = "basic_pro"
    PRO_PLUS = "pro_plus"


class PaymentPurpose(StrEnum):
    QUEUE_ENTRY = "queue_entry"
    AUCTION = "auction"
    SUBSCRIPTION = "subscription"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PlanFeature(BaseModel):
    label: str
    included: bool


class Plan(BaseModel):
    tier: ProTier
    name: str
    price_paise: int
    period: str = "month"
    features: list[PlanFeature]
    daily_matches: int


class PlansResponse(BaseModel):
    """``GET /pro/plans``."""

    plans: list[Plan]
    #: FR-6.4 (DECIDED): base access is free forever for active users — never revoked.
    free_tier_daily_matches: int
    free_tier_note: str


class SubscribeRequest(BaseModel):
    """``POST /pro/subscribe``."""

    tier: ProTier
    idempotency_key: str = Field(min_length=8, max_length=128)
    billing_state: str = Field(
        min_length=2,
        max_length=2,
        description="GST state code from the billing address (FR-6.5 place of supply)",
    )


class CheckoutResponse(BaseModel):
    payment_id: str
    amount_paise: int
    checkout_url: str
    expires_at: datetime


class SubscriptionResponse(BaseModel):
    tier: ProTier | None = None
    status: str
    renews_at: datetime | None = None
    daily_matches: int
    boosted: bool = False


class EntryTierResponse(BaseModel):
    """``GET /profiles/:id/entry-tier`` — FR-6.3, Pro-subscribed women only."""

    user_id: str
    entry_tier: str | None
    note: str


class InvoiceLine(BaseModel):
    invoice_number: str
    amount_paise: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    place_of_supply_state: str
    created_at: datetime


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceLine]
