"""Public interface of the identity module.

Other modules may import ONLY from this file — never from module internals (§3 rule 2).
Cross-module reactions go through domain events (``sincere/shared/events.py``, §3 rule 3).

Enforced by the import-linter contract "identity internals are private" in ``pyproject.toml``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sincere.identity import repository as _repo
from sincere.identity import service as _service
from sincere.identity.schemas import EntryTier, Gender, UserStatus


class UserSummary(TypedDict):
    """The user facts other modules are allowed to see.

    Deliberately narrow. Notably absent: ``phone_hash`` (nobody else needs it), the embedding
    vector (§9 purpose limitation), and the warnings ledger (antiabuse owns that history).
    """

    user_id: str
    status: str
    gender: str | None
    h3_region: str | None
    radius_km: int
    entry_tier: str | None
    is_active_30d: bool
    created_at: datetime | None


async def get_user_summary(user_id: str) -> UserSummary | None:
    """Fetch the cross-module view of a user. Returns ``None`` if no such account."""
    user = await _repo.get_user(user_id)
    if user is None:
        return None
    return _summarize(user)


async def get_user_summaries(user_ids: list[str]) -> dict[str, UserSummary]:
    """Batch form. Matching resolves whole candidate pools, so the N+1 shape matters (§19)."""
    from sincere.shared.db import C, collection

    cursor = collection(C.USERS).find({"_id": {"$in": user_ids}})
    return {doc["_id"]: _summarize(doc) async for doc in cursor}


def _summarize(user: dict[str, Any]) -> UserSummary:
    return UserSummary(
        user_id=user["_id"],
        status=user["status"],
        gender=user.get("gender"),
        h3_region=user.get("h3_region"),
        radius_km=user.get("radius_km", 25),
        entry_tier=user.get("entry_tier"),
        is_active_30d=bool(user.get("activity", {}).get("is_active_30d")),
        created_at=user.get("created_at"),
    )


async def get_profile_card(user_id: str) -> dict[str, Any] | None:
    """The public-facing profile shown to another user.

    Excludes everything privacy-sensitive: no phone, no exact coordinates, no verification
    record. ``entry_tier`` is NOT included here — FR-6.3 gates it behind a Pro subscription,
    and monetization owns that check.
    """
    user = await _repo.get_user(user_id)
    if user is None or user["status"] in {str(UserStatus.BANNED), str(UserStatus.GRACE_PERIOD)}:
        return None

    profile = user.get("profile", {})
    dob = profile.get("dob")
    return {
        "user_id": user["_id"],
        "name": profile.get("name"),
        "age": _age(dob),
        "bio": profile.get("bio"),
        "prompts": profile.get("prompts", []),
        "tags": profile.get("tags", []),
        "photos": [{"url": p.get("url")} for p in profile.get("photos", [])],
        "created_at": user.get("created_at"),
    }


def _age(dob: Any) -> int | None:
    if not dob:
        return None
    if isinstance(dob, str):
        dob = datetime.fromisoformat(dob).date()
    if isinstance(dob, datetime):
        dob = dob.date()
    today = datetime.now(UTC).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


async def get_location(user_id: str) -> dict[str, Any] | None:
    """GeoJSON point for the candidate-pool ``$geoNear`` query (§11 step 1)."""
    user = await _repo.get_user(user_id)
    return (user or {}).get("last_recorded_location")


async def set_entry_tier(user_id: str, tier: EntryTier) -> None:
    """Record how a man entered (FR-6.3). Called by admission on activation.

    FR-2.11 is the rule this must not violate: entry tier carries **no compatibility-score
    advantage**. It is a visibility attribute only.
    """
    await _repo.update_user(user_id, {"entry_tier": str(tier)})


async def mark_active(user_id: str) -> None:
    """Transition a verified user to active. Called by admission on admission (§14)."""
    await _repo.set_status(user_id, UserStatus.ACTIVE)


async def mark_waitlisted(user_id: str) -> None:
    """Called by admission when the hex is at its ratio ceiling (FR-2.4)."""
    await _repo.set_status(user_id, UserStatus.WAITLISTED)


async def mark_banned(user_id: str) -> None:
    """Called by antiabuse after the third warning (FR-5.3).

    §6: the embedding is deliberately retained for account lifetime so that a re-signup is
    caught by the FR-1.4 duplicate check. :func:`sincere.identity.service.hard_delete`
    honours this.
    """
    await _repo.set_status(user_id, UserStatus.BANNED)
    await _repo.revoke_all_user_tokens(user_id)


async def record_swipe_activity(user_id: str) -> None:
    """FR-2.3: "active" requires a login AND a swipe within the window. Matching calls this
    on every swipe so the ratio denominators stay honest."""
    from sincere.shared.db import C, collection

    now = datetime.now(UTC)
    await collection(C.USERS).update_one(
        {"_id": user_id},
        {"$set": {"activity.last_swipe_at": now, "activity.is_active_30d": True}},
    )


async def recompute_active_flag(user_id: str, window_days: int = 30) -> bool:
    """Re-evaluate FR-2.3's active definition for one user. Returns the new flag.

    §6: going inactive drops the user out of the ratio numerator/denominator **only** — the
    account, matches and chats are untouched.
    """
    user = await _repo.get_user(user_id)
    if user is None:
        return False

    activity = user.get("activity", {})
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    last_login = activity.get("last_login_at")
    last_swipe = activity.get("last_swipe_at")

    is_active = bool(
        last_login and last_login >= cutoff and last_swipe and last_swipe >= cutoff
    )
    if is_active != activity.get("is_active_30d"):
        await _repo.update_user(user_id, {"activity.is_active_30d": is_active})
    return is_active


async def get_embedding_vector(user_id: str) -> list[float] | None:
    """The face embedding, for the §12 ``visual_pattern_similarity`` term ONLY.

    §9 purpose limitation: duplicate detection and per-user visual-pattern matching are the
    two sanctioned uses. Never marketing, and never decomposed into named facial features.
    """
    doc = await _repo.get_embedding(user_id)
    return doc.get("vector") if doc else None


async def get_embedding_vectors(user_ids: list[str]) -> dict[str, list[float]]:
    """Batch form for building a user's liked-profile centroid (§16 cached feature vectors)."""
    from sincere.shared.db import C, collection

    cursor = collection(C.EMBEDDINGS).find({"user_id": {"$in": user_ids}})
    return {doc["user_id"]: doc["vector"] async for doc in cursor}


