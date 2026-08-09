"""Matching business logic — the §11 pipeline and the §7 swipe/match endpoints.

§11's seven stages, implemented in :func:`generate_batch`:

1. Pool query — ``$geoNear``, bidirectional radius
2. Feature assembly — cached user-level vectors keep this O(pool)
3. Scoring — cold-start / final / blended per graduation state
4. Reciprocity symmetric check — P(candidate → user)
5. Exploration injection — ~40% / ~15%
6. Fairness constraints — **entry tier is not a scoring feature, full stop**
7. Delivery — persist the ordered list; the request-time read is a lookup
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sincere.identity import api as identity
from sincere.matching import models, scoring
from sincere.matching import repository as repo
from sincere.matching.schemas import (
    DailyBatchResponse,
    DailyCandidate,
    MatchListResponse,
    MatchSummary,
    SwipeDirection,
    SwipeResponse,
    UnmatchResponse,
)
from sincere.shared import cache
from sincere.shared.config import Thresholds
from sincere.shared.errors import ForbiddenError, NotFoundError
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)


def today_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


# ---------------------------------------------------------------------------
# §16 cached feature vectors — what makes scoring O(pool) rather than O(pool^2)
# ---------------------------------------------------------------------------

async def user_features(user_id: str) -> dict[str, Any]:
    """Tag vector, prompt embedding and liked-profile centroid, cached per §16.

    Invalidated on profile edit (identity) and on a new like (below), exactly as §16's table
    prescribes.
    """
    key = cache.Keys.user_features(user_id)
    hit = await cache.get_json(key)
    if hit is not None:
        return hit

    card = await identity.get_profile_card(user_id)
    liked_ids = await repo.liked_target_ids(user_id)
    liked_vectors = await identity.get_embedding_vectors(liked_ids) if liked_ids else {}

    features = {
        "tags": (card or {}).get("tags", []),
        "prompt_vector": _prompt_vector((card or {}).get("prompts", [])),
        "liked_centroid": scoring.centroid(list(liked_vectors.values())),
        "liked_count": len(liked_vectors),
    }
    await cache.set_json(key, features, ttl=cache.TTL["user_features"])
    return features


def _prompt_vector(prompts: list[dict[str, str]]) -> list[float] | None:
    """Bag-of-words embedding of prompt answers.

    §12 wants embedding cosine similarity of prompt answers. A sentence-transformer is the
    §13 upgrade path; this hashed bag-of-words gives a real, deterministic 128-d vector with
    no model dependency, which keeps the API installable while the ML extras are optional
    (see ``requirements-ml.txt``).
    """
    text = " ".join((p.get("a") or "") for p in prompts).lower()
    if not text.strip():
        return None

    import hashlib

    dimensions = 128
    vector = [0.0] * dimensions
    for word in text.split():
        cleaned = "".join(ch for ch in word if ch.isalnum())
        if len(cleaned) < 3:
            continue
        bucket = int(hashlib.md5(cleaned.encode()).hexdigest(), 16) % dimensions
        vector[bucket] += 1.0
    return vector if any(vector) else None


# ---------------------------------------------------------------------------
# §11 batch generation
# ---------------------------------------------------------------------------

async def generate_batch(user_id: str, thresholds: Thresholds | None = None) -> int:
    """Build and persist one user's daily list. Returns how many candidates were produced.

    Idempotent: re-running for the same day overwrites the same document (§15).
    """
    thresholds = thresholds or await load_thresholds()

    user = await identity.get_user_summary(user_id)
    if user is None or user["status"] != "active":
        return 0

    location = await identity.get_location(user_id)
    if not location:
        logger.debug("matching.no_location", extra={"user_id": user_id})
        return 0

    # --- Stage 1: pool query, with both-direction radius (§11 step 1) ---
    excluded = await repo.swiped_target_ids(user_id) | await repo.matched_user_ids(user_id)
    opposite = "female" if user["gender"] == "male" else "male"

    raw_pool = await repo.candidate_pool(
        user_id=user_id,
        location=location,
        radius_km=user["radius_km"],
        opposite_gender=opposite,
        exclude_ids=excluded,
        # Recently present, not FR-2.3's swipe-based ratio flag — see candidate_pool's
        # docstring for why using that flag here would deadlock discovery.
        active_since=datetime.now(UTC) - timedelta(days=thresholds.active_window_days),
        limit=thresholds.candidate_pool_cap,
    )

    pool = [
        doc
        for doc in raw_pool
        # §11 step 1: the candidate must also have the user inside THEIR radius.
        if (doc.get("distance_m", 0) / 1000.0) <= doc.get("radius_km", 25)
    ]
    if not pool:
        await repo.store_batch(
            user_id=user_id, region=user["h3_region"], batch_date=today_key(), entries=[]
        )
        return 0

    # --- Stage 2/3/4: features, scoring, reciprocity (§11 steps 2-4) ---
    swipes = await repo.count_swipes(user_id)
    matches = await repo.count_matches(user_id)
    graduated = scoring.has_graduated(swipes, matches, thresholds)
    post_graduation_swipes = max(0, swipes - thresholds.graduation_swipes) if graduated else 0

    viewer = await user_features(user_id)
    viewer_card = await identity.get_profile_card(user_id)
    viewer_age = (viewer_card or {}).get("age") or 30

    reciprocity_model, cf_model = models.get_providers()
    candidate_vectors = await identity.get_embedding_vectors([doc["_id"] for doc in pool])

    scored: list[scoring.ScoreBreakdown] = []
    for doc in pool:
        features = await _build_features(
            viewer=viewer,
            viewer_age=viewer_age,
            viewer_radius=user["radius_km"],
            candidate=doc,
            candidate_vector=candidate_vectors.get(doc["_id"]),
            user_id=user_id,
            reciprocity_model=reciprocity_model,
            cf_model=cf_model,
            thresholds=thresholds,
        )
        scored.append(
            scoring.score_candidate(doc["_id"], features, post_graduation_swipes, thresholds)
        )

    # --- Stage 5/6: exploration injection, fairness (§11 steps 5-6) ---
    #
    # Note what is NOT here: entry_tier is never read, so it cannot enter the ranking.
    # §11 step 6 and FR-2.11 both require that, and absence is the strongest enforcement.
    quota = _daily_quota(user_id, thresholds)
    ordered = _rank_with_exploration(scored, quota, graduated, thresholds)

    # --- Stage 7: delivery (§11 step 7) ---
    await repo.store_batch(
        user_id=user_id,
        region=user["h3_region"],
        batch_date=today_key(),
        entries=[
            {
                "target_id": item.candidate_id,
                "blended_score": item.blended_score,
                "cold_start_score": item.cold_start_score,
                "final_score": item.final_score,
                "confidence": item.confidence,
                "is_exploration": item.is_exploration,
            }
            for item in ordered
        ],
    )
    await cache.invalidate(cache.Keys.daily_batch(user_id, today_key()))
    logger.info(
        "matching.batch_generated",
        extra={"user_id": user_id, "count": len(ordered), "graduated": graduated},
    )
    return len(ordered)


async def _build_features(
    *,
    viewer: dict[str, Any],
    viewer_age: int,
    viewer_radius: int,
    candidate: dict[str, Any],
    candidate_vector: list[float] | None,
    user_id: str,
    reciprocity_model: models.ReciprocityModel,
    cf_model: models.CollaborativeFilter,
    thresholds: Thresholds,
) -> scoring.Features:
    profile = candidate.get("profile", {})
    candidate_tags = profile.get("tags", [])
    distance_km = candidate.get("distance_m", 0) / 1000.0

    candidate_age = _age_from(profile.get("dob")) or viewer_age
    age_gap = abs(viewer_age - candidate_age)

    shared_tags = len(set(viewer.get("tags", [])) & set(candidate_tags))

    return scoring.Features(
        preference_similarity=scoring.preference_similarity(
            viewer.get("tags", []), candidate_tags
        ),
        demographic_fit=scoring.demographic_fit(
            age_gap_years=age_gap, distance_km=distance_km, radius_km=viewer_radius
        ),
        prompt_text_similarity=scoring.prompt_text_similarity(
            viewer.get("prompt_vector"), _prompt_vector(profile.get("prompts", []))
        ),
        # §11 step 4: P(candidate -> user), not P(user -> candidate).
        reciprocity_prediction=reciprocity_model.predict(
            {
                "age_gap_years": age_gap,
                "distance_km": distance_km,
                "radius_km": viewer_radius,
                "shared_tag_count": shared_tags,
                "candidate_activity": 1.0,
            }
        ),
        collaborative_filtering=cf_model.affinity(user_id, candidate["_id"]),
        engagement_score=0.0,  # no conversation exists with an unmatched candidate
        freshness_boost=scoring.freshness_boost(
            candidate.get("created_at") or datetime.now(UTC),
            thresholds.freshness_halflife_days,
        ),
        visual_pattern_similarity=scoring.visual_pattern_similarity(
            candidate_vector,
            viewer.get("liked_centroid"),
            viewer.get("liked_count", 0),
            thresholds,
        ),
    )


def _age_from(dob: Any) -> int | None:
    if not dob:
        return None
    if isinstance(dob, str):
        try:
            dob = datetime.fromisoformat(dob)
        except ValueError:
            return None
    if isinstance(dob, datetime):
        dob = dob.date()
    if not isinstance(dob, date):
        return None
    today = datetime.now(UTC).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _daily_quota(user_id: str, thresholds: Thresholds) -> int:
    """FR-3.1 / FR-6.1. The Pro uplift is applied at read time by :func:`daily_batch`, so the
    batch itself is generated at the largest tier's size and trimmed on delivery."""
    return thresholds.daily_match_count_pro_plus


