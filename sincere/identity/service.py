"""Identity business logic (FR-1.1-1.7, §5 auth flow, §6 lifecycle, §9 AI pipeline)."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sincere.identity import biometrics, risk
from sincere.identity import repository as repo
from sincere.identity.schemas import (
    Gender,
    LivenessSessionResponse,
    ProfileResponse,
    RiskBand,
    TokenResponse,
    UserStatus,
    VerificationStatusResponse,
)
from sincere.shared import storage
from sincere.shared.audit import AuditAction, record
from sincere.shared.auth import (
    Scope,
    create_access_token,
    create_refresh_token,
    hash_phone,
    hash_token,
)
from sincere.shared.config import Settings, Thresholds, get_settings
from sincere.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ProblemException,
    ValidationError,
)
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# §5 Authentication flow
# ---------------------------------------------------------------------------

async def start_signup(phone: str) -> tuple[str, int, str | None]:
    """``POST /auth/signup`` — issue an OTP. Returns (challenge_id, ttl, dev_otp)."""
    settings = get_settings()
    phone_hash = hash_phone(phone)

    existing = await repo.get_user_by_phone_hash(phone_hash)
    if existing and existing["status"] == str(UserStatus.BANNED):
        # §6: a ban is terminal. Refusing here (rather than at first product action) also
        # avoids issuing a token to a banned account.
        raise ForbiddenError(
            "Account unavailable",
            "This account cannot be used. Contact support if you believe this is an error.",
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = await repo.create_otp_challenge(
        phone_hash=phone_hash, otp_hash=hash_token(otp), ttl_seconds=OTP_TTL_SECONDS
    )

    await _deliver_otp(phone, otp, settings)

    # §22 forbids logging OTPs. The dev echo below is gated on the console provider, which
    # the production settings guard prevents from being selected there.
    is_console_dev = settings.sms_provider == "console" and settings.environment != "production"
    dev_otp = otp if is_console_dev else None
    return challenge_id, OTP_TTL_SECONDS, dev_otp


async def _deliver_otp(phone: str, otp: str, settings: Settings) -> None:
    """§17: SMS carries OTP only — never marketing or engagement messages."""
    if settings.sms_provider == "console":
        # Printed, not logged: the §22 redaction filter would strip it from a log record,
        # and it must never reach a log store even in development.
        print(f"[dev-otp] {phone} -> {otp}")  # noqa: T201
        return

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.sms_account_sid}/Messages.json",
            auth=(settings.sms_account_sid, settings.sms_auth_token),
            data={
                "To": phone,
                "From": settings.sms_from_number,
                "Body": f"{otp} is your Sincère verification code. It expires in 5 minutes.",
            },
        )
        if response.status_code >= 400:
            logger.error("otp.delivery_failed", extra={"status": response.status_code})
            raise ProblemException(
                status=502,
                title="Could not send code",
                detail="We could not send your verification code. Please try again.",
                type_="/errors/otp-delivery",
            )


async def verify_otp(
    challenge_id: str, otp: str, *, device_fingerprint: str | None, ip: str | None
) -> TokenResponse:
    """``POST /auth/verify-otp`` → onboarding-scope tokens (§5)."""
    challenge = await repo.get_otp_challenge(challenge_id)
    if challenge is None:
        raise NotFoundError("Verification code", "This code has expired. Request a new one.")
    if challenge.get("consumed"):
        raise ConflictError("Code already used", "Request a new verification code.")

    attempts = await repo.increment_otp_attempts(challenge_id)
    if attempts > OTP_MAX_ATTEMPTS:
        # Brute-force guard on a 6-digit space; the §18 rate limit covers issuance, this
        # covers redemption.
        await repo.consume_otp_challenge(challenge_id)
        raise ForbiddenError("Too many attempts", "Request a new verification code.")

    if not secrets.compare_digest(challenge["otp_hash"], hash_token(otp)):
        raise ValidationError("That code is not correct.")

    await repo.consume_otp_challenge(challenge_id)

    user = await repo.get_user_by_phone_hash(challenge["phone_hash"])
    if user is None:
        user = await repo.create_user(phone_hash=challenge["phone_hash"])
    else:
        await repo.touch_login(user["_id"])

    await repo.record_device_signal(
        user_id=user["_id"], fingerprint=device_fingerprint, ip=ip, event_type="signup"
    )

    return await issue_tokens(user)


async def issue_tokens(user: dict[str, Any]) -> TokenResponse:
    """Mint a token pair whose scope mirrors the user's lifecycle state (§5)."""
    settings = get_settings()
    status = UserStatus(user["status"])
    scope = scope_for_status(status)

    access = create_access_token(
        user["_id"], scope, gender=user.get("gender"), region=user.get("h3_region")
    )
    refresh, family_id = create_refresh_token(user["_id"])
    await repo.store_refresh_token(
        token_hash=hash_token(refresh),
        user_id=user["_id"],
        family_id=family_id,
        ttl_seconds=settings.jwt_refresh_ttl,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_ttl,
        scope=str(scope),
        status=status,
    )


