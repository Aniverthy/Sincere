"""Batch retraining with holdout gating (§13, §23:808). Pure logic where possible.

§13 (DECIDED): "Models validated against a holdout set **before promotion**" and, on failure,
"**Keep current model**". §23:808: "Model rollback = repointing the registry, no code deploy."

The gate is the important part. A retrain that produces a worse model must not reach users,
and the only thing standing between the two is :func:`passes_holdout_gate`.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Below this many labelled rows, a holdout score is noise rather than evidence. §25 phase 3
#: gates the first real training on "We-Met response volume meaningful" for the same reason.
MIN_TRAINING_ROWS = 200

#: A new model must beat the incumbent by at least this margin to be promoted. Requiring a
#: *margin* rather than any improvement stops churn from run-to-run sampling noise.
PROMOTION_MARGIN = 0.01

HOLDOUT_FRACTION = 0.2


@dataclass(frozen=True, slots=True)
class TrainingResult:
    trained: bool
    promoted: bool
    reason: str
    rows: int = 0
    holdout_auc: float | None = None
    incumbent_auc: float | None = None
    version: str | None = None


def split_holdout(
    rows: list[dict[str, Any]], fraction: float = HOLDOUT_FRACTION, seed: int = 20260809
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic train/holdout split.

    Seeded so a rerun of the same data gives the same verdict — a promotion decision that
    flips on reshuffling is not a decision, and §13 makes this gate load-bearing.
    """
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    cut = max(1, int(len(shuffled) * fraction))
    return shuffled[cut:], shuffled[:cut]


def auc(predictions: list[float], labels: list[int]) -> float:
    """Area under the ROC curve, by the rank-sum identity.

    Computed directly rather than via scikit-learn so the holdout gate has no dependency on
    the optional ML extras — the gate must be able to *refuse* a promotion even in an
    environment where the training libraries failed to load.
    """
    positives = [p for p, y in zip(predictions, labels, strict=True) if y == 1]
    negatives = [p for p, y in zip(predictions, labels, strict=True) if y == 0]
    if not positives or not negatives:
        return 0.5  # a single-class holdout carries no discriminative information

    ranked = sorted(zip(predictions, labels, strict=True), key=lambda pair: pair[0])
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index
        while end + 1 < len(ranked) and ranked[end + 1][0] == ranked[index][0]:
            end += 1
        # Ties share the average rank, or an all-constant model would score 1.0.
        average_rank = (index + end + 2) / 2.0
        for position in range(index, end + 1):
            if ranked[position][1] == 1:
                rank_sum += average_rank
        index = end + 1

    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def passes_holdout_gate(
    candidate_auc: float, incumbent_auc: float | None, margin: float = PROMOTION_MARGIN
) -> tuple[bool, str]:
    """§13's promotion gate. Returns ``(promote, reason)``.

    Three refusals, each for a distinct failure mode:

    * below 0.5 — the model is worse than a coin flip, so its ranking is actively harmful
    * no improvement over the incumbent — churn without benefit
    * within the noise margin — an improvement we cannot distinguish from sampling variance
    """
    if candidate_auc < 0.5:
        return False, f"holdout AUC {candidate_auc:.3f} is no better than chance"

    if incumbent_auc is None:
        return True, f"first model, holdout AUC {candidate_auc:.3f}"

    if candidate_auc < incumbent_auc:
        return False, (
            f"holdout AUC {candidate_auc:.3f} is below the current model's {incumbent_auc:.3f} "
            "— keeping the current model"
        )

    if candidate_auc - incumbent_auc < margin:
        return False, (
            f"holdout AUC {candidate_auc:.3f} improves on {incumbent_auc:.3f} by less than "
            f"the {margin:.2f} noise margin — keeping the current model"
        )

    return True, f"holdout AUC {candidate_auc:.3f} beats {incumbent_auc:.3f}"