def _rank_with_exploration(
    scored: list[scoring.ScoreBreakdown],
    quota: int,
    graduated: bool,
    thresholds: Thresholds,
) -> list[scoring.ScoreBreakdown]:
    """§11 step 5: reserve ~40%/15% of slots for candidates sampled outside top-rank order.

    "Uniform-over-eligible at MVP; bandit-style selection is a post-launch refinement" — so
    the exploration picks are a uniform sample from everyone below the top-ranked cut, not a
    second ranking. Sampling with ``secrets`` rather than ``random`` keeps the choice
    unpredictable to a user probing the algorithm.
    """
    scored.sort(key=lambda item: item.blended_score, reverse=True)
    if len(scored) <= quota:
        return scored

    rate = scoring.exploration_rate(graduated, thresholds)
    exploration_slots = min(int(round(quota * rate)), max(0, len(scored) - quota))
    ranked_slots = quota - exploration_slots

    chosen = scored[:ranked_slots]
    remainder = scored[ranked_slots:]

    for _ in range(min(exploration_slots, len(remainder))):
        pick = remainder.pop(secrets.randbelow(len(remainder)))
        pick.is_exploration = True
        chosen.append(pick)

    # Re-sort so the delivered order still reads as a ranking; exploration changes *which*
    # profiles appear, not that the list is ordered.
    chosen.sort(key=lambda item: item.blended_score, reverse=True)
    return chosen


