"""Scoring formula tests (§12).

§24 Unit: "Scoring formulas (cold-start/final/blended/confidence — **exact-value tests against
hand-computed fixtures**)".
§24 ML: "cold-start↔learned blend continuity (**no score cliffs at graduation**)".

Every expected value below is computed by hand from the §12 formulas, not read back from the
implementation — otherwise the test would only assert that the code equals itself.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sincere.matching.scoring import (
    Features,
    apply_visual_cap,
    blended_score,
    cold_start_score,
    confidence,
    demographic_fit,
    engagement_score,
    exploration_rate,
    final_score,
    freshness_boost,
    has_graduated,
    preference_similarity,
    score_candidate,
    visual_pattern_similarity,
)
from sincere.shared.config import Thresholds


class TestColdStartScore:
    """cold_start = 0.45·preference + 0.30·demographic + 0.25·prompt"""

    def test_hand_computed_value(self, thresholds: Thresholds) -> None:
        features = Features(
            preference_similarity=0.8, demographic_fit=0.6, prompt_text_similarity=0.4
        )
        # 0.45(0.8) + 0.30(0.6) + 0.25(0.4) = 0.36 + 0.18 + 0.10 = 0.64
        assert cold_start_score(features, thresholds) == pytest.approx(0.64)

    def test_all_ones_gives_one(self, thresholds: Thresholds) -> None:
        features = Features(
            preference_similarity=1.0, demographic_fit=1.0, prompt_text_similarity=1.0
        )
        assert cold_start_score(features, thresholds) == pytest.approx(1.0)

    def test_all_zeros_gives_zero(self, thresholds: Thresholds) -> None:
        features = Features(
            preference_similarity=0.0, demographic_fit=0.0, prompt_text_similarity=0.0
        )
        assert cold_start_score(features, thresholds) == pytest.approx(0.0)

    def test_preference_dominates_cold_start(self, thresholds: Thresholds) -> None:
        """0.45 is the largest cold-start weight — stated interests are the best signal
        available before anyone has swiped."""
        pref_only = cold_start_score(Features(preference_similarity=1.0), thresholds)
        demo_only = cold_start_score(Features(demographic_fit=1.0), thresholds)
        prompt_only = cold_start_score(Features(prompt_text_similarity=1.0), thresholds)
        assert pref_only > demo_only > prompt_only


class TestFinalScore:
    """final = 0.35·recip + 0.25·cf + 0.20·pref + 0.10·engage + 0.05·fresh + 0.05·visual"""

    def test_hand_computed_value(self, thresholds: Thresholds) -> None:
        features = Features(
            reciprocity_prediction=0.8,
            collaborative_filtering=0.6,
            preference_similarity=0.5,
            engagement_score=0.4,
            freshness_boost=0.2,
            visual_pattern_similarity=0.5,
        )
        # 0.35(0.8)=0.280  0.25(0.6)=0.150  0.20(0.5)=0.100
        # 0.10(0.4)=0.040  0.05(0.2)=0.010  0.05(0.5)=0.025  => 0.605
        assert final_score(features, thresholds) == pytest.approx(0.605)

    def test_all_ones_gives_one(self, thresholds: Thresholds) -> None:
        features = Features(
            reciprocity_prediction=1.0,
            collaborative_filtering=1.0,
            preference_similarity=1.0,
            engagement_score=1.0,
            freshness_boost=1.0,
            visual_pattern_similarity=1.0,
        )
        assert final_score(features, thresholds) == pytest.approx(1.0)

    def test_reciprocity_is_the_heaviest_term(self, thresholds: Thresholds) -> None:
        """§11 step 4: the candidate's like-back probability is *the* heaviest signal."""
        recip = final_score(Features(reciprocity_prediction=1.0), thresholds)
        cf = final_score(Features(collaborative_filtering=1.0), thresholds)
        # Features() defaults visual_pattern_similarity to the FR-3.6 neutral 0.5, which
        # contributes 0.05 x 0.5 = 0.025 to every score. So 0.35 + 0.025 = 0.375.
        assert recip == pytest.approx(0.375)
        assert recip > cf

    def test_visual_contributes_exactly_five_percent(self, thresholds: Thresholds) -> None:
        """FR-3.6 fixes this weight; a change here changes the product's legal posture."""
        base = final_score(Features(visual_pattern_similarity=0.0), thresholds)
        maxed = final_score(Features(visual_pattern_similarity=1.0), thresholds)
        assert maxed - base == pytest.approx(0.05)


