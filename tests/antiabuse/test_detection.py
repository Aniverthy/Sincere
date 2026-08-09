"""Dwell-rule tests (FR-5.1-5.3, §18).

§24 Security: "dwell-ms spoof detection". §11's principle is also asserted here: low-intent
swiping is a conduct problem, not a ranking penalty — nothing in this module touches §12.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sincere.antiabuse.detection import (
    effective_dwell,
    evaluate_window,
    is_separate_occasion,
    next_action,
    warning_message,
)

THRESHOLD_MS = 10_000
RATIO = 0.70
MIN_SWIPES = 25


def swipes(*, right_fast: int = 0, right_slow: int = 0, left_fast: int = 0) -> list[dict]:
    out = []
    out += [{"direction": "right", "dwell_ms": 500, "server_dwell_ms": None}] * right_fast
    out += [{"direction": "right", "dwell_ms": 25_000, "server_dwell_ms": None}] * right_slow
    out += [{"direction": "left", "dwell_ms": 300, "server_dwell_ms": None}] * left_fast
    return out


class TestDwellRule:
    """FR-5.2: <10 s dwell on >70% of right-swipes."""

    def test_trips_above_seventy_percent(self) -> None:
        verdict = evaluate_window(
            swipes(right_fast=80, right_slow=20),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert verdict.tripped is True
        assert verdict.ratio == pytest.approx(0.80)

    def test_does_not_trip_at_exactly_seventy_percent(self) -> None:
        """FR-5.2 says ">70%", so exactly 70 is not a violation."""
        verdict = evaluate_window(
            swipes(right_fast=70, right_slow=30),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert verdict.ratio == pytest.approx(0.70)
        assert verdict.tripped is False

    def test_left_swipes_are_not_counted(self) -> None:
        """FR-5.2's denominator is right-swipes only. Fast left-swiping is discernment —
        counting it would punish the exact behaviour the product wants."""
        verdict = evaluate_window(
            swipes(right_fast=2, right_slow=30, left_fast=500),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert verdict.right_swipes == 32
        assert verdict.tripped is False

    def test_too_few_swipes_is_not_evaluated(self) -> None:
        """A handful of quick likes is not a pattern — banning on it would be indefensible."""
        verdict = evaluate_window(
            swipes(right_fast=10),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert verdict.evaluated is False
        assert verdict.tripped is False

    def test_empty_window_is_safe(self) -> None:
        verdict = evaluate_window(
            [], dwell_threshold_ms=THRESHOLD_MS, dwell_ratio=RATIO, min_swipes=MIN_SWIPES
        )
        assert verdict.tripped is False and verdict.evaluated is False

    def test_careful_swiper_never_trips(self) -> None:
        verdict = evaluate_window(
            swipes(right_slow=100),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert verdict.tripped is False
        assert verdict.ratio == 0.0

    def test_verdict_explains_itself(self) -> None:
        """A ban must be explicable to the person receiving it."""
        verdict = evaluate_window(
            swipes(right_fast=90, right_slow=10),
            dwell_threshold_ms=THRESHOLD_MS,
            dwell_ratio=RATIO,
            min_swipes=MIN_SWIPES,
        )
        assert "90 of 100" in verdict.reason


class TestSpoofDetection:
    """§18: the client is untrusted, so ``dwell_ms`` is cross-checked server-side."""

    def test_inflated_claim_is_clamped_to_server_timing(self) -> None:
        """A bot claiming 60 s of reading when the profile was served 400 ms ago is lying;
        the server figure is an upper bound on what was possible."""
        assert effective_dwell(claimed_ms=60_000, server_ms=400) == 400

    def test_honest_claim_passes_through(self) -> None:
        assert effective_dwell(claimed_ms=8_000, server_ms=9_000) == 8_000

    def test_claim_below_server_time_is_trusted(self) -> None:
        """The user may have left the app open — a short claim under a long window is
        plausible and is taken at face value."""
        assert effective_dwell(claimed_ms=3_000, server_ms=300_000) == 3_000

    def test_missing_server_timing_falls_back_to_the_claim(self) -> None:
        assert effective_dwell(claimed_ms=5_000, server_ms=None) == 5_000

    def test_negative_claims_are_floored(self) -> None:
        assert effective_dwell(claimed_ms=-1_000, server_ms=None) == 0

    def test_spoofed_window_still_trips_the_rule(self) -> None:
        """The whole point: inflating dwell_ms must not buy immunity."""
        spoofed = [
            {"direction": "right", "dwell_ms": 999_999, "server_dwell_ms": 200} for _ in range(100)
        ]
        verdict = evaluate_window(
            spoofed, dwell_threshold_ms=THRESHOLD_MS, dwell_ratio=RATIO, min_swipes=MIN_SWIPES
        )
        assert verdict.tripped is True
        assert verdict.ratio == pytest.approx(1.0)


class TestEscalation:
    """FR-5.3: 3 warnings on **separate occasions**, then ban."""

    def test_first_warning_is_always_a_separate_occasion(self) -> None:
        assert is_separate_occasion(None, datetime.now(UTC), 24) is True

    def test_same_session_is_one_occasion(self) -> None:
        """Otherwise a single bad session issues three warnings and bans someone who never
        had a chance to change their behaviour."""
        now = datetime.now(UTC)
        assert is_separate_occasion(now - timedelta(minutes=5), now, 24) is False

    def test_next_day_is_a_new_occasion(self) -> None:
        now = datetime.now(UTC)
        assert is_separate_occasion(now - timedelta(hours=25), now, 24) is True

    def test_third_occasion_bans(self) -> None:
        assert next_action(warning_count=0, warnings_before_ban=3) == "warn"
        assert next_action(warning_count=1, warnings_before_ban=3) == "warn"
        assert next_action(warning_count=2, warnings_before_ban=3) == "ban"

    def test_warning_copy_counts_down(self) -> None:
        first = warning_message(1, 3)
        second = warning_message(2, 3)
        assert "1 of 3" in first and "2 more" in first
        assert "2 of 3" in second and "1 more" in second

    def test_ban_copy_does_not_offer_another_chance(self) -> None:
        assert "suspended" in warning_message(3, 3)
        assert "more and your account" not in warning_message(3, 3)


def test_detection_does_not_touch_scoring() -> None:
    """§11: "low-intent swiping is a **conduct problem, not a ranking penalty**".

    Structural check that the anti-abuse track never imports the scoring module — the two
    systems are deliberately separate (FR-5.3).
    """
    import inspect

    import sincere.antiabuse.detection as detection_module
    import sincere.antiabuse.service as service_module

    for module in (detection_module, service_module):
        source = inspect.getsource(module)
        assert "matching.scoring" not in source
        assert "blended_score" not in source
