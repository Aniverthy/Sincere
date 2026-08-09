"""Composite bot-risk scoring and 3-band routing (FR-1.6).

FR-1.6 (DECIDED): "A composite bot-risk score routes signups into **auto-approve /
auto-reject / human-review** bands; human review only for the ambiguous middle."

The signals are the ones §8 records on ``bot_risk_flags.signals`` and FR-5.4 enumerates:
duplicate similarity, device reuse, IP clustering, swipe timing, signup velocity, and
spam-template bio detection.

Two design rules that are not incidental:

* **A duplicate never auto-rejects.** FR-1.4 is explicit — >0.90 cosine goes to human review,
  never an automatic ban. A real person with an identical twin, or someone who deleted and
  re-signed up, must reach a human. :func:`route` enforces this after scoring.
* **Bands are configurable, not hard-coded.** §2 requires post-launch retuning without a
  redeploy, and FR-1.7's agreement logging exists precisely to inform that retuning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sincere.identity.schemas import RiskBand
from sincere.shared.config import Thresholds

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RiskSignals:
    """Raw inputs. Each is normalized to 0-1 by :func:`score`, where 1 = most suspicious."""

    duplicate_similarity: float | None = None
    """Highest cosine similarity against existing embeddings (FR-1.4)."""

    device_reuse_count: int = 0
    """Other accounts sharing this device fingerprint (FR-5.4)."""

    ip_cluster_count: int = 0
    """Other accounts from this IP in the recent window (FR-5.4)."""

    signup_velocity: int = 0
    """Signups platform-wide in the last hour (FR-5.4)."""

    bio_text: str = ""
    """Checked against spam templates (FR-5.4)."""

    photo_selfie_match: bool | None = None
    """FR-1.5. ``False`` is a strong signal; ``None`` means it could not be evaluated."""

    liveness_passed: bool | None = None
    """FR-1.2. ``False`` is the strongest single signal available."""


@dataclass(slots=True)
class RiskAssessment:
    composite_score: float
    band: RiskBand
    normalized: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


#: Weights for the composite. Structure follows FR-5.4's signal list; the values are launch
#: defaults meant to be retuned from FR-1.7 agreement data. They sum to exactly 1.0 so the
#: composite spans the full 0-1 range the FR-1.6 bands are expressed in.
#:
#: ``duplicate`` is deliberately ABSENT. FR-1.4 makes a duplicate face a *routing* decision —
#: always human review, never auto-ban — so it is applied as an override in :func:`route`
#: rather than as a score contributor. Including it here would have made auto-reject nearly
#: unreachable: the duplicate weight could only be earned by a signal that simultaneously
#: forces the band away from auto-reject, capping the reachable composite below the threshold.
WEIGHTS: dict[str, float] = {
    "liveness": 0.35,
    "photo_selfie": 0.25,
    "device_reuse": 0.15,
    "ip_cluster": 0.10,
    "bio_template": 0.075,
    "signup_velocity": 0.075,
}

#: FR-5.4 "spam-template bio detection". Deliberately narrow: these patterns catch the
#: copy-paste scam bios, and a false positive only costs a human review, never a ban.
SPAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:whats?app|telegram|signal)\s*[:+]?\s*\+?\d", re.I),
    re.compile(r"\b(?:cash\s?app|venmo|paypal|bitcoin|btc|usdt|crypto)\b", re.I),
    re.compile(r"\b(?:invest|trading|forex|profit|earn)\s+\w*\s*(?:daily|weekly|guaranteed)", re.I),
    re.compile(r"(?:https?://|www\.)\S+", re.I),
    re.compile(r"\bsugar\s+(?:daddy|baby|mommy)\b", re.I),
    re.compile(r"\b(?:onlyfans|of)\s*[:/]", re.I),
)


def _saturating(count: int, midpoint: float) -> float:
    """Map an unbounded count to 0-1, hitting 0.5 at ``midpoint``.

    Saturating rather than linear: the difference between 1 and 3 shared devices is
    meaningful, the difference between 30 and 60 is not — both are simply "a device farm".
    """
    if count <= 0:
        return 0.0
    return count / (count + midpoint)


def bio_spam_score(bio: str) -> float:
    if not bio:
        return 0.0
    hits = sum(1 for pattern in SPAM_PATTERNS if pattern.search(bio))
    return min(1.0, hits / 2.0)


def score(signals: RiskSignals, thresholds: Thresholds) -> RiskAssessment:
    """Compute the composite score and its band."""
    normalized: dict[str, float] = {}
    reasons: list[str] = []

    # Liveness (FR-1.2). Unknown is treated as mildly suspicious rather than clean: an
    # unevaluated check is not a passed check.
    if signals.liveness_passed is False:
        normalized["liveness"] = 1.0
        reasons.append("liveness check failed")
    elif signals.liveness_passed is None:
        normalized["liveness"] = 0.5
        reasons.append("liveness check could not be evaluated")
    else:
        normalized["liveness"] = 0.0

    # Photo-to-selfie match (FR-1.5).
    if signals.photo_selfie_match is False:
        normalized["photo_selfie"] = 1.0
        reasons.append("profile photos do not match the verification selfie")
    elif signals.photo_selfie_match is None:
        normalized["photo_selfie"] = 0.3
    else:
        normalized["photo_selfie"] = 0.0

    # Duplicate embedding (FR-1.4). Scaled across the threshold-to-1.0 range so that a hit
    # just over the line is not treated the same as a near-identical match.
    if signals.duplicate_similarity is None:
        normalized["duplicate"] = 0.0
    else:
        cutoff = thresholds.duplicate_similarity_threshold
        if signals.duplicate_similarity < cutoff:
            normalized["duplicate"] = 0.0
        else:
            span = max(1.0 - cutoff, 1e-9)
            normalized["duplicate"] = min(1.0, (signals.duplicate_similarity - cutoff) / span)
            reasons.append(
                f"face matches an existing account at {signals.duplicate_similarity:.0%} similarity"
            )

    normalized["device_reuse"] = _saturating(signals.device_reuse_count, midpoint=2.0)
    if signals.device_reuse_count > 0:
        reasons.append(f"device shared with {signals.device_reuse_count} other account(s)")

    normalized["ip_cluster"] = _saturating(signals.ip_cluster_count, midpoint=5.0)
    if signals.ip_cluster_count > 3:
        reasons.append(f"{signals.ip_cluster_count} recent signups from this IP")

    normalized["bio_template"] = bio_spam_score(signals.bio_text)
    if normalized["bio_template"] > 0:
        reasons.append("bio matches a known spam template")

    # Signup velocity is a platform-level signal: it raises suspicion of everyone during a
    # burst, which is the intent — a bot wave should widen the review net.
    normalized["signup_velocity"] = _saturating(max(0, signals.signup_velocity - 20), midpoint=50.0)

    # Summed over WEIGHTS, not over `normalized` — `normalized["duplicate"]` is recorded for
    # the audit trail and the reviewer's context, but never scored (see WEIGHTS).
    composite = sum(weight * normalized[key] for key, weight in WEIGHTS.items())
    band = route(composite, signals, thresholds)

    logger.info(
        "identity.risk_scored",
        extra={"composite_score": round(composite, 4), "band": str(band), "reasons": reasons},
    )
    return RiskAssessment(
        composite_score=round(composite, 4), band=band, normalized=normalized, reasons=reasons
    )


def route(composite: float, signals: RiskSignals, thresholds: Thresholds) -> RiskBand:
    """FR-1.6 three-band routing, with FR-1.4's override applied last.

    The duplicate override is deliberately the final word: whatever the composite says, a
    face that matches an existing account is a **human review**, never an automatic rejection.
    Getting this backwards would ban twins and returning users.
    """
    duplicate_hit = (
        signals.duplicate_similarity is not None
        and signals.duplicate_similarity >= thresholds.duplicate_similarity_threshold
    )

    if composite < thresholds.bot_risk_auto_approve_below:
        band = RiskBand.AUTO_APPROVE
    elif composite > thresholds.bot_risk_auto_reject_above:
        band = RiskBand.AUTO_REJECT
    else:
        band = RiskBand.REVIEW

    if duplicate_hit and band is not RiskBand.REVIEW:
        logger.info(
            "identity.duplicate_forces_review",
            extra={"band_before": str(band), "similarity": signals.duplicate_similarity},
        )
        return RiskBand.REVIEW

    return band
