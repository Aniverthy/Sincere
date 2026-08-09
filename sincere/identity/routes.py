"""HTTP routes for identity (§7 Identity & Verification, Profile & Location, Account)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from sincere.identity import service
from sincere.identity.schemas import (
    DeleteAccountResponse,
    Gender,
    LivenessSessionResponse,
    LivenessSubmitRequest,
    LocationUpdate,
    PhotoUploadRequest,
    PhotoUploadResponse,
    ProfileResponse,
    ProfileUpdate,
    RadiusUpdate,
    RefreshRequest,
    RestoreAccountResponse,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    VerificationStatusResponse,
    VerifyOtpRequest,
)
from sincere.shared import storage
from sincere.shared.auth import (
    PROFILE_SCOPES,
    VERIFICATION_SCOPES,
    Principal,
    current_principal,
    require_scopes,
)
from sincere.shared.ratelimit import check as rate_limit_check

router = APIRouter(tags=["identity"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# Auth — the only unauthenticated routes in the API (§7)
# ---------------------------------------------------------------------------

@router.post("/auth/signup", response_model=SignupResponse, summary="Request an OTP")
async def signup(payload: SignupRequest, request: Request) -> SignupResponse:
    # §18 rate-limits OTP issuance by phone, not by user: there is no user yet, and the
    # abuse being prevented is SMS-cost burning against arbitrary numbers.
    await rate_limit_check("otp", payload.phone)
    challenge_id, ttl, dev_otp = await service.start_signup(payload.phone)
    return SignupResponse(challenge_id=challenge_id, expires_in=ttl, dev_otp=dev_otp)


@router.post("/auth/verify-otp", response_model=TokenResponse, summary="Exchange OTP for tokens")
async def verify_otp(payload: VerifyOtpRequest, request: Request) -> TokenResponse:
    return await service.verify_otp(
        payload.challenge_id,
        payload.otp,
        device_fingerprint=payload.device_fingerprint,
        ip=_client_ip(request),
    )


@router.post("/auth/refresh", response_model=TokenResponse, summary="Rotate the refresh token")
async def refresh(payload: RefreshRequest) -> TokenResponse:
    return await service.refresh_tokens(payload.refresh_token)


# ---------------------------------------------------------------------------
# Verification (§5, §9)
# ---------------------------------------------------------------------------

@router.post(
    "/verification/liveness/session",
    response_model=LivenessSessionResponse,
    summary="Start a liveness capture (randomized prompts + pre-signed upload)",
)
async def liveness_session(
    request: Request,
    principal: Annotated[Principal, Depends(require_scopes(*VERIFICATION_SCOPES))],
) -> LivenessSessionResponse:
    session = await service.start_liveness_session(principal.user_id)
    # The client cannot resolve a backend-relative URL, and a phone reaches this API on the
    # dev machine's LAN address rather than localhost — so resolve it against this request.
    session.upload_url = storage.absolutize(session.upload_url, str(request.base_url))
    return session


@router.post(
    "/verification/liveness",
    response_model=VerificationStatusResponse,
    summary="Submit a liveness capture — runs the FR-1.2-1.6 pipeline",
)
async def submit_liveness(
    payload: LivenessSubmitRequest,
    principal: Annotated[Principal, Depends(require_scopes(*VERIFICATION_SCOPES))],
) -> VerificationStatusResponse:
    return await service.submit_liveness(principal.user_id, payload.session_id, payload.object_key)


@router.get(
    "/verification/status",
    response_model=VerificationStatusResponse,
    summary="onboarding / pending-review / verified / rejected",
)
async def verification_status(
    principal: Annotated[Principal, Depends(current_principal)],
) -> VerificationStatusResponse:
    return await service.verification_status(principal.user_id)


# ---------------------------------------------------------------------------
# Profile & location (§7)
# ---------------------------------------------------------------------------

@router.get("/me", response_model=ProfileResponse, summary="Current profile")
async def get_me(
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> ProfileResponse:
    return await service.get_profile(principal.user_id)


@router.patch("/me", response_model=ProfileResponse, summary="Update profile, prompts, tags")
async def patch_me(
    payload: ProfileUpdate,
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> ProfileResponse:
    return await service.update_profile(
        principal.user_id, payload.model_dump(exclude_unset=True, mode="json")
    )


@router.post("/me/gender", response_model=ProfileResponse, summary="Set gender (write-once)")
async def set_gender(
    gender: Gender,
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> ProfileResponse:
    await service.set_gender(principal.user_id, gender)
    return await service.get_profile(principal.user_id)


@router.patch("/me/radius", response_model=ProfileResponse, summary="Radius slider, 1-100 km")
async def patch_radius(
    payload: RadiusUpdate,
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> ProfileResponse:
    return await service.update_radius(principal.user_id, payload.radius_km)


@router.post("/me/location", summary="Update last recorded location (sent on every app open)")
async def post_location(
    payload: LocationUpdate,
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> dict[str, str]:
    region = await service.update_location(principal.user_id, payload.latitude, payload.longitude)
    return {"h3_region": region}


@router.post(
    "/me/photos/upload-url",
    response_model=PhotoUploadResponse,
    summary="Pre-signed URL for a profile photo",
)
async def photo_upload_url(
    payload: PhotoUploadRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> PhotoUploadResponse:
    extension = payload.content_type.split("/")[1]
    object_key = storage.build_object_key("profile_photo", principal.user_id, extension)
    presigned = await storage.get_storage().presign_upload(object_key, payload.content_type)
    return PhotoUploadResponse(
        upload_url=storage.absolutize(presigned.upload_url, str(request.base_url)),
        object_key=presigned.object_key,
        expires_at=presigned.expires_at,
        # Where the photo will be readable once uploaded, so the client can show it back and
        # store it on the profile without reconstructing the URL itself.
        public_url=storage.absolutize(
            await storage.get_storage().presign_download(object_key), str(request.base_url)
        ),
    )


# ---------------------------------------------------------------------------
# Account lifecycle (§6)
# ---------------------------------------------------------------------------

@router.delete("/me", response_model=DeleteAccountResponse, summary="Start the 30-day grace period")
async def delete_me(
    principal: Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))],
) -> DeleteAccountResponse:
    deleted_at, restorable_until = await service.request_deletion(principal.user_id)
    return DeleteAccountResponse(
        deleted_at=deleted_at,
        restorable_until=restorable_until,
        message=(
            "Your profile is hidden immediately and removed from all queues. You can restore "
            "it within 30 days; after that everything is permanently deleted."
        ),
    )


@router.post("/me/restore", response_model=RestoreAccountResponse, summary="Restore within grace")
async def restore_me(
    principal: Annotated[Principal, Depends(current_principal)],
) -> RestoreAccountResponse:
    status_after = await service.restore_account(principal.user_id)
    return RestoreAccountResponse(
        status=status_after,
        message="Welcome back. We are finding your place in your region again.",
    )