# ---------------------------------------------------------------------------
# §7 endpoints
# ---------------------------------------------------------------------------

async def daily_batch(user_id: str) -> DailyBatchResponse:
    """``GET /matches/daily`` — §19: "request time is a cache/collection lookup"."""
    thresholds = await load_thresholds()
    batch_date = today_key()
    stored = await repo.get_batch(user_id, batch_date)

    if stored is None:
        # No batch yet (new user, or first day). Generate on demand so the product is never
        # empty; the nightly job is the optimization, not the only path.
        await generate_batch(user_id, thresholds)
        stored = await repo.get_batch(user_id, batch_date)

    if stored is None:
        return DailyBatchResponse(
            batch_date=batch_date,
            candidates=[],
            total=0,
            remaining=0,
            message="We could not find anyone new near you today. Try widening your radius.",
        )

    quota = await _quota_for(user_id, thresholds)
    consumed = set(stored.get("consumed", []))
    entries = [e for e in stored.get("entries", []) if e["target_id"] not in consumed][:quota]

    boosted_ids = await _boosted_ids([e["target_id"] for e in entries])
    candidates: list[DailyCandidate] = []
    for entry in entries:
        card = await identity.get_profile_card(entry["target_id"])
        if card is None:
            continue  # deleted or banned between generation and delivery
        candidates.append(
            DailyCandidate(
                user_id=card["user_id"],
                name=card.get("name"),
                age=card.get("age"),
                bio=card.get("bio"),
                prompts=card.get("prompts", []),
                tags=card.get("tags", []),
                photos=card.get("photos", []),
                # FR-6.2: the client MUST render a "Boosted" label when this is true.
                boosted=card["user_id"] in boosted_ids,
            )
        )

    return DailyBatchResponse(
        batch_date=batch_date,
        candidates=candidates,
        total=len(stored.get("entries", [])),
        remaining=len(candidates),
        generated_at=stored.get("generated_at"),
    )


async def _quota_for(user_id: str, thresholds: Thresholds) -> int:
    """FR-6.1 tier allowances; FR-6.4 makes the free 15 permanent."""
    try:
        from sincere.monetization import api as monetization

        tier = await monetization.get_tier(user_id)
    except ImportError:
        tier = None

    if tier == "pro_plus":
        return thresholds.daily_match_count_pro_plus
    if tier == "basic_pro":
        return thresholds.daily_match_count_basic_pro
    return thresholds.daily_match_count


async def _boosted_ids(user_ids: list[str]) -> set[str]:
    """FR-6.2: which of these profiles currently hold boosted visibility."""
    try:
        from sincere.monetization import api as monetization

        return await monetization.boosted_user_ids(user_ids)
    except ImportError:
        return set()


