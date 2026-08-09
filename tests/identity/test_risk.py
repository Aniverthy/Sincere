"""Bot-risk scoring and 3-band routing tests (FR-1.4, FR-1.6).

The rule this file exists to protect is FR-1.4's "**never auto-ban**". A duplicate face is
evidence of an identical twin or a returning user as often as it is evidence of fraud, so it
must always reach a human. §24 puts this class of decision logic under "Unit".
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from sincere.identity.risk import RiskSignals, bio_spam_score, route, score
from sincere.identity.schemas import RiskBand
from sincere.shared.config import Thresholds


@pytest.fixture
def clean() -> RiskSignals:
    """A signup with nothing suspicious about it."""
    return RiskSignals(
        liveness_passed=True,
        photo_selfie_match=True,
        duplicate_similarity=None,
        device_reuse_count=0,
        ip_cluster_count=0,
        signup_velocity=0,
        bio_text="Long walks and filter coffee.",
    )


class TestBandRouting:
    """FR-1.6: auto-approve / human-review / auto-reject."""

    def test_clean_signup_auto_approves(self, clean: RiskSignals, thresholds: Thresholds) -> None:
        assessment = score(clean, thresholds)
        assert assessment.band is RiskBand.AUTO_APPROVE
        assert assessment.composite_score < thresholds.bot_risk_auto_approve_below

    def test_failed_liveness_auto_rejects(self, thresholds: Thresholds) -> None:
        """A failed liveness check is the strongest single signal (FR-1.2)."""
        signals = RiskSignals(
            liveness_passed=False,
            photo_selfie_match=False,
            device_reuse_count=6,
            ip_cluster_count=20,
            bio_text="Invest with me daily profit — whatsapp +1555",
        )
        assert score(signals, thresholds).band is RiskBand.AUTO_REJECT

    def test_middling_evidence_goes_to_human_review(self, thresholds: Thresholds) -> None:
        """Enough doubt to not wave through, not enough to reject — FR-1.6's whole point."""
        signals = RiskSignals(
            liveness_passed=None,      # could not be evaluated
            photo_selfie_match=False,  # photos do not match the selfie
            device_reuse_count=2,
        )
        assert score(signals, thresholds).band is RiskBand.REVIEW

    def test_faint_signals_still_auto_approve(self, thresholds: Thresholds) -> None:
        """A shared device alone must not queue a real person for manual review — §21 alerts
        when review depth outgrows founder capacity, so the bar has to mean something."""
        signals = RiskSignals(
            liveness_passed=True, photo_selfie_match=True, device_reuse_count=1
        )
        assert score(signals, thresholds).band is RiskBand.AUTO_APPROVE

    def test_weights_sum_to_one_so_bands_are_reachable(self) -> None:
        """The FR-1.6 bands are expressed on 0-1; if the weights did not span that range the
        auto-reject band would be unreachable in practice."""
        from sincere.identity.risk import WEIGHTS

        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
        assert "duplicate" not in WEIGHTS, "FR-1.4 makes duplicates a routing override, not a score"

    def test_unevaluated_liveness_is_not_treated_as_passed(
        self, clean: RiskSignals, thresholds: Thresholds
    ) -> None:
        """An unevaluated check must not score the same as a passed one — otherwise a
        pipeline failure becomes a free pass."""
        unknown = replace(clean, liveness_passed=None)
        assert score(unknown, thresholds).composite_score > score(clean, thresholds).composite_score


