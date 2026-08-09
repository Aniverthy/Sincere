"""MongoDB access for the identity module.

§3 rule 1: this module owns ``users``, ``embeddings``, ``verification_captures``,
``bot_risk_flags``, ``otp_challenges`` and ``refresh_tokens``. No other module writes them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sincere.identity.schemas import Gender, RiskBand, UserStatus
from sincere.shared.db import C, collection

# ---------------------------------------------------------------------------
# OTP challenges (§5)
# ---------------------------------------------------------------------------

async def create_otp_challenge(phone_hash: str, otp_hash: str, ttl_seconds: int) -> str:
    challenge_id = str(uuid4())
    now = datetime.now(UTC)
    await collection(C.OTP_CHALLENGES).insert_one(
        {
            "_id": challenge_id,
            "phone_hash": phone_hash,
            "otp_hash": otp_hash,
            "attempts": 0,
            "consumed": False,
            "created_at": now,
            "expires_at": now + timedelta(seconds=ttl_seconds),
        }
    )
    return challenge_id


async def get_otp_challenge(challenge_id: str) -> dict[str, Any] | None:
    return await collection(C.OTP_CHALLENGES).find_one({"_id": challenge_id})


async def increment_otp_attempts(challenge_id: str) -> int:
    doc = await collection(C.OTP_CHALLENGES).find_one_and_update(
        {"_id": challenge_id}, {"$inc": {"attempts": 1}}, return_document=True
    )
    return int(doc.get("attempts", 0)) if doc else 0


async def consume_otp_challenge(challenge_id: str) -> None:
    await collection(C.OTP_CHALLENGES).update_one(
        {"_id": challenge_id}, {"$set": {"consumed": True, "consumed_at": datetime.now(UTC)}}
    )


# ---------------------------------------------------------------------------
# Refresh tokens (§5 rotation + reuse detection)
# ---------------------------------------------------------------------------

async def store_refresh_token(
    *, token_hash: str, user_id: str, family_id: str, ttl_seconds: int
) -> None:
    now = datetime.now(UTC)
    await collection(C.REFRESH_TOKENS).insert_one(
        {
            "_id": str(uuid4()),
            "token_hash": token_hash,
            "user_id": user_id,
            "family_id": family_id,
            "used": False,
            "created_at": now,
            "expires_at": now + timedelta(seconds=ttl_seconds),
        }
    )


async def find_refresh_token(token_hash: str) -> dict[str, Any] | None:
    return await collection(C.REFRESH_TOKENS).find_one({"token_hash": token_hash})


async def mark_refresh_token_used(token_hash: str) -> None:
    await collection(C.REFRESH_TOKENS).update_one(
        {"token_hash": token_hash}, {"$set": {"used": True, "used_at": datetime.now(UTC)}}
    )


async def revoke_token_family(family_id: str) -> int:
    """§5: a replayed refresh token revokes the entire family.

    Deleting rather than flagging: a revoked family must never authenticate again, and a
    deleted row cannot be resurrected by a bug in a status check.
    """
    result = await collection(C.REFRESH_TOKENS).delete_many({"family_id": family_id})
    return int(result.deleted_count)


async def revoke_all_user_tokens(user_id: str) -> int:
    result = await collection(C.REFRESH_TOKENS).delete_many({"user_id": user_id})
    return int(result.deleted_count)


# ---------------------------------------------------------------------------
# Users (§8)
# ---------------------------------------------------------------------------

async def create_user(*, phone_hash: str, gender: Gender | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "_id": str(uuid4()),
        "phone_hash": phone_hash,
        "gender": str(gender) if gender else None,
        "status": str(UserStatus.ONBOARDING),
        "profile": {
            "name": None, "dob": None, "bio": None,
            "prompts": [], "tags": [], "photos": [],
        },
        "last_recorded_location": None,
        "h3_region": None,
        "radius_km": 25,
        "activity": {
            "last_login_at": now,
            "last_swipe_at": None,
            "is_active_30d": False,
        },
        "graduation": {"swipes": 0, "matches": 0, "graduated_at": None},
        "entry_tier": None,
        "warnings": [],
        "deleted_at": None,
        "hard_delete_after": None,
        "created_at": now,
        "updated_at": now,
    }
    await collection(C.USERS).insert_one(doc)
    return doc


async def get_user(user_id: str) -> dict[str, Any] | None:
    return await collection(C.USERS).find_one({"_id": user_id})


async def get_user_by_phone_hash(phone_hash: str) -> dict[str, Any] | None:
    return await collection(C.USERS).find_one({"phone_hash": phone_hash})


async def update_user(user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    changes["updated_at"] = datetime.now(UTC)
    return await collection(C.USERS).find_one_and_update(
        {"_id": user_id}, {"$set": changes}, return_document=True
    )


async def set_status(user_id: str, status: UserStatus) -> None:
    await collection(C.USERS).update_one(
        {"_id": user_id},
        {"$set": {"status": str(status), "updated_at": datetime.now(UTC)}},
    )


async def touch_login(user_id: str) -> None:
    """FR-2.3: "active" needs a login timestamp AND a swipe in the window. This records the
    login half; matching records the swipe half."""
    await collection(C.USERS).update_one(
        {"_id": user_id}, {"$set": {"activity.last_login_at": datetime.now(UTC)}}
    )


# ---------------------------------------------------------------------------
# Embeddings (§8, §9) — vectors only, never source images
# ---------------------------------------------------------------------------

async def store_embedding(user_id: str, vector: list[float]) -> str:
    """§9/§18: the ``purpose`` field is single-valued by design. Any new use of the vector
    requires a fresh consent flow — it is never repurposed for marketing."""
    embedding_id = str(uuid4())
    await collection(C.EMBEDDINGS).insert_one(
        {
            "_id": embedding_id,
            "user_id": user_id,
            "vector": vector,
            "purpose": "duplicate_and_visual_pattern",
            "created_at": datetime.now(UTC),
        }
    )
    return embedding_id


async def get_embedding(user_id: str) -> dict[str, Any] | None:
    return await collection(C.EMBEDDINGS).find_one({"user_id": user_id})


async def delete_embedding(user_id: str) -> None:
    await collection(C.EMBEDDINGS).delete_many({"user_id": user_id})


# ---------------------------------------------------------------------------
# Verification captures (§8: 30-day soft delete → hard delete)
# ---------------------------------------------------------------------------

async def store_capture(
    *,
    user_id: str,
    object_key: str,
    prompt_sequence: list[str],
    liveness_result: dict[str, Any],
    retention_days: int,
) -> str:
    capture_id = str(uuid4())
    now = datetime.now(UTC)
    await collection(C.VERIFICATION_CAPTURES).insert_one(
        {
            "_id": capture_id,
            "user_id": user_id,
            "object_key": object_key,
            "prompt_sequence": prompt_sequence,
            "liveness_result": liveness_result,
            "created_at": now,
            "hard_delete_after": now + timedelta(days=retention_days),
        }
    )
    return capture_id


async def get_latest_capture(user_id: str) -> dict[str, Any] | None:
    cursor = collection(C.VERIFICATION_CAPTURES).find({"user_id": user_id}).sort("created_at", -1)
    async for doc in cursor:
        return doc
    return None


async def delete_captures(user_id: str) -> None:
    await collection(C.VERIFICATION_CAPTURES).delete_many({"user_id": user_id})


# ---------------------------------------------------------------------------
# Bot-risk flags (FR-1.6, FR-1.7)
# ---------------------------------------------------------------------------

async def create_risk_flag(
    *, user_id: str, composite_score: float, band: RiskBand, signals: dict[str, Any]
) -> str:
    flag_id = str(uuid4())
    await collection(C.BOT_RISK_FLAGS).insert_one(
        {
            "_id": flag_id,
            "user_id": user_id,
            "composite_score": composite_score,
            "band": str(band),
            "signals": signals,
            "review": {
                "decided_by": None,
                "decision": None,
                "agreed_with_score": None,
                "decided_at": None,
            },
            "created_at": datetime.now(UTC),
        }
    )
    return flag_id


async def get_risk_flag(flag_id: str) -> dict[str, Any] | None:
    return await collection(C.BOT_RISK_FLAGS).find_one({"_id": flag_id})


async def latest_risk_flag(user_id: str) -> dict[str, Any] | None:
    cursor = collection(C.BOT_RISK_FLAGS).find({"user_id": user_id}).sort("created_at", -1)
    async for doc in cursor:
        return doc
    return None


async def list_review_queue(limit: int = 50) -> list[dict[str, Any]]:
    """FR-8.1: the review queue is exactly the undecided ambiguous band."""
    cursor = (
        collection(C.BOT_RISK_FLAGS)
        .find({"band": str(RiskBand.REVIEW), "review.decided_at": None})
        .sort("created_at", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def record_review_decision(
    *, flag_id: str, decided_by: str, decision: str, agreed_with_score: bool, note: str | None
) -> dict[str, Any] | None:
    """FR-1.7: every decision logs agreement/disagreement with the automated score, which is
    what feeds the FR-1.6 threshold retuning loop."""
    return await collection(C.BOT_RISK_FLAGS).find_one_and_update(
        {"_id": flag_id},
        {
            "$set": {
                "review.decided_by": decided_by,
                "review.decision": decision,
                "review.agreed_with_score": agreed_with_score,
                "review.decided_at": datetime.now(UTC),
                "review.note": note,
            }
        },
        return_document=True,
    )


# ---------------------------------------------------------------------------
# Device signals (FR-5.4) — written here at signup, read by antiabuse
# ---------------------------------------------------------------------------

async def record_device_signal(
    *, user_id: str, fingerprint: str | None, ip: str | None, event_type: str
) -> None:
    await collection(C.DEVICE_SIGNALS).insert_one(
        {
            "_id": str(uuid4()),
            "user_id": user_id,
            "fingerprint": fingerprint,
            "ip": ip,
            "event_type": event_type,
            "created_at": datetime.now(UTC),
        }
    )


async def count_fingerprint_reuse(fingerprint: str, exclude_user_id: str) -> int:
    """FR-5.4 device-reuse signal: how many *other* accounts share this fingerprint."""
    if not fingerprint:
        return 0
    users = await collection(C.DEVICE_SIGNALS).distinct(
        "user_id", {"fingerprint": fingerprint, "user_id": {"$ne": exclude_user_id}}
    )
    return len(users)


async def count_ip_cluster(ip: str, exclude_user_id: str, window_days: int = 7) -> int:
    """FR-5.4 IP-clustering signal: distinct accounts from one IP in a recent window."""
    if not ip:
        return 0
    since = datetime.now(UTC) - timedelta(days=window_days)
    users = await collection(C.DEVICE_SIGNALS).distinct(
        "user_id", {"ip": ip, "user_id": {"$ne": exclude_user_id}, "created_at": {"$gte": since}}
    )
    return len(users)


async def count_recent_signups(window_hours: int = 1) -> int:
    """FR-5.4 signup-velocity signal."""
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    return await collection(C.USERS).count_documents({"created_at": {"$gte": since}})