async def record_swipe(
    user_id: str, target_id: str, direction: SwipeDirection, dwell_ms: int
) -> SwipeResponse:
    """``POST /swipes`` — §19: "single insert + counter increments; event fan-out async"."""
    thresholds = await load_thresholds()

    if target_id == user_id:
        raise ForbiddenError("Invalid target", "You cannot swipe on yourself.")

    # §18: cross-check the client's dwell claim against when we actually served the profile.
    server_dwell = await _server_side_dwell(user_id, target_id)

    inserted = await repo.record_swipe(
        user_id=user_id,
        target_id=target_id,
        direction=str(direction),
        dwell_ms=dwell_ms,
        server_dwell_ms=server_dwell,
    )
    if not inserted:
        existing = await repo.find_match_between(user_id, target_id)
        return SwipeResponse(
            matched=existing is not None,
            match_id=existing["_id"] if existing else None,
        )

    await repo.mark_consumed(user_id, today_key(), target_id)
    await identity.record_swipe_activity(user_id)

    if direction is SwipeDirection.RIGHT:
        # A new like changes the liked-centroid, which §16 says to invalidate on.
        await cache.invalidate(cache.Keys.user_features(user_id))

    # antiabuse evaluates the dwell rule; matching updates graduation counters (§14).
    await bus.emit(
        Event.SWIPE_RECORDED,
        {
            "user_id": user_id,
            "target_id": target_id,
            "direction": str(direction),
            "dwell_ms": dwell_ms,
            "server_dwell_ms": server_dwell,
        },
    )

    matched = False
    match_id: str | None = None
    if direction is SwipeDirection.RIGHT and await repo.has_liked(target_id, user_id):
        user = await identity.get_user_summary(user_id)
        existing = await repo.find_match_between(user_id, target_id)
        if existing is None:
            match = await repo.create_match(user_id, target_id, (user or {}).get("h3_region"))
            match_id, matched = match["_id"], True
            await bus.emit(
                Event.MATCH_FORMED,
                {"match_id": match["_id"], "users": match["users"], "region": match["region"]},
            )
        else:
            match_id, matched = existing["_id"], True

    stored = await repo.get_batch(user_id, today_key())
    quota = await _quota_for(user_id, thresholds)
    consumed = set((stored or {}).get("consumed", []))
    remaining = len(
        [e for e in (stored or {}).get("entries", []) if e["target_id"] not in consumed][:quota]
    )

    return SwipeResponse(matched=matched, match_id=match_id, remaining_today=remaining)


async def _server_side_dwell(user_id: str, target_id: str) -> int | None:
    """§18: when did we actually serve this profile? Used to sanity-check ``dwell_ms``."""
    served_at = await cache.get_json(f"served:{user_id}:{target_id}")
    if not served_at:
        return None
    try:
        delta = datetime.now(UTC) - datetime.fromisoformat(served_at)
        return int(delta.total_seconds() * 1000)
    except (TypeError, ValueError):
        return None


async def list_matches(user_id: str) -> MatchListResponse:
    """``GET /matches``."""
    matches = await repo.list_matches(user_id)
    summaries: list[MatchSummary] = []

    for match in matches:
        other_id = next((uid for uid in match["users"] if uid != user_id), None)
        if other_id is None:
            continue
        card = await identity.get_profile_card(other_id)
        if card is None:
            continue
        photos = card.get("photos") or []
        engagement = match.get("engagement", {})
        summaries.append(
            MatchSummary(
                match_id=match["_id"],
                user_id=other_id,
                name=card.get("name"),
                photo_url=photos[0].get("url") if photos else None,
                formed_at=match["formed_at"],
                last_message_at=engagement.get("last_msg_at"),
                message_count=engagement.get("msg_count", 0),
            )
        )

    return MatchListResponse(matches=summaries, total=len(summaries))


async def unmatch(user_id: str, match_id: str) -> UnmatchResponse:
    """``DELETE /matches/:id`` — starts the 90-day message-retention clock (§8)."""
    thresholds = await load_thresholds()
    match = await repo.get_match(match_id)
    if match is None or user_id not in match["users"]:
        raise NotFoundError("Match")

    updated = await repo.unmatch(match_id, thresholds.message_retention_days_post_unmatch)
    if updated is None:
        raise NotFoundError("Match", "This match is already ended.")

    await bus.emit(
        Event.UNMATCHED,
        {"match_id": match_id, "users": match["users"], "by": user_id},
    )
    return UnmatchResponse(
        match_id=match_id,
        unmatched_at=updated["unmatched_at"],
        messages_purge_after=updated["messages_purge_after"],
        message=(
            "Unmatched. Your messages will be deleted in "
            f"{thresholds.message_retention_days_post_unmatch} days."
        ),
    )