def scope_for_status(status: UserStatus) -> Scope:
    """The §6 state → §5 scope mapping, in one place."""
    return {
        UserStatus.ONBOARDING: Scope.ONBOARDING,
        UserStatus.PENDING_REVIEW: Scope.PENDING_REVIEW,
        UserStatus.WAITLISTED: Scope.WAITLISTED,
        UserStatus.ACTIVE: Scope.ACTIVE,
        UserStatus.INACTIVE: Scope.ACTIVE,  # §6: inactive affects ratio counts only
        UserStatus.GRACE_PERIOD: Scope.ACTIVE,  # restorable until hard delete
    }.get(status, Scope.ONBOARDING)


async def refresh_tokens(refresh_token: str) -> TokenResponse:
    """``POST /auth/refresh`` — rotation with reuse detection (§5).

    "A replayed refresh token revokes the family." A token already marked used means either
    an attacker replayed a stolen token or the legitimate client is replaying one; either way
    the family is no longer trustworthy, so every token in it dies.
    """
    token_hash = hash_token(refresh_token)
    stored = await repo.find_refresh_token(token_hash)

    if stored is None:
        raise ProblemException(
            status=401,
            title="Invalid refresh token",
            detail="Sign in again.",
            type_="/errors/invalid-refresh",
        )

    if stored.get("used"):
        revoked = await repo.revoke_token_family(stored["family_id"])
        logger.warning(
            "auth.refresh_reuse_detected",
            extra={"user_id": stored["user_id"], "revoked_tokens": revoked},
        )
        raise ProblemException(
            status=401,
            title="Session revoked",
            detail=(
                "This session has been revoked for your security because a sign-in token "
                "was reused. Please sign in again."
            ),
            type_="/errors/refresh-reuse",
        )

    if stored["expires_at"] < datetime.now(UTC):
        raise ProblemException(
            status=401, title="Session expired", detail="Sign in again.", type_="/errors/expired"
        )

    await repo.mark_refresh_token_used(token_hash)

    user = await repo.get_user(stored["user_id"])
    if user is None:
        raise NotFoundError("Account")

    settings = get_settings()
    status = UserStatus(user["status"])
    scope = scope_for_status(status)
    access = create_access_token(
        user["_id"], scope, gender=user.get("gender"), region=user.get("h3_region")
    )
    # Rotation stays inside the same family, so a later replay of ANY member is detectable.
    new_refresh, _ = create_refresh_token(user["_id"], stored["family_id"])
    await repo.store_refresh_token(
        token_hash=hash_token(new_refresh),
        user_id=user["_id"],
        family_id=stored["family_id"],
        ttl_seconds=settings.jwt_refresh_ttl,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_ttl,
        scope=str(scope),
        status=status,
    )


# ---------------------------------------------------------------------------
# Profile (§7 Profile & Location)
# ---------------------------------------------------------------------------

async def get_profile(user_id: str) -> ProfileResponse:
    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Profile")
    return _to_profile_response(user)


def _to_profile_response(user: dict[str, Any]) -> ProfileResponse:
    profile = user.get("profile", {})
    graduation = user.get("graduation", {})
    return ProfileResponse(
        user_id=user["_id"],
        status=UserStatus(user["status"]),
        gender=Gender(user["gender"]) if user.get("gender") else Gender.FEMALE,
        name=profile.get("name"),
        dob=profile.get("dob"),
        bio=profile.get("bio"),
        prompts=profile.get("prompts", []),
        tags=profile.get("tags", []),
        photos=profile.get("photos", []),
        radius_km=user.get("radius_km", 25),
        h3_region=user.get("h3_region"),
        graduated=graduation.get("graduated_at") is not None,
        swipe_count=graduation.get("swipes", 0),
        match_count=graduation.get("matches", 0),
    )


