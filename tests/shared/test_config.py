"""Threshold invariant tests.

Every assertion here traces to a value the decision record marked **(DECIDED)**. These are
the guardrails that stop a well-meaning config change from silently breaking a documented
product guarantee — §24 lists exactly this under "Unit".
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sincere.shared.config import Thresholds, get_default_thresholds


class TestDocumentedDefaults:
    """The launch defaults must be the values the docs state, not approximations."""

    def test_hysteresis_band_matches_fr_2_4(self, thresholds: Thresholds) -> None:
        assert thresholds.ratio_upper_band == 1.05
        assert thresholds.ratio_lower_band == 0.95

    def test_slot_split_matches_fr_2_7(self, thresholds: Thresholds) -> None:
        assert thresholds.queue_split_free == 0.60
        assert thresholds.queue_split_paid == 0.25
        assert thresholds.queue_split_auction == 0.15

    def test_daily_match_count_matches_fr_3_1(self, thresholds: Thresholds) -> None:
        assert thresholds.daily_match_count == 15

    def test_graduation_matches_fr_3_4(self, thresholds: Thresholds) -> None:
        assert thresholds.graduation_swipes == 20
        assert thresholds.graduation_matches == 3

    def test_dwell_rule_matches_fr_5_2(self, thresholds: Thresholds) -> None:
        assert thresholds.dwell_threshold_ms == 10_000
        assert thresholds.dwell_ratio == 0.70

    def test_warnings_before_ban_matches_fr_5_3(self, thresholds: Thresholds) -> None:
        assert thresholds.warnings_before_ban == 3

    def test_duplicate_threshold_matches_fr_1_4(self, thresholds: Thresholds) -> None:
        assert thresholds.duplicate_similarity_threshold == 0.90

    def test_h3_resolution_matches_fr_2_1(self, thresholds: Thresholds) -> None:
        assert thresholds.h3_resolution == 6

    def test_wemet_trigger_matches_fr_4_3(self, thresholds: Thresholds) -> None:
        assert thresholds.wemet_trigger_messages == 20
        assert thresholds.wemet_trigger_messages_max == 30
        assert thresholds.wemet_trigger_window_days == 3

    def test_retention_windows_match_section_8(self, thresholds: Thresholds) -> None:
        assert thresholds.grace_period_days == 30
        assert thresholds.message_retention_days_post_unmatch == 90
        assert thresholds.device_signal_retention_days == 90

    def test_radius_bounds_match_fr_3_2(self, thresholds: Thresholds) -> None:
        assert thresholds.radius_min_km == 1
        assert thresholds.radius_max_km == 100

    def test_exploration_rates_match_fr_3_5(self, thresholds: Thresholds) -> None:
        assert thresholds.exploration_rate_pre_graduation == 0.40
        assert thresholds.exploration_rate_post_graduation == 0.15


class TestScoringWeights:
    """§12 weights. Scores stop being comparable across users if these drift off 1.0."""

    def test_cold_start_weights_match_section_12(self, thresholds: Thresholds) -> None:
        assert thresholds.weight_cold_preference == 0.45
        assert thresholds.weight_cold_demographic == 0.30
        assert thresholds.weight_cold_prompt == 0.25

    def test_final_weights_match_section_12(self, thresholds: Thresholds) -> None:
        assert thresholds.weight_final_reciprocity == 0.35
        assert thresholds.weight_final_collaborative == 0.25
        assert thresholds.weight_final_preference == 0.20
        assert thresholds.weight_final_engagement == 0.10
        assert thresholds.weight_final_freshness == 0.05
        assert thresholds.weight_final_visual == 0.05

    def test_reciprocity_is_the_heaviest_signal(self, thresholds: Thresholds) -> None:
        """§11 step 4: "the candidate's predicted like-back probability is *the* heaviest
        signal". A reweighting that broke this would change the product's thesis."""
        weights = {
            "reciprocity": thresholds.weight_final_reciprocity,
            "collaborative": thresholds.weight_final_collaborative,
            "preference": thresholds.weight_final_preference,
            "engagement": thresholds.weight_final_engagement,
            "freshness": thresholds.weight_final_freshness,
            "visual": thresholds.weight_final_visual,
        }
        assert max(weights, key=weights.__getitem__) == "reciprocity"