class TestConfidence:
    """confidence(n) = min(1, log(1+n) / log(1+N_mature))"""

    def test_zero_swipes_gives_zero_confidence(self, thresholds: Thresholds) -> None:
        """§10: pre-graduation confidence is 0, so blended degenerates to pure cold-start."""
        assert confidence(0, thresholds.confidence_mature_swipes) == 0.0

    def test_hand_computed_midpoint(self) -> None:
        # log(1+50)/log(1+200) = log(51)/log(201) = 3.93183/5.30330 = 0.741
        assert confidence(50, 200) == pytest.approx(math.log(51) / math.log(201))
        assert confidence(50, 200) == pytest.approx(0.74140, abs=1e-4)

    def test_reaches_one_at_maturity(self) -> None:
        assert confidence(200, 200) == pytest.approx(1.0)

    def test_caps_at_one_beyond_maturity(self) -> None:
        assert confidence(10_000, 200) == 1.0

    def test_curve_is_monotonic(self) -> None:
        from itertools import pairwise

        values = [confidence(n, 200) for n in range(0, 200, 10)]
        assert all(b >= a for a, b in pairwise(values))

    def test_early_swipes_carry_more_weight_than_late_ones(self) -> None:
        """§12's stated rationale for the log form: "early post-graduation swipes carry the
        most new information, so model weight should rise fast then flatten"."""
        first_ten = confidence(10, 200) - confidence(0, 200)
        last_ten = confidence(200, 200) - confidence(190, 200)
        assert first_ten > last_ten


class TestBlendedScore:
    """blended = confidence·final + (1 - confidence)·cold"""

    def test_hand_computed_value(self) -> None:
        # 0.6(0.8) + 0.4(0.5) = 0.48 + 0.20 = 0.68
        assert blended_score(cold=0.5, final=0.8, conf=0.6) == pytest.approx(0.68)

    def test_zero_confidence_is_pure_cold_start(self) -> None:
        assert blended_score(cold=0.42, final=0.99, conf=0.0) == pytest.approx(0.42)

    def test_full_confidence_is_pure_final(self) -> None:
        assert blended_score(cold=0.42, final=0.99, conf=1.0) == pytest.approx(0.99)

    def test_no_score_cliff_at_graduation(self, thresholds: Thresholds) -> None:
        """§24 ML: "no score cliffs at graduation".

        The instant a user graduates, n = 0, so confidence = 0 and the blended score equals
        exactly what it was the moment before. A step function here would visibly reshuffle
        everyone's matches on their 20th swipe.
        """
        features = Features(
            preference_similarity=0.7,
            demographic_fit=0.5,
            prompt_text_similarity=0.3,
            reciprocity_prediction=0.9,
            collaborative_filtering=0.9,
        )
        before = score_candidate("c1", features, post_graduation_swipes=0, thresholds=thresholds)
        assert before.blended_score == pytest.approx(before.cold_start_score)

        # And the first post-graduation swipe moves it only slightly, not in a jump.
        after = score_candidate("c1", features, post_graduation_swipes=1, thresholds=thresholds)
        assert abs(after.blended_score - before.blended_score) < 0.05

    @given(
        cold=st.floats(min_value=0, max_value=1),
        final=st.floats(min_value=0, max_value=1),
        conf=st.floats(min_value=0, max_value=1),
    )
    @settings(max_examples=200, deadline=None)
    def test_blend_always_lies_between_its_inputs(
        self, cold: float, final: float, conf: float
    ) -> None:
        result = blended_score(cold, final, conf)
        assert min(cold, final) - 1e-9 <= result <= max(cold, final) + 1e-9


class TestGraduation:
    """FR-3.4: 20+ swipes AND 3+ matches."""

    def test_requires_both_conditions(self, thresholds: Thresholds) -> None:
        assert has_graduated(20, 3, thresholds) is True
        assert has_graduated(19, 3, thresholds) is False
        assert has_graduated(20, 2, thresholds) is False
        assert has_graduated(1_000, 2, thresholds) is False, "swipes alone must not graduate"
        assert has_graduated(5, 50, thresholds) is False, "matches alone must not graduate"

    def test_exploration_rate_by_stage(self, thresholds: Thresholds) -> None:
        """FR-3.5: ~40% pre-graduation, ~15% post."""
        assert exploration_rate(graduated=False, thresholds=thresholds) == 0.40
        assert exploration_rate(graduated=True, thresholds=thresholds) == 0.15