async def update_profile(user_id: str, changes: dict[str, Any]) -> ProfileResponse:
    """``PATCH /me``. Profile edits invalidate the cached feature vectors that §16 keeps for
    nightly scoring — tags and prompts are inputs to ``preference_similarity`` and
    ``prompt_text_similarity`` (§12)."""
    updates = {f"profile.{key}": value for key, value in changes.items() if value is not None}
    if not updates:
        return await get_profile(user_id)

    user = await repo.update_user(user_id, updates)
    if user is None:
        raise NotFoundError("Profile")

    if {"profile.tags", "profile.prompts"} & set(updates):
        from sincere.shared import cache

        await cache.invalidate(cache.Keys.user_features(user_id))

    return _to_profile_response(user)


async def set_gender(user_id: str, gender: Gender) -> None:
    """Gender is write-once: it determines which pool the user is admitted against (FR-2.4),
    and letting it change would corrupt every hex's ratio counters retroactively."""
    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Profile")
    if user.get("gender"):
        raise ConflictError(
            "Gender already set",
            "Contact support if this needs to change — it affects how you were admitted.",
        )
    await repo.update_user(user_id, {"gender": str(gender)})


async def update_radius(user_id: str, radius_km: int) -> ProfileResponse:
    """``PATCH /me/radius`` (FR-3.2). Affects the candidate pool only — never queue position."""
    user = await repo.update_user(user_id, {"radius_km": radius_km})
    if user is None:
        raise NotFoundError("Profile")
    return _to_profile_response(user)


async def update_location(user_id: str, latitude: float, longitude: float) -> str:
    """``POST /me/location``, called on every app open (FR-3.3).

    §18 location minimalism: this OVERWRITES ``last_recorded_location``. No history is kept.
    The H3 cell is derived server-side (FR-2.1) rather than trusted from the client.

    Returns the H3 cell. Note the two-geography separation (README §2): the H3 cell is the
    *admission* region and is assigned once at first location; the radius pool is computed
    from the live coordinates. Moving across the city does not re-queue you.
    """
    import h3

    thresholds = await load_thresholds()
    cell = h3.latlng_to_cell(latitude, longitude, thresholds.h3_resolution)

    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Profile")

    updates: dict[str, Any] = {
        "last_recorded_location": {"type": "Point", "coordinates": [longitude, latitude]},
        "activity.last_login_at": datetime.now(UTC),
    }
    # First location fixes the admission region for the account's life.
    if not user.get("h3_region"):
        updates["h3_region"] = cell

    await repo.update_user(user_id, updates)
    return user.get("h3_region") or cell


# ---------------------------------------------------------------------------
# §9 Verification pipeline
# ---------------------------------------------------------------------------

async def start_liveness_session(user_id: str) -> LivenessSessionResponse:
    """§5: hand the client a randomized prompt sequence + a pre-signed upload URL."""
    from uuid import uuid4

    sequence = biometrics.random_prompt_sequence()
    object_key = storage.build_object_key("liveness", user_id, "mp4")
    presigned = await storage.get_storage().presign_upload(object_key, "video/mp4")

    session_id = str(uuid4())
    from sincere.shared import cache

    await cache.set_json(
        f"liveness:{session_id}",
        {"user_id": user_id, "sequence": sequence, "object_key": object_key},
        ttl=900,
    )

    return LivenessSessionResponse(
        session_id=session_id,
        prompt_sequence=sequence,
        upload_url=presigned.upload_url,
        object_key=object_key,
        expires_at=presigned.expires_at,
    )