def build_features(row: dict[str, Any]) -> dict[str, float]:
    """Feature vector for the reciprocity model (§13 inputs).

    §13 lists: "shared interests, distance, activity level, **chat-derived engagement
    features**". The chat-derived ones are what the We-Met loop makes meaningful — they are
    the only signals that correlate with meeting in person rather than swiping.
    """
    latency = row.get("avg_response_latency_s")
    return {
        "msg_count": float(row.get("msg_count", 0)),
        "avg_response_latency_s": float(latency) if latency is not None else 86_400.0,
        "has_conversation": 1.0 if row.get("msg_count", 0) > 0 else 0.0,
        "sustained_conversation": 1.0 if row.get("msg_count", 0) >= 20 else 0.0,
    }


def train_reciprocity(rows: list[dict[str, Any]]) -> tuple[Any, list[str]] | None:
    """Train the GBT reciprocity model (§13). Returns ``(booster, feature_order)``.

    Returns ``None`` when XGBoost is unavailable — the ML extras are an optional install
    (``requirements-ml.txt``), and the app must keep running on the §10 cold-start providers
    without them.
    """
    try:
        import numpy as np
        import xgboost as xgb
    except ImportError:
        logger.warning(
            "training.xgboost_unavailable — install requirements-ml.txt to train the §13 "
            "reciprocity model. The cold-start priors remain in use."
        )
        return None

    feature_order = sorted(build_features(rows[0]))
    matrix = np.array([[build_features(r)[name] for name in feature_order] for r in rows])
    labels = np.array([r["label"] for r in rows])

    booster = xgb.train(
        {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": 4,
            "eta": 0.1,
            # Shallow and regularized: §13 chose GBT because the data volume is small, and a
            # deep tree on a few hundred rows memorizes rather than generalizes.
            "min_child_weight": 5,
            "subsample": 0.8,
        },
        xgb.DMatrix(matrix, label=labels, feature_names=feature_order),
        num_boost_round=60,
    )
    return booster, feature_order


def predict_batch(
    booster: Any, feature_order: list[str], rows: list[dict[str, Any]]
) -> list[float]:
    import numpy as np
    import xgboost as xgb

    matrix = np.array([[build_features(r)[name] for name in feature_order] for r in rows])
    return [
        float(p)
        for p in booster.predict(xgb.DMatrix(matrix, feature_names=feature_order))
    ]


def train_collaborative(swipes: list[dict[str, Any]], factors: int = 16) -> dict[str, Any] | None:
    """Train ALS latent factors over the swipe matrix (§13).

    Returns a serializable ``{"user_factors": ..., "item_factors": ...}`` payload, or ``None``
    when ``implicit`` is unavailable.
    """
    try:
        import numpy as np
        from implicit.als import AlternatingLeastSquares
        from scipy.sparse import csr_matrix
    except ImportError:
        logger.warning("training.implicit_unavailable — keeping the co-swipe provider")
        return None

    users = sorted({s["user_id"] for s in swipes})
    items = sorted({s["target_id"] for s in swipes})
    if not users or not items:
        return None

    user_index = {uid: i for i, uid in enumerate(users)}
    item_index = {iid: i for i, iid in enumerate(items)}

    rows = [user_index[s["user_id"]] for s in swipes]
    cols = [item_index[s["target_id"]] for s in swipes]
    # A right-swipe is a positive signal; a left-swipe is weak negative evidence, not absence.
    data = [1.0 if s.get("direction") == "right" else 0.1 for s in swipes]

    matrix = csr_matrix((data, (rows, cols)), shape=(len(users), len(items)))
    model = AlternatingLeastSquares(factors=factors, iterations=15, regularization=0.05)
    model.fit(matrix)

    return {
        "user_factors": {
            uid: np.asarray(model.user_factors[i]).tolist() for uid, i in user_index.items()
        },
        "item_factors": {
            iid: np.asarray(model.item_factors[i]).tolist() for iid, i in item_index.items()
        },
    }