class TestRejectedConfigurations:
    """Invariants that must refuse to load rather than misbehave at runtime."""

    def test_zero_width_hysteresis_band_is_rejected(self) -> None:
        """FR-2.4: without a gap between freeze and resume, the state machine flaps."""
        with pytest.raises(ValidationError, match="strictly below"):
            Thresholds(ratio_upper_band=1.0, ratio_lower_band=1.0)

    def test_inverted_hysteresis_band_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="strictly below"):
            Thresholds(ratio_upper_band=0.90, ratio_lower_band=0.95)

    def test_slot_split_not_summing_to_one_is_rejected(self) -> None:
        """FR-2.7: the three tiers partition one ceiling."""
        with pytest.raises(ValidationError, match="sum to 1.0"):
            Thresholds(queue_split_free=0.70)

    def test_final_weights_not_summing_to_one_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"final_score weights"):
            Thresholds(weight_final_reciprocity=0.50)

    def test_cold_start_weights_not_summing_to_one_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"cold_start_score weights"):
            Thresholds(weight_cold_preference=0.60)

    def test_visual_weight_cannot_be_tuned(self) -> None:
        """FR-3.6 fixes it at 0.05 by decision record. Even a sum-preserving change fails."""
        with pytest.raises(ValidationError, match="fixed at 0.05"):
            Thresholds(weight_final_visual=0.10, weight_final_freshness=0.0)

    def test_bot_risk_bands_must_leave_a_review_middle(self) -> None:
        """FR-1.6: the ambiguous middle band is the whole point of 3-band routing —
        collapsing it would mean every signup is auto-decided."""
        with pytest.raises(ValidationError, match="human-review middle"):
            Thresholds(bot_risk_auto_approve_below=0.90, bot_risk_auto_reject_above=0.80)


class TestProductionGuards:
    """Settings that must refuse to boot in production."""

    @pytest.mark.parametrize(
        "secret",
        [
            "dev-only-insecure-secret-change-me",  # the shipped default
            "short",  # under the 32-char floor
            "test-secret-not-used-in-any-real-deployment",  # a test value leaking through
        ],
    )
    def test_weak_jwt_secret_rejected_in_production(self, secret: str) -> None:
        from sincere.shared.config import Settings

        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(
                environment="production",
                jwt_secret=secret,
                mongodb_uri="mongodb+srv://cluster/sincere",
            )

    def test_strong_jwt_secret_accepted_in_production(self) -> None:
        from sincere.shared.config import Settings

        settings = Settings(
            environment="production",
            jwt_secret="Yb3F" * 12,
            mongodb_uri="mongodb+srv://cluster/sincere",
        )
        assert settings.environment == "production"

    def test_non_atlas_uri_rejected_in_production(self) -> None:
        """§9 duplicate detection (FR-1.4) requires Atlas Vector Search — a plain
        mongodb:// URI in production means duplicate detection silently does not run."""
        from sincere.shared.config import Settings

        with pytest.raises(ValidationError, match="Atlas"):
            Settings(
                environment="production",
                jwt_secret="Yb3F" * 12,
                mongodb_uri="mongodb://localhost:27017",
            )


def test_thresholds_are_all_documented() -> None:
    """Every threshold must carry a docstring naming the FR or section it implements.

    Guards against an undocumented magic number entering config, which is how launch
    defaults quietly become untraceable.
    """
    undocumented = [
        name
        for name, field in get_default_thresholds().model_fields.items()
        if not field.description and name not in Thresholds.__doc__
    ]
    # Pydantic keeps prose docstrings out of `description`; assert the source instead.
    import inspect

    source = inspect.getsource(Thresholds)
    missing = [name for name in undocumented if f"{name}:" in source and '"""' not in source]
    assert not missing, f"Thresholds without documentation: {missing}"