async def submit_liveness(
    user_id: str, session_id: str, object_key: str
) -> VerificationStatusResponse:
    """``POST /verification/liveness`` — runs the FR-1.2-1.6 pipeline.

    Order matters and follows §5's sequence diagram:
      liveness check → FaceNet embedding → duplicate search → photo-selfie match → risk score
    """
    from sincere.shared import cache

    session = await cache.get_json(f"liveness:{session_id}")
    if session is None or session["user_id"] != user_id:
        raise NotFoundError("Liveness session", "Start the verification again.")
    if session["object_key"] != object_key:
        raise ValidationError("The uploaded capture does not match this session.")

    thresholds = await load_thresholds()
    settings = get_settings()

    signals = risk.RiskSignals()
    vector: list[float] | None = None
    liveness_result: dict[str, Any] = {"prompts": session["sequence"]}

    if settings.biometric_pipeline_enabled:
        vector, signals, liveness_result = await _run_biometric_pipeline(
            user_id, object_key, session["sequence"], thresholds
        )
    else:
        # §9:484 legal gate closed. Rather than skipping verification (which would let
        # unverified accounts through), every signup routes to the human queue.
        logger.info("identity.biometric_gate_closed", extra={"user_id": user_id})
        liveness_result["skipped"] = "biometric pipeline disabled pending legal review (§9:484)"

    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Account")

    signals.bio_text = user.get("profile", {}).get("bio", "") or ""
    signals.device_reuse_count = await _device_reuse(user_id)
    signals.ip_cluster_count = await _ip_cluster(user_id)
    signals.signup_velocity = await repo.count_recent_signups()

    assessment = risk.score(signals, thresholds)

    # §9 forces review when the gate is closed — there is no automated evidence to approve on.
    band = assessment.band if settings.biometric_pipeline_enabled else RiskBand.REVIEW

    await repo.store_capture(
        user_id=user_id,
        object_key=object_key,
        prompt_sequence=session["sequence"],
        liveness_result=liveness_result,
        retention_days=thresholds.verification_capture_retention_days,
    )
    if vector is not None:
        await repo.store_embedding(user_id, vector)

    flag_id = await repo.create_risk_flag(
        user_id=user_id,
        composite_score=assessment.composite_score,
        band=band,
        signals={
            "duplicate_sim": signals.duplicate_similarity,
            "device_reuse": signals.device_reuse_count,
            "ip_cluster": signals.ip_cluster_count,
            "signup_velocity": signals.signup_velocity,
            "bio_template": assessment.normalized.get("bio_template"),
            "photo_selfie": signals.photo_selfie_match,
            "liveness": signals.liveness_passed,
        },
    )

    await cache.invalidate(f"liveness:{session_id}")
    return await _apply_verification_outcome(user_id, band, flag_id, assessment)


async def _run_biometric_pipeline(
    user_id: str, object_key: str, sequence: list[str], thresholds: Thresholds
) -> tuple[list[float] | None, risk.RiskSignals, dict[str, Any]]:
    """§9: embed, search for duplicates, compare against profile photos.

    The image buffer is dropped as soon as the vector exists — §18's "image buffer discarded
    post-embedding", enforced here rather than trusted to the storage lifecycle.
    """
    signals = risk.RiskSignals()
    result: dict[str, Any] = {"prompts": sequence}

    try:
        capture_bytes = await storage.get_storage().read(object_key)
        provider = biometrics.get_provider()
        vector = provider.embed(capture_bytes)
        del capture_bytes  # §18 data minimization
        signals.liveness_passed = True
        result["passed"] = True
    except biometrics.BiometricPipelineDisabled:
        raise
    except Exception as exc:  # noqa: BLE001 — a failed embed is a signal, not a 500
        logger.warning("identity.embedding_failed", extra={"error": str(exc)})
        signals.liveness_passed = False
        result["passed"] = False
        result["error"] = "no usable face detected in the capture"
        return None, signals, result

    duplicates = await biometrics.find_duplicates(
        vector,
        exclude_user_id=user_id,
        threshold=thresholds.duplicate_similarity_threshold,
    )
    if duplicates:
        signals.duplicate_similarity = duplicates[0].similarity
        result["duplicate_of"] = duplicates[0].user_id

    signals.photo_selfie_match = await _photo_matches(user_id, vector, thresholds)
    return vector, signals, result


async def _photo_matches(
    user_id: str, selfie_vector: list[float], thresholds: Thresholds
) -> bool | None:
    """FR-1.5. Returns ``None`` when there are no photos to compare against yet."""
    user = await repo.get_user(user_id)
    photos = (user or {}).get("profile", {}).get("photos", [])
    if not photos:
        return None

    provider = biometrics.get_provider()
    for photo in photos:
        try:
            photo_bytes = await storage.get_storage().read(photo["object_key"])
            photo_vector = provider.embed(photo_bytes)
            del photo_bytes
            if biometrics.photo_matches_selfie(
                photo_vector, selfie_vector, thresholds.photo_selfie_match_threshold
            ):
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("identity.photo_compare_failed", extra={"error": str(exc)})
    return False


async def _device_reuse(user_id: str) -> int:
    from sincere.shared.db import C, collection

    signal = await collection(C.DEVICE_SIGNALS).find_one({"user_id": user_id})
    fingerprint = (signal or {}).get("fingerprint")
    return await repo.count_fingerprint_reuse(fingerprint, user_id) if fingerprint else 0


