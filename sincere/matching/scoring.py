"""Ranking formulas (§12) and the recommendation blend (§10).

Pure functions. Every coefficient here is quoted from §12; the module exists so those formulas
live in exactly one place and can be tested against hand-computed fixtures, which §24 requires:
"Scoring formulas (cold-start/final/blended/confidence — **exact-value tests against
hand-computed fixtures**)".

The formulas, verbatim from §12:

    cold_start_score = 0.45·preference_similarity
                     + 0.30·demographic_fit
                     + 0.25·prompt_text_similarity

    final_score      = 0.35·reciprocity_prediction
                     + 0.25·collaborative_filtering
                     + 0.20·preference_similarity
                     + 0.10·engagement_score
                     + 0.05·freshness_boost
                     + 0.05·visual_pattern_similarity      // fixed (DECIDED)

    blended_score    = confidence·final_score + (1 - confidence)·cold_start_score

    confidence(n)    = min(1, log(1 + n) / log(1 + N_mature))

§10's note matters for reading this: pre-graduation ``confidence`` is 0, so ``blended_score``
degenerates to pure ``cold_start_score``. **One formula covers every lifecycle stage** — there
is no branch on graduation anywhere in the scoring path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sincere.shared.config import Thresholds


@dataclass(slots=True)
class Features:
    """The §12 variable table, per (user, candidate) pair. All 0-1."""

    preference_similarity: float = 0.0
    """Cosine similarity of stated-interest/tag vectors."""

    demographic_fit: float = 0.0
    """Function of age gap + distance, normalized."""

    prompt_text_similarity: float = 0.0
    """Embedding cosine similarity of onboarding prompt answers."""

    reciprocity_prediction: float = 0.0
    """GBT model output: **P(candidate likes user back)** — §11 step 4 is explicit that the
    model scores the candidate's like-back probability, not the user's interest."""

    collaborative_filtering: float = 0.0
    """Matrix-factorization affinity over platform swipe history."""

    engagement_score: float = 0.0
    """Recency-weighted, from chat message count + response latency; decays on stagnation."""

    freshness_boost: float = 0.0
    """Decay function of days-since-signup."""

    visual_pattern_similarity: float = 0.5
    """Cosine(candidate embedding, user's liked-profile embeddings). Defaults to the
    FR-3.6 neutral value, so a user with thin like-history is neither helped nor punished."""


@dataclass(slots=True)
class ScoreBreakdown:
    """A scored candidate, with its parts kept for debugging and admin inspection."""

    candidate_id: str
    cold_start_score: float
    final_score: float
    blended_score: float
    confidence: float
    features: Features = field(default_factory=Features)
    is_exploration: bool = False
    """True when this candidate was injected by FR-3.5 exploration rather than by rank."""


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# §12 formulas
# ---------------------------------------------------------------------------

def confidence(post_graduation_swipes: int, mature_swipes: int) -> float:
    """``confidence(n) = min(1, log(1 + n) / log(1 + N_mature))`` (§12).

    §12's rationale for the log curve (DECIDED): "early post-graduation swipes carry the most
    new information, so model weight should rise fast then flatten — rather than a linear ramp
    (wastes early signal) or step function (jarring transition)".

    Returns exactly 0 for a pre-graduation user (n = 0), which is what makes
    :func:`blended_score` degenerate to pure cold-start without a branch.
    """
    if post_graduation_swipes <= 0:
        return 0.0
    if mature_swipes <= 0:
        return 1.0
    return min(1.0, math.log(1 + post_graduation_swipes) / math.log(1 + mature_swipes))


def cold_start_score(features: Features, thresholds: Thresholds) -> float:
    """§12 ``cold_start_score``. Weights: 0.45 / 0.30 / 0.25."""
    return clamp(
        thresholds.weight_cold_preference * features.preference_similarity
        + thresholds.weight_cold_demographic * features.demographic_fit
        + thresholds.weight_cold_prompt * features.prompt_text_similarity
    )


def final_score(features: Features, thresholds: Thresholds) -> float:
    """§12 ``final_score``. Weights: 0.35 / 0.25 / 0.20 / 0.10 / 0.05 / 0.05.

    The visual term is capped per FR-3.6 before it is weighted — see :func:`apply_visual_cap`.
    """
    return clamp(
        thresholds.weight_final_reciprocity * features.reciprocity_prediction
        + thresholds.weight_final_collaborative * features.collaborative_filtering
        + thresholds.weight_final_preference * features.preference_similarity
        + thresholds.weight_final_engagement * features.engagement_score
        + thresholds.weight_final_freshness * features.freshness_boost
        + thresholds.weight_final_visual * features.visual_pattern_similarity
    )


def blended_score(cold: float, final: float, conf: float) -> float:
    """§12 ``blended_score = confidence·final + (1 - confidence)·cold``.

    §24 requires "cold-start↔learned blend continuity (**no score cliffs at graduation**)".
    Continuity holds because confidence is continuous in n and equals 0 at n = 0 — the blend
    starts at exactly the cold-start score and moves smoothly from there.
    """
    conf = clamp(conf)
    return clamp(conf * final + (1.0 - conf) * cold)


def score_candidate(
    candidate_id: str, features: Features, post_graduation_swipes: int, thresholds: Thresholds
) -> ScoreBreakdown:
    """Run the whole §12 pipeline for one candidate."""
    conf = confidence(post_graduation_swipes, thresholds.confidence_mature_swipes)
    cold = cold_start_score(features, thresholds)
    final = final_score(features, thresholds)
    return ScoreBreakdown(
        candidate_id=candidate_id,
        cold_start_score=cold,
        final_score=final,
        blended_score=blended_score(cold, final, conf),
        confidence=conf,
        features=features,
    )


# ---------------------------------------------------------------------------
# Feature computation (§12 variable table)
# ---------------------------------------------------------------------------

def preference_similarity(user_tags: list[str], candidate_tags: list[str]) -> float:
    """Cosine similarity of tag sets (§12).

    Tag sets are binary vectors, so cosine reduces to ``|A ∩ B| / sqrt(|A|·|B|)``. Jaccard was
    the alternative; cosine is what §12 specifies, and it is kinder to users with many tags —
    Jaccard would penalize a broad-interest profile for the size of its own set.
    """
    if not user_tags or not candidate_tags:
        return 0.0
    shared = len(set(user_tags) & set(candidate_tags))
    if shared == 0:
        return 0.0
    return clamp(shared / math.sqrt(len(set(user_tags)) * len(set(candidate_tags))))


def demographic_fit(
    *, age_gap_years: float, distance_km: float, radius_km: int
) -> float:
    """"Function of age gap + distance, normalized" (§12).

    Both components decay rather than cliff. Distance is normalized against the *user's own
    radius*, so someone who set 5 km and someone who set 100 km are each scored against what
    they asked for — a 20 km candidate is far for the first and near for the second.
    """
    # Age: a 2-year gap is unremarkable; a 15-year gap is a real mismatch signal.
    age_component = 1.0 / (1.0 + (max(0.0, age_gap_years) / 8.0) ** 2)

    # Distance: linear decay across the user's chosen radius, floored at 0.
    span = max(radius_km, 1)
    distance_component = clamp(1.0 - (max(0.0, distance_km) / span))

    return clamp(0.5 * age_component + 0.5 * distance_component)


def prompt_text_similarity(
    user_vector: list[float] | None, candidate_vector: list[float] | None
) -> float:
    """Embedding cosine similarity of prompt answers (§12).

    Returns the neutral 0.5 when either side has no prompt embedding yet — same reasoning as
    FR-3.6's thin-history rule: absence of data must not read as absence of compatibility.
    """
    if not user_vector or not candidate_vector:
        return 0.5
    return cosine_unit(user_vector, candidate_vector)


def cosine_unit(a: list[float], b: list[float]) -> float:
    """Cosine similarity mapped from -1..1 onto 0..1, matching §12's 0-1 variable range."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return clamp((dot / (norm_a * norm_b) + 1.0) / 2.0)


def freshness_boost(
    signup_at: datetime, halflife_days: float, now: datetime | None = None
) -> float:
    """"Decay function of days-since-signup" (§12).

    Exponential half-life: a brand-new profile scores 1.0, and halves every ``halflife_days``.
    This is what stops the same established profiles monopolizing every batch — §10 pairs it
    with exploration injection for the same purpose.
    """
    now = now or datetime.now(UTC)
    days = max(0.0, (now - signup_at).total_seconds() / 86_400.0)
    if halflife_days <= 0:
        return 0.0
    return clamp(0.5 ** (days / halflife_days))


def engagement_score(
    *, message_count: int, avg_response_latency_s: float | None, days_since_last_message: float
) -> float:
    """"Recency-weighted, per-match, from chat message count + response latency; **decays on
    stagnation**" (§12).

    Three components: conversation volume, reply speed, and a recency multiplier. The recency
    multiplier is what implements "decays on stagnation" — a once-lively conversation that has
    gone quiet should not keep earning its old score.
    """
    volume = min(1.0, message_count / 40.0)

    if avg_response_latency_s is None:
        latency = 0.5  # unknown, treated as neutral
    else:
        # An hour is good, a day is poor. Saturating so a 3-day reply and a 5-day reply are
        # both simply "slow".
        latency = clamp(1.0 / (1.0 + (avg_response_latency_s / 3_600.0) / 6.0))

    recency = clamp(0.5 ** (max(0.0, days_since_last_message) / 7.0))
    return clamp((0.5 * volume + 0.5 * latency) * recency)


def apply_visual_cap(raw_similarity: float, thresholds: Thresholds) -> float:
    """FR-3.6: "capped/discounted >0.95 cosine, neutral (0.5) for thin like-history".

    Above the cap, the score is *discounted* rather than clipped. A near-identical face is
    more likely a duplicate account or the user's own photo than a genuine preference match,
    so pushing it up the ranking would be actively wrong. Discounting sends it back toward
    neutral instead of rewarding it.
    """
    cap = thresholds.visual_similarity_cap
    if raw_similarity <= cap:
        return clamp(raw_similarity)
    overshoot = (raw_similarity - cap) / max(1.0 - cap, 1e-9)
    return clamp(cap - overshoot * (cap - thresholds.visual_similarity_neutral))


def visual_pattern_similarity(
    candidate_vector: list[float] | None,
    liked_centroid: list[float] | None,
    liked_count: int,
    thresholds: Thresholds,
) -> float:
    """FR-3.6 visual-pattern term. Weight is fixed at 0.05 — see :data:`Thresholds`.

    §9's constraints hold here: cosine similarity only, **per-user-relative**. The comparison
    is against *this user's* liked-profile centroid. There is no universal attractiveness
    metric anywhere in the system, and this function is the closest thing to one — which is
    exactly why it is capped, weighted at 0.05, and neutral by default.
    """
    # "Neutral (0.5) for thin like-history" — a handful of likes cannot establish a pattern.
    if not candidate_vector or not liked_centroid or liked_count < 5:
        return thresholds.visual_similarity_neutral
    return apply_visual_cap(cosine_unit(candidate_vector, liked_centroid), thresholds)


def centroid(vectors: list[list[float]]) -> list[float] | None:
    """Mean vector of a user's liked profiles. Cached per §16 to keep scoring O(pool)."""
    usable = [v for v in vectors if v]
    if not usable:
        return None
    length = len(usable[0])
    if any(len(v) != length for v in usable):
        usable = [v for v in usable if len(v) == length]
        if not usable:
            return None
    return [sum(v[i] for v in usable) / len(usable) for i in range(length)]


def has_graduated(swipes: int, matches: int, thresholds: Thresholds) -> bool:
    """FR-3.4 (DECIDED): graduation at **20+ swipes AND 3+ matches**.

    Both conditions, not either. Swipes alone can be produced by a bot; matches alone means
    too little signal about what the user rejects.
    """
    return swipes >= thresholds.graduation_swipes and matches >= thresholds.graduation_matches


def exploration_rate(graduated: bool, thresholds: Thresholds) -> float:
    """FR-3.5: ~40% pre-graduation, ~15% post."""
    return (
        thresholds.exploration_rate_post_graduation
        if graduated
        else thresholds.exploration_rate_pre_graduation
    )