async def hard_delete_user(user_id: str) -> dict[str, int]:
    """Execute the §6 deletion cascade for identity-owned data. Called by the retention job."""
    return await _service.hard_delete(user_id)


async def list_review_queue(limit: int = 50) -> list[dict[str, Any]]:
    """FR-8.1 admin review queue — the undecided ambiguous band only."""
    return await _repo.list_review_queue(limit)


async def decide_review(
    *, flag_id: str, reviewer_id: str, decision: str, note: str | None = None
) -> dict[str, Any]:
    """FR-8.2: approve/reject with score-agreement logging."""
    return await _service.decide_review(
        flag_id=flag_id, reviewer_id=reviewer_id, decision=decision, note=note
    )


async def count_by_region_and_gender(h3_region: str, gender: Gender, active_only: bool) -> int:
    """Ratio counts for a hex (FR-2.3, FR-2.4).

    Admission calls this for the hourly full recount that §19 prescribes as drift correction
    against its event-maintained counters.
    """
    from sincere.shared.db import C, collection

    query: dict[str, Any] = {
        "h3_region": h3_region,
        "gender": str(gender),
        "status": {"$in": [str(UserStatus.ACTIVE), str(UserStatus.INACTIVE)]},
    }
    if active_only:
        query["activity.is_active_30d"] = True
    return await collection(C.USERS).count_documents(query)


__all__ = [
    "EntryTier",
    "Gender",
    "UserStatus",
    "UserSummary",
    "count_by_region_and_gender",
    "decide_review",
    "get_embedding_vector",
    "get_embedding_vectors",
    "get_location",
    "get_profile_card",
    "get_user_summaries",
    "get_user_summary",
    "hard_delete_user",
    "list_review_queue",
    "mark_active",
    "mark_banned",
    "mark_waitlisted",
    "recompute_active_flag",
    "record_swipe_activity",
    "set_entry_tier",
]