class TestVisualPattern:
    """FR-3.6: fixed 0.05 weight, capped above 0.95, neutral on thin history."""

    def test_thin_history_returns_neutral(self, thresholds: Thresholds) -> None:
        assert visual_pattern_similarity([1.0, 0.0], [1.0, 0.0], 2, thresholds) == 0.5

    def test_missing_centroid_returns_neutral(self, thresholds: Thresholds) -> None:
        assert visual_pattern_similarity([1.0, 0.0], None, 50, thresholds) == 0.5

    def test_below_cap_passes_through(self, thresholds: Thresholds) -> None:
        assert apply_visual_cap(0.80, thresholds) == pytest.approx(0.80)

    def test_at_cap_passes_through(self, thresholds: Thresholds) -> None:
        assert apply_visual_cap(0.95, thresholds) == pytest.approx(0.95)

    def test_above_cap_is_discounted_toward_neutral(self, thresholds: Thresholds) -> None:
        """A near-identical face is more likely a duplicate account than a preference match,
        so it must not rank higher than a genuinely similar one."""
        assert apply_visual_cap(1.0, thresholds) < apply_visual_cap(0.95, thresholds)
        assert apply_visual_cap(1.0, thresholds) == pytest.approx(0.5)

    def test_discount_is_monotonic_above_the_cap(self, thresholds: Thresholds) -> None:
        assert apply_visual_cap(0.96, thresholds) > apply_visual_cap(0.99, thresholds)


class TestFeatureComputation:
    def test_preference_similarity_of_identical_tags_is_one(self) -> None:
        assert preference_similarity(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)

    def test_preference_similarity_of_disjoint_tags_is_zero(self) -> None:
        assert preference_similarity(["a"], ["b"]) == 0.0

    def test_preference_similarity_hand_computed(self) -> None:
        # shared = 2, |A| = 4, |B| = 4  ->  2 / sqrt(16) = 0.5
        assert preference_similarity(
            ["a", "b", "c", "d"], ["a", "b", "e", "f"]
        ) == pytest.approx(0.5)

    def test_empty_tags_score_zero(self) -> None:
        assert preference_similarity([], ["a"]) == 0.0

    def test_demographic_fit_is_best_when_close_and_same_age(self) -> None:
        near = demographic_fit(age_gap_years=0, distance_km=0, radius_km=50)
        far = demographic_fit(age_gap_years=20, distance_km=50, radius_km=50)
        assert near == pytest.approx(1.0)
        assert far < 0.2

    def test_distance_is_scored_against_the_users_own_radius(self) -> None:
        """20 km is far for someone who asked for 25 km, near for someone who asked for 100."""
        tight = demographic_fit(age_gap_years=0, distance_km=20, radius_km=25)
        loose = demographic_fit(age_gap_years=0, distance_km=20, radius_km=100)
        assert loose > tight

    def test_freshness_halves_each_halflife(self) -> None:
        now = datetime(2026, 8, 9, tzinfo=UTC)
        assert freshness_boost(now, 7.0, now) == pytest.approx(1.0)
        assert freshness_boost(now - timedelta(days=7), 7.0, now) == pytest.approx(0.5)
        assert freshness_boost(now - timedelta(days=14), 7.0, now) == pytest.approx(0.25)

    def test_engagement_decays_on_stagnation(self) -> None:
        """§12: "decays on stagnation"."""
        fresh = engagement_score(
            message_count=40, avg_response_latency_s=600, days_since_last_message=0
        )
        stale = engagement_score(
            message_count=40, avg_response_latency_s=600, days_since_last_message=21
        )
        assert fresh > stale
        assert stale < 0.2

    def test_engagement_rewards_fast_replies(self) -> None:
        quick = engagement_score(
            message_count=20, avg_response_latency_s=300, days_since_last_message=0
        )
        slow = engagement_score(
            message_count=20, avg_response_latency_s=172_800, days_since_last_message=0
        )
        assert quick > slow


@given(
    pref=st.floats(min_value=0, max_value=1),
    demo=st.floats(min_value=0, max_value=1),
    prompt=st.floats(min_value=0, max_value=1),
    recip=st.floats(min_value=0, max_value=1),
    cf=st.floats(min_value=0, max_value=1),
    swipes=st.integers(min_value=0, max_value=5_000),
)
@settings(max_examples=200, deadline=None)
def test_every_score_stays_in_unit_range(
    pref: float, demo: float, prompt: float, recip: float, cf: float, swipes: int
) -> None:
    """§12 declares every variable 0-1; a score outside that range makes candidates from
    different users incomparable and would corrupt the ranking."""
    from sincere.shared.config import get_default_thresholds

    thresholds = get_default_thresholds()
    features = Features(
        preference_similarity=pref,
        demographic_fit=demo,
        prompt_text_similarity=prompt,
        reciprocity_prediction=recip,
        collaborative_filtering=cf,
    )
    result = score_candidate("c", features, swipes, thresholds)

    assert 0.0 <= result.cold_start_score <= 1.0
    assert 0.0 <= result.final_score <= 1.0
    assert 0.0 <= result.blended_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
