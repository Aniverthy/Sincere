"""Holdout-gating tests (§13, §24 ML).

§13: "Models validated against a holdout set **before promotion**"; on failure, "**Keep
current model**". §24 ML: "Holdout-set gating on every retrain; drift checks between model
versions."

This gate is the only thing preventing a worse model from reaching users, so it gets tested
harder than the training itself.
"""

from __future__ import annotations

import pytest

from sincere.feedback_ml.training import (
    MIN_TRAINING_ROWS,
    PROMOTION_MARGIN,
    auc,
    build_features,
    passes_holdout_gate,
    split_holdout,
)


class TestAuc:
    def test_perfect_separation_scores_one(self) -> None:
        assert auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)

    def test_inverted_predictions_score_zero(self) -> None:
        assert auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == pytest.approx(0.0)

    def test_random_ordering_scores_half(self) -> None:
        assert auc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == pytest.approx(0.5)

    def test_constant_predictions_are_not_perfect(self) -> None:
        """A model that outputs the same number for everyone discriminates nothing. Without
        average-rank tie handling this would score 1.0 and get promoted."""
        assert auc([0.7] * 10, [1, 0] * 5) == pytest.approx(0.5)

    def test_single_class_holdout_is_uninformative(self) -> None:
        """All-positive or all-negative holdouts carry no signal — returning 0.5 makes the
        gate refuse rather than promote on nothing."""
        assert auc([0.1, 0.9], [1, 1]) == 0.5
        assert auc([0.1, 0.9], [0, 0]) == 0.5

    def test_partial_separation_is_between(self) -> None:
        score = auc([0.1, 0.6, 0.4, 0.9], [0, 0, 1, 1])
        assert 0.0 < score < 1.0


class TestHoldoutGate:
    """§13's promotion decision."""

    def test_first_model_promotes_when_better_than_chance(self) -> None:
        promote, reason = passes_holdout_gate(0.72, incumbent_auc=None)
        assert promote is True
        assert "first model" in reason

    def test_first_model_is_refused_when_no_better_than_chance(self) -> None:
        promote, reason = passes_holdout_gate(0.48, incumbent_auc=None)
        assert promote is False
        assert "chance" in reason

    def test_worse_than_incumbent_keeps_current_model(self) -> None:
        """§13's diagram: holdout fail -> "Keep current model"."""
        promote, reason = passes_holdout_gate(0.65, incumbent_auc=0.75)
        assert promote is False
        assert "keeping the current model" in reason

    def test_marginal_improvement_is_refused_as_noise(self) -> None:
        """An improvement smaller than run-to-run variance is not an improvement — promoting
        on it would churn the ranking for no benefit."""
        promote, _ = passes_holdout_gate(0.7505, incumbent_auc=0.75)
        assert promote is False

    def test_clear_improvement_promotes(self) -> None:
        promote, reason = passes_holdout_gate(0.80, incumbent_auc=0.75)
        assert promote is True
        assert "beats" in reason

    def test_margin_boundary(self) -> None:
        base = 0.70
        assert passes_holdout_gate(base + PROMOTION_MARGIN, base)[0] is True
        assert passes_holdout_gate(base + PROMOTION_MARGIN - 1e-6, base)[0] is False

    def test_equal_scores_do_not_promote(self) -> None:
        assert passes_holdout_gate(0.75, incumbent_auc=0.75)[0] is False

    @pytest.mark.parametrize("candidate", [0.0, 0.1, 0.3, 0.49])
    def test_nothing_below_chance_ever_promotes(self, candidate: float) -> None:
        """Whatever the incumbent scores, a coin-flip model must never ship."""
        assert passes_holdout_gate(candidate, incumbent_auc=None)[0] is False
        assert passes_holdout_gate(candidate, incumbent_auc=0.4)[0] is False


class TestHoldoutSplit:
    def test_split_is_deterministic(self) -> None:
        """A promotion decision that flips on reshuffling is not a decision."""
        rows = [{"match_id": str(i), "label": i % 2} for i in range(100)]
        first_train, first_hold = split_holdout(rows)
        second_train, second_hold = split_holdout(rows)
        assert [r["match_id"] for r in first_hold] == [r["match_id"] for r in second_hold]
        assert len(first_train) == len(second_train)

    def test_split_partitions_without_overlap(self) -> None:
        rows = [{"match_id": str(i), "label": i % 2} for i in range(100)]
        train, holdout = split_holdout(rows)
        assert len(train) + len(holdout) == 100
        assert not ({r["match_id"] for r in train} & {r["match_id"] for r in holdout})

    def test_holdout_is_roughly_the_requested_fraction(self) -> None:
        rows = [{"match_id": str(i), "label": 0} for i in range(100)]
        _, holdout = split_holdout(rows, fraction=0.2)
        assert len(holdout) == 20

    def test_tiny_dataset_still_yields_a_holdout(self) -> None:
        rows = [{"match_id": "a", "label": 1}, {"match_id": "b", "label": 0}]
        train, holdout = split_holdout(rows)
        assert len(holdout) >= 1 and len(train) >= 1


class TestFeatures:
    def test_missing_latency_is_treated_as_very_slow(self) -> None:
        """``None`` means nobody has replied. Defaulting to 0 would read as instant."""
        features = build_features({"msg_count": 5, "avg_response_latency_s": None})
        assert features["avg_response_latency_s"] == 86_400.0

    def test_conversation_flags(self) -> None:
        silent = build_features({"msg_count": 0})
        brief = build_features({"msg_count": 5})
        sustained = build_features({"msg_count": 25})

        assert silent["has_conversation"] == 0.0
        assert brief["has_conversation"] == 1.0 and brief["sustained_conversation"] == 0.0
        assert sustained["sustained_conversation"] == 1.0

    def test_feature_keys_are_stable(self) -> None:
        """The registry stores a feature ORDER; a renamed key would silently misalign the
        columns at inference time."""
        assert set(build_features({"msg_count": 1})) == {
            "msg_count",
            "avg_response_latency_s",
            "has_conversation",
            "sustained_conversation",
        }


def test_minimum_training_volume_is_enforced() -> None:
    """§25 phase 3 gates the first real training on "We-Met response volume meaningful"."""
    assert MIN_TRAINING_ROWS >= 100