class TestDuplicateNeverAutoBans:
    """FR-1.4 (DECIDED): ">90% cosine similarity → human review, **never auto-ban**"."""

    def test_duplicate_forces_review_even_when_score_says_approve(
        self, clean: RiskSignals, thresholds: Thresholds
    ) -> None:
        signals = replace(clean, duplicate_similarity=0.97)
        assert score(signals, thresholds).band is RiskBand.REVIEW

    def test_duplicate_forces_review_even_when_score_says_reject(
        self, thresholds: Thresholds
    ) -> None:
        """The override is the LAST word. A near-identical face plus every other red flag is
        still a human decision — banning an identical twin is the failure this prevents."""
        signals = RiskSignals(
            liveness_passed=False,
            photo_selfie_match=False,
            device_reuse_count=10,
            ip_cluster_count=30,
            bio_text="crypto profit guaranteed daily http://scam.example",
            duplicate_similarity=0.99,
        )
        assessment = score(signals, thresholds)
        assert assessment.composite_score > thresholds.bot_risk_auto_reject_above
        assert assessment.band is RiskBand.REVIEW, "a duplicate must never auto-reject"

    def test_similarity_below_threshold_does_not_force_review(
        self, clean: RiskSignals, thresholds: Thresholds
    ) -> None:
        just_under = thresholds.duplicate_similarity_threshold - 0.01
        signals = replace(clean, duplicate_similarity=just_under)
        assert score(signals, thresholds).band is RiskBand.AUTO_APPROVE

    def test_similarity_scales_for_the_reviewer(self, thresholds: Thresholds) -> None:
        """The duplicate strength is not scored (see WEIGHTS) but IS reported, so the human
        reviewer can tell a borderline match from a near-identical one."""
        low = score(RiskSignals(liveness_passed=True, duplicate_similarity=0.91), thresholds)
        high = score(RiskSignals(liveness_passed=True, duplicate_similarity=0.999), thresholds)

        assert high.normalized["duplicate"] > low.normalized["duplicate"]
        # Both still route to review, and neither is dragged toward auto-reject by it.
        assert low.band is high.band is RiskBand.REVIEW
        assert high.composite_score == low.composite_score

    def test_duplicate_does_not_inflate_the_composite(
        self, clean: RiskSignals, thresholds: Thresholds
    ) -> None:
        """A duplicate must not push an otherwise-clean account toward rejection — it only
        changes the routing (FR-1.4)."""
        flagged = replace(clean, duplicate_similarity=0.99)
        assert (
            score(flagged, thresholds).composite_score
            == score(clean, thresholds).composite_score
        )

    @pytest.mark.parametrize("composite", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_no_composite_score_can_auto_reject_a_duplicate(
        self, composite: float, thresholds: Thresholds
    ) -> None:
        signals = RiskSignals(duplicate_similarity=0.95)
        assert route(composite, signals, thresholds) is not RiskBand.AUTO_REJECT


class TestSignalNormalization:
    def test_device_reuse_saturates(self, thresholds: Thresholds) -> None:
        """30 shared devices and 60 are both simply "a device farm" — the score should not
        keep climbing linearly."""
        many = score(RiskSignals(liveness_passed=True, device_reuse_count=30), thresholds)
        more = score(RiskSignals(liveness_passed=True, device_reuse_count=60), thresholds)
        assert more.composite_score - many.composite_score < 0.02

    def test_zero_counts_contribute_nothing(self, thresholds: Thresholds) -> None:
        assessment = score(RiskSignals(liveness_passed=True, photo_selfie_match=True), thresholds)
        assert assessment.normalized["device_reuse"] == 0.0
        assert assessment.normalized["ip_cluster"] == 0.0

    def test_composite_stays_in_unit_range(self, thresholds: Thresholds) -> None:
        worst = RiskSignals(
            liveness_passed=False,
            photo_selfie_match=False,
            duplicate_similarity=1.0,
            device_reuse_count=999,
            ip_cluster_count=999,
            signup_velocity=9999,
            bio_text="whatsapp +1555 bitcoin invest guaranteed daily http://x.example sugar daddy",
        )
        assert 0.0 <= score(worst, thresholds).composite_score <= 1.0


class TestBioSpamDetection:
    """FR-5.4 "spam-template bio detection"."""

    @pytest.mark.parametrize(
        "bio",
        [
            "Message me on whatsapp +919876543210",
            "Bitcoin trading, guaranteed profit daily",
            "Check out http://my-link.example",
            "Looking for a sugar daddy",
        ],
    )
    def test_spam_templates_are_flagged(self, bio: str) -> None:
        assert bio_spam_score(bio) > 0

    @pytest.mark.parametrize(
        "bio",
        [
            "",
            "Architect. I make bread on Sundays and argue about films.",
            "Dog person. Will beat you at badminton.",
            "I invest my weekends in hiking.",
        ],
    )
    def test_ordinary_bios_are_not_flagged(self, bio: str) -> None:
        """A false positive only costs a human review, but it should still be rare — note
        'invest' alone must not trip the trading pattern."""
        assert bio_spam_score(bio) == 0


def test_reasons_are_human_readable(thresholds: Thresholds) -> None:
    """FR-1.7's reviewer needs to know *why* an account was queued, not just a number."""
    signals = RiskSignals(
        liveness_passed=True, duplicate_similarity=0.94, device_reuse_count=3
    )
    reasons = score(signals, thresholds).reasons
    assert any("face matches an existing account" in reason for reason in reasons)
    assert any("device shared with" in reason for reason in reasons)