async def _ip_cluster(user_id: str) -> int:
    from sincere.shared.db import C, collection

    signal = await collection(C.DEVICE_SIGNALS).find_one({"user_id": user_id})
    ip = (signal or {}).get("ip")
    return await repo.count_ip_cluster(ip, user_id) if ip else 0


async def _apply_verification_outcome(
    user_id: str, band: RiskBand, flag_id: str, assessment: risk.RiskAssessment
) -> VerificationStatusResponse:
    """Route the three bands (FR-1.6) and emit ``UserVerified`` on approval (§14)."""
    now = datetime.now(UTC)

    if band is RiskBand.AUTO_APPROVE:
        await repo.set_status(user_id, UserStatus.PENDING_REVIEW)
        await record(
            AuditAction.VERIFICATION_AUTO_APPROVED,
            subject_id=user_id,
            context={"composite_score": assessment.composite_score, "flag_id": flag_id},
        )
        # admission decides activate-vs-waitlist from the hex ratio (§14).
        await bus.emit(Event.USER_VERIFIED, {"user_id": user_id})
        return VerificationStatusResponse(
            status=UserStatus.PENDING_REVIEW,
            band=band,
            submitted_at=now,
            decided_at=now,
            message="You are verified. Finding your place now.",
        )

    if band is RiskBand.AUTO_REJECT:
        await repo.set_status(user_id, UserStatus.REJECTED)
        await record(
            AuditAction.VERIFICATION_AUTO_REJECTED,
            subject_id=user_id,
            context={
                "composite_score": assessment.composite_score,
                "reasons": assessment.reasons,
                "flag_id": flag_id,
            },
        )
        return VerificationStatusResponse(
            status=UserStatus.REJECTED,
            band=band,
            submitted_at=now,
            decided_at=now,
            message="We could not verify this account.",
        )

    await repo.set_status(user_id, UserStatus.PENDING_REVIEW)
    await record(
        AuditAction.VERIFICATION_QUEUED_FOR_REVIEW,
        subject_id=user_id,
        context={
            "composite_score": assessment.composite_score,
            "reasons": assessment.reasons,
            "flag_id": flag_id,
        },
    )
    return VerificationStatusResponse(
        status=UserStatus.PENDING_REVIEW,
        band=band,
        submitted_at=now,
        message="A person is reviewing your verification. This usually takes a few hours.",
    )


async def verification_status(user_id: str) -> VerificationStatusResponse:
    """``GET /verification/status``."""
    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Account")

    status = UserStatus(user["status"])
    flag = await repo.latest_risk_flag(user_id)

    messages = {
        UserStatus.ONBOARDING: "Complete your profile and verification to continue.",
        UserStatus.PENDING_REVIEW: "A person is reviewing your verification.",
        UserStatus.REJECTED: "We could not verify this account.",
        UserStatus.WAITLISTED: "You are verified and on the waitlist.",
        UserStatus.ACTIVE: "You are verified and active.",
    }
    return VerificationStatusResponse(
        status=status,
        band=RiskBand(flag["band"]) if flag else None,
        submitted_at=flag.get("created_at") if flag else None,
        decided_at=(flag.get("review") or {}).get("decided_at") if flag else None,
        message=messages.get(status, "Verification in progress."),
    )


# ---------------------------------------------------------------------------
# FR-1.7 human review
# ---------------------------------------------------------------------------

async def decide_review(
    *, flag_id: str, reviewer_id: str, decision: str, note: str | None
) -> dict[str, Any]:
    """Apply a human review decision, logging score agreement (FR-1.7, FR-8.2).

    "Agreement" is derived, not self-reported: an approve agrees with the score when the
    score sat in the lower half of the review band. That derived signal is what retunes the
    FR-1.6 thresholds, so a reviewer cannot skew it by mislabelling their own decision.
    """
    flag = await repo.get_risk_flag(flag_id)
    if flag is None:
        raise NotFoundError("Review item")
    if (flag.get("review") or {}).get("decided_at"):
        raise ConflictError("Already decided", "This account has already been reviewed.")

    thresholds = await load_thresholds()
    midpoint = (thresholds.bot_risk_auto_approve_below + thresholds.bot_risk_auto_reject_above) / 2
    score_leaned_approve = flag["composite_score"] < midpoint
    agreed = (decision == "approve") == score_leaned_approve

    await repo.record_review_decision(
        flag_id=flag_id,
        decided_by=reviewer_id,
        decision=decision,
        agreed_with_score=agreed,
        note=note,
    )

    user_id = flag["user_id"]
    if decision == "approve":
        await bus.emit(Event.USER_VERIFIED, {"user_id": user_id})
    else:
        await repo.set_status(user_id, UserStatus.REJECTED)

    await record(
        AuditAction.REVIEW_DECISION,
        actor_id=reviewer_id,
        subject_id=user_id,
        context={
            "flag_id": flag_id,
            "decision": decision,
            "composite_score": flag["composite_score"],
            "agreed_with_score": agreed,
            "note": note,
        },
    )
    logger.info(
        "identity.review_decided",
        extra={"decision": decision, "agreed_with_score": agreed},
    )
    return {"flag_id": flag_id, "decision": decision, "agreed_with_score": agreed}


