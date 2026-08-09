"""Request/response models for the identity module (§7 Identity & Verification, Profile)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")  # E.164


class Gender(StrEnum):
    """Sincère's ratio system (FR-2.4) is defined over two opposite pools, so gender is a
    two-valued field here. This is a mechanical constraint of the documented admission model,
    not a statement about identity."""

    MALE = "male"
    FEMALE = "female"


class UserStatus(StrEnum):
    """The §6 lifecycle states, as stored in ``users.status`` (§8)."""

    ONBOARDING = "onboarding"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    WAITLISTED = "waitlisted"
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    GRACE_PERIOD = "grace_period"


class RiskBand(StrEnum):
    """FR-1.6 three-band routing. The middle band is the only one a human ever sees."""

    AUTO_APPROVE = "auto_approve"
    REVIEW = "review"
    AUTO_REJECT = "auto_reject"


class EntryTier(StrEnum):
    """FR-6.3: how a man entered. Visible only to Pro-subscribed women."""

    FREE = "free"
    PAID = "paid"
    AUCTION = "auction"


# ---------------------------------------------------------------------------
# Auth (§7 Identity & Verification)
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    """``POST /auth/signup`` — phone → OTP."""

    phone: str = Field(description="E.164 format, e.g. +919876543210")

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        value = value.strip().replace(" ", "")
        if not PHONE_PATTERN.match(value):
            raise ValueError("Phone must be in E.164 format, e.g. +919876543210")
        return value


class SignupResponse(BaseModel):
    challenge_id: str
    expires_in: int
    #: Dev convenience only — populated when SMS_PROVIDER=console so the flow is testable
    #: without an SMS account. Never populated in staging or production.
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    """``POST /auth/verify-otp`` → onboarding-scope tokens."""

    challenge_id: str
    otp: str = Field(min_length=4, max_length=8)
    #: FR-5.4 / §8 device_signals: fingerprint collected at signup for velocity clustering.
    device_fingerprint: str | None = None


class TokenResponse(BaseModel):
    """§5 token pair. ``scope`` mirrors the lifecycle state and drives client navigation."""

    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    scope: str
    status: UserStatus


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Profile (§7 Profile & Location, §8 users.profile)
# ---------------------------------------------------------------------------

class Prompt(BaseModel):
    """§8 ``profile.prompts: [{q, a}]``. Answers feed ``prompt_text_similarity`` (§12)."""

    q: str = Field(max_length=120)
    a: str = Field(min_length=1, max_length=400)


class Photo(BaseModel):
    url: str
    object_key: str
    is_boost_labeled: bool = False


class ProfileUpdate(BaseModel):
    """``PATCH /me``. Every field optional — this is a partial update."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    dob: date | None = None
    bio: str | None = Field(default=None, max_length=500)
    prompts: list[Prompt] | None = Field(default=None, max_length=5)
    tags: list[str] | None = Field(default=None, max_length=20)
    photos: list[Photo] | None = Field(default=None, max_length=6)
    """Uploaded via pre-signed URL first (§4); this records the resulting object keys on the
    profile. FR-1.5 then matches these against the verification selfie, which is why they
    must be persisted *before* the liveness capture runs."""

    @field_validator("dob")
    @classmethod
    def _must_be_adult(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = datetime.now(UTC).date()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise ValueError("You must be 18 or older to use Sincère")
        if age > 120:
            raise ValueError("Please enter a valid date of birth")
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return sorted({tag.strip().lower() for tag in value if tag.strip()})


class RadiusUpdate(BaseModel):
    """``PATCH /me/radius``. FR-3.2 bounds the slider at 1-100 km."""

    radius_km: Annotated[int, Field(ge=1, le=100)]


class LocationUpdate(BaseModel):
    """``POST /me/location`` — sent on every app open (FR-3.3).

    §18 "location minimalism": this OVERWRITES a single value. No history is kept, so there
    is no location log to breach.
    """

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class ProfileResponse(BaseModel):
    user_id: str
    status: UserStatus
    gender: Gender
    name: str | None = None
    dob: date | None = None
    bio: str | None = None
    prompts: list[Prompt] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    photos: list[Photo] = Field(default_factory=list)
    radius_km: int = 25
    h3_region: str | None = None
    graduated: bool = False
    swipe_count: int = 0
    match_count: int = 0


# ---------------------------------------------------------------------------
# Verification (§5, §9)
# ---------------------------------------------------------------------------

class LivenessSessionResponse(BaseModel):
    """§5: "randomized prompt sequence + pre-signed upload URL".

    The sequence is randomized per session precisely so a replayed recording of someone
    else's session fails — that is what makes the check *live* (FR-1.2).
    """

    session_id: str
    prompt_sequence: list[str]
    upload_url: str
    object_key: str
    expires_at: datetime


class LivenessSubmitRequest(BaseModel):
    """``POST /verification/liveness`` — submit the capture reference (FR-1.2)."""

    session_id: str
    object_key: str


class VerificationStatusResponse(BaseModel):
    """``GET /verification/status`` — onboarding / pending-review / verified / rejected."""

    status: UserStatus
    band: RiskBand | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    message: str


class PhotoUploadRequest(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/heic"]


class PhotoUploadResponse(BaseModel):
    upload_url: str
    object_key: str
    expires_at: datetime
    public_url: str | None = None
    """Where the photo will be readable once uploaded, so the client does not have to
    reconstruct the URL. Absolute, resolved against the calling request's host."""


# ---------------------------------------------------------------------------
# Account lifecycle (§6, FR-7)
# ---------------------------------------------------------------------------

class DeleteAccountResponse(BaseModel):
    """``DELETE /me`` — starts the 30-day grace period (§6)."""

    deleted_at: datetime
    restorable_until: datetime
    message: str


class RestoreAccountResponse(BaseModel):
    status: UserStatus
    message: str


# ---------------------------------------------------------------------------
# Admin review (FR-1.7, §7 Admin)
# ---------------------------------------------------------------------------

class ReviewDecision(BaseModel):
    """``POST /admin/review/:flagId/decision``.

    FR-1.7 requires logging whether the human agreed with the automated score. That
    agreement signal is the training data for retuning the FR-1.6 band thresholds, so it is
    derived here rather than left to the reviewer to self-report.
    """

    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


class ReviewQueueItem(BaseModel):
    flag_id: str
    user_id: str
    composite_score: float
    band: RiskBand
    signals: dict[str, float | None]
    created_at: datetime

    @model_validator(mode="after")
    def _only_ambiguous_band_is_reviewable(self) -> ReviewQueueItem:
        """FR-1.6: human review exists for the ambiguous middle only. An auto-decided
        account appearing in the queue means the routing logic is wrong."""
        if self.band is not RiskBand.REVIEW:
            raise ValueError(f"Only '{RiskBand.REVIEW}' band accounts belong in the review queue")
        return self
