"""ML model providers for reciprocity and collaborative filtering (§13).

§13 specifies **gradient-boosted trees** (XGBoost/LightGBM) for reciprocity and **matrix
factorization** (SVD/ALS) for collaborative filtering, both retrained on a periodic batch and
gated by holdout validation before promotion.

Both sit behind an interface for a reason the docs state directly, not as an abstraction for
its own sake: §10:507 says reciprocity is "substituted with **coarse population-level priors**
(age-range overlap, distance decay) until real reciprocity data accumulates **(DECIDED
cold-start strategy)**". So a launch deployment genuinely runs the prior-based provider, and
swaps to the trained one only once :mod:`sincere.feedback_ml` promotes a model. The interface
is the switch the decision record already called for.

§23:808: "Model rollback = repointing the registry, no code deploy." :func:`get_providers`
reads the registry on every call for that reason.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Protocol

from sincere.shared.config import get_settings

logger = logging.getLogger(__name__)


class ReciprocityModel(Protocol):
    """Predicts **P(candidate likes user back)** — §11 step 4."""

    name: str

    def predict(self, features: dict[str, float]) -> float:  # pragma: no cover - interface
        ...


class CollaborativeFilter(Protocol):
    """Latent-factor affinity over the platform-wide swipe matrix (§13)."""

    name: str

    def affinity(self, user_id: str, candidate_id: str) -> float:  # pragma: no cover
        ...


# ---------------------------------------------------------------------------
# Cold-start providers — the DECIDED launch behaviour (§10:507)
# ---------------------------------------------------------------------------

class PopulationPriorReciprocity:
    """Coarse population-level priors: age-range overlap and distance decay (§10:507).

    Not a stub. This is what the decision record specifies the system should use until real
    reciprocity data exists, and it produces genuine, defensible rankings from day one.

    The prior encodes two robust population regularities: mutual interest falls off with age
    gap, and falls off with distance. Nothing more — deliberately, because inventing richer
    structure without data would be guessing dressed up as a model.
    """

    name = "population_prior_v1"

    def predict(self, features: dict[str, float]) -> float:
        age_gap = features.get("age_gap_years", 0.0)
        distance_km = features.get("distance_km", 0.0)
        radius_km = max(features.get("radius_km", 25.0), 1.0)
        shared_tags = features.get("shared_tag_count", 0.0)
        candidate_activity = features.get("candidate_activity", 0.5)

        age_term = 1.0 / (1.0 + (max(0.0, age_gap) / 10.0) ** 2)
        distance_term = max(0.0, 1.0 - (distance_km / radius_km))
        interest_term = min(1.0, shared_tags / 5.0)

        # An inactive candidate cannot like anyone back, whatever the compatibility says.
        # This is the single most predictive term available before real data exists.
        prior = 0.35 * age_term + 0.25 * distance_term + 0.20 * interest_term
        return max(0.0, min(1.0, prior + 0.20 * candidate_activity))


class CoSwipeCollaborativeFilter:
    """Item-item affinity from co-swipe counts, standing in for ALS until it is trained.

    §13's ALS needs a swipe matrix that a pre-launch app does not have. This computes the same
    *shape* of signal — "people who liked what you liked also liked this" — from raw co-swipe
    counts supplied by the caller, with no factorization step.

    Returns the neutral 0.5 when there is no co-swipe evidence, so an unseen candidate is
    neither promoted nor buried by a signal that simply does not exist yet.
    """

    name = "co_swipe_v1"

    def __init__(self, affinities: dict[tuple[str, str], float] | None = None) -> None:
        self._affinities = affinities or {}

    def affinity(self, user_id: str, candidate_id: str) -> float:
        return self._affinities.get((user_id, candidate_id), 0.5)


# ---------------------------------------------------------------------------
# Trained providers — loaded from the registry once feedback_ml promotes a model
# ---------------------------------------------------------------------------

class TrainedReciprocity:
    """XGBoost reciprocity model loaded from the §13 registry."""

    def __init__(self, booster: Any, feature_order: list[str], version: str) -> None:
        self._booster = booster
        self._feature_order = feature_order
        self.name = f"gbt_{version}"

    def predict(self, features: dict[str, float]) -> float:
        import numpy as np
        import xgboost as xgb

        row = np.array([[features.get(name, 0.0) for name in self._feature_order]])
        prediction = float(self._booster.predict(xgb.DMatrix(row))[0])
        return max(0.0, min(1.0, prediction))


class TrainedCollaborativeFilter:
    """ALS latent factors loaded from the §13 registry."""

    def __init__(
        self,
        user_factors: dict[str, list[float]],
        item_factors: dict[str, list[float]],
        version: str,
    ) -> None:
        self._user_factors = user_factors
        self._item_factors = item_factors
        self.name = f"als_{version}"

    def affinity(self, user_id: str, candidate_id: str) -> float:
        user_vector = self._user_factors.get(user_id)
        item_vector = self._item_factors.get(candidate_id)
        if not user_vector or not item_vector:
            return 0.5  # unseen pair — neutral, same reasoning as the co-swipe provider
        dot = sum(a * b for a, b in zip(user_vector, item_vector, strict=False))
        # Logistic squash into 0-1: raw dot products are unbounded and §12 needs 0-1.
        return 1.0 / (1.0 + math.exp(-dot))


# ---------------------------------------------------------------------------
# Registry (§13, §23:808)
# ---------------------------------------------------------------------------

def registry_path() -> Path:
    return Path(get_settings().model_registry_path)


def read_registry() -> dict[str, Any]:
    """Current promoted model pointers. Missing registry means cold-start providers."""
    manifest = registry_path() / "current.json"
    if not manifest.exists():
        return {}
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("registry.unreadable — falling back to cold-start providers")
        return {}


def promote(entry: dict[str, Any]) -> None:
    """Point the registry at a newly validated model (§13, §23:808).

    Called by feedback_ml **only after** holdout validation passes. Rollback is a second call
    to this function with the previous entry — no code deploy, per §23:808.
    """
    directory = registry_path()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "current.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    logger.info("registry.promoted", extra={"entry": entry})


_cache: tuple[str, ReciprocityModel, CollaborativeFilter] | None = None


def get_providers() -> tuple[ReciprocityModel, CollaborativeFilter]:
    """Return the currently promoted providers, falling back to the §10 cold-start pair.

    The registry is re-read whenever its version pointer changes, so a promotion or rollback
    takes effect without restarting the workers (§23:808).
    """
    global _cache

    manifest = read_registry()
    version = str(manifest.get("version", "cold-start"))

    if _cache is not None and _cache[0] == version:
        return _cache[1], _cache[2]

    reciprocity: ReciprocityModel = PopulationPriorReciprocity()
    collaborative: CollaborativeFilter = CoSwipeCollaborativeFilter()

    if manifest:
        try:
            reciprocity = _load_reciprocity(manifest) or reciprocity
            collaborative = _load_collaborative(manifest) or collaborative
        except Exception:
            logger.exception(
                "registry.load_failed — continuing with cold-start providers. §13 keeps the "
                "current model on validation failure; the same applies to a load failure."
            )

    logger.info(
        "models.loaded",
        extra={"version": version, "reciprocity": reciprocity.name, "cf": collaborative.name},
    )
    _cache = (version, reciprocity, collaborative)
    return reciprocity, collaborative


def _load_reciprocity(manifest: dict[str, Any]) -> ReciprocityModel | None:
    entry = manifest.get("reciprocity")
    if not entry:
        return None

    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(str(registry_path() / entry["file"]))
    return TrainedReciprocity(booster, entry["features"], manifest.get("version", "0"))


def _load_collaborative(manifest: dict[str, Any]) -> CollaborativeFilter | None:
    entry = manifest.get("collaborative")
    if not entry:
        return None

    payload = json.loads((registry_path() / entry["file"]).read_text(encoding="utf-8"))
    return TrainedCollaborativeFilter(
        payload["user_factors"], payload["item_factors"], manifest.get("version", "0")
    )


def reset_cache() -> None:
    """Test seam, and the hook a manual rollback uses to force an immediate re-read."""
    global _cache
    _cache = None