# ---------------------------------------------------------------------------
# §6 Account deletion cascade
# ---------------------------------------------------------------------------

async def request_deletion(user_id: str) -> tuple[datetime, datetime]:
    """``DELETE /me`` — §6: immediate hide + pool/queue removal, then a 30-day recoverable
    soft delete. The hard delete itself is the retention job's work (§15b)."""
    thresholds = await load_thresholds()
    now = datetime.now(UTC)
    restorable_until = now + timedelta(days=thresholds.grace_period_days)

    await repo.update_user(
        user_id,
        {
            "status": str(UserStatus.GRACE_PERIOD),
            "deleted_at": now,
            "hard_delete_after": restorable_until,
        },
    )
    await repo.revoke_all_user_tokens(user_id)

    # Every module removes the user from its own pools and queues (§14).
    await bus.emit(Event.ACCOUNT_DELETION_REQUESTED, {"user_id": user_id})
    await record(
        AuditAction.DELETION_REQUESTED,
        subject_id=user_id,
        context={"restorable_until": restorable_until.isoformat()},
    )
    return now, restorable_until


async def restore_account(user_id: str) -> UserStatus:
    """``POST /me/restore`` — within the grace period (§6)."""
    user = await repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Account")
    if user["status"] != str(UserStatus.GRACE_PERIOD):
        raise ConflictError("Not deleted", "This account is not scheduled for deletion.")
    if user.get("hard_delete_after") and user["hard_delete_after"] < datetime.now(UTC):
        raise ConflictError(
            "Grace period expired", "This account can no longer be restored."
        )

    # Restore to waitlisted, never straight to active: the hex ratio has moved on while the
    # account was hidden, and admission (FR-2.4) must re-decide rather than be bypassed.
    await repo.update_user(
        user_id,
        {"status": str(UserStatus.WAITLISTED), "deleted_at": None, "hard_delete_after": None},
    )
    await bus.emit(Event.USER_VERIFIED, {"user_id": user_id})
    await record(AuditAction.DELETION_RESTORED, subject_id=user_id)
    return UserStatus.WAITLISTED


async def hard_delete(user_id: str) -> dict[str, int]:
    """Execute the §6 cascade. Called by the retention job (§15b) after the grace period.

    §18 "bounded genuine deletion" — the embedding and captures really go. The one deliberate
    exception is a banned user's embedding, retained for account lifetime so a re-signup is
    caught by the duplicate check (§6).
    """
    user = await repo.get_user(user_id)
    if user is None:
        return {"users": 0}

    was_banned = user["status"] == str(UserStatus.BANNED)
    removed: dict[str, int] = {}

    await repo.delete_captures(user_id)
    removed["captures"] = 1

    if not was_banned:
        await repo.delete_embedding(user_id)
        removed["embeddings"] = 1
    else:
        logger.info("identity.embedding_retained_for_ban", extra={"user_id": user_id})
        removed["embeddings"] = 0

    deleted_objects = await storage.get_storage().delete_prefix(
        f"{storage.PREFIXES['liveness']}/{user_id}"
    )
    deleted_objects += await storage.get_storage().delete_prefix(
        f"{storage.PREFIXES['profile_photo']}/{user_id}"
    )
    removed["objects"] = deleted_objects

    from sincere.shared.db import C, collection

    await collection(C.USERS).delete_one({"_id": user_id})
    removed["users"] = 1

    await repo.revoke_all_user_tokens(user_id)
    await record(AuditAction.HARD_DELETE_EXECUTED, subject_id=user_id, context=removed)
    return removed
