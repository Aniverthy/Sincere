"""Ratio, hysteresis and slot-allocation tests (FR-2.3-2.7, FR-2.10).

§24 names three things this file must prove:

* Unit: "hysteresis state machine (freeze at x1.05, resume at x0.95, **no flapping under
  oscillating counts**)" and "slot allocation rounding (60/25/15 over small daily slot counts)".
* Property-based: "**no admission sequence may push active_men above ceiling**" and the
  "never-evict invariant".
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sincere.admission.ratio import (
    AdmissionState,
    RatioSnapshot,
    allocate_slots,
    available_slots,
    can_admit_man,
    ceiling,
    engagement_priority,
    next_state,
    profile_completeness,
)
from sincere.shared.config import Thresholds

UPPER = 1.05
LOWER = 0.95
BUFFER = 0.93


class TestHysteresis:
    """FR-2.4 — the band, and why it is a band."""

    def test_freezes_above_upper_band(self) -> None:
        snapshot = RatioSnapshot(active_men=106, active_women=100)  # ratio 1.06
        assert next_state(AdmissionState.OPEN, snapshot, UPPER, LOWER) is AdmissionState.FROZEN

    def test_stays_open_exactly_at_the_upper_band(self) -> None:
        """FR-2.4 freezes *above* the band, so sitting exactly on 1.05 is still open."""
        snapshot = RatioSnapshot(active_men=105, active_women=100)
        assert next_state(AdmissionState.OPEN, snapshot, UPPER, LOWER) is AdmissionState.OPEN

    def test_frozen_stays_frozen_inside_the_band(self) -> None:
        """The dead zone. A frozen region at ratio 1.00 does NOT reopen — it must fall all
        the way below 0.95 first. This is the anti-flapping mechanism."""
        snapshot = RatioSnapshot(active_men=100, active_women=100)
        assert next_state(AdmissionState.FROZEN, snapshot, UPPER, LOWER) is AdmissionState.FROZEN

    def test_reopens_below_lower_band(self) -> None:
        snapshot = RatioSnapshot(active_men=94, active_women=100)  # ratio 0.94
        assert next_state(AdmissionState.FROZEN, snapshot, UPPER, LOWER) is AdmissionState.OPEN

    def test_no_flapping_under_oscillating_counts(self) -> None:
        """§24's named scenario: counts oscillating inside the band must produce at most one
        state change, not one per tick."""
        state = AdmissionState.OPEN
        transitions = 0

        # Oscillate the male count across the band boundary repeatedly.
        for men in [104, 106, 104, 106, 103, 106, 100, 106] * 5:
            new_state = next_state(state, RatioSnapshot(men, 100), UPPER, LOWER)
            if new_state is not state:
                transitions += 1
            state = new_state

        # It freezes once at 106 and never reopens, because the count never drops below 95.
        assert transitions == 1
        assert state is AdmissionState.FROZEN

    def test_zero_women_with_men_freezes(self) -> None:
        """Every woman going inactive must not read as ratio 0 and open the floodgates."""
        snapshot = RatioSnapshot(active_men=10, active_women=0)
        assert snapshot.ratio == float("inf")
        assert next_state(AdmissionState.OPEN, snapshot, UPPER, LOWER) is AdmissionState.FROZEN

    def test_empty_region_stays_open(self) -> None:
        """A brand-new hex has nobody in it; it must be open for the first signups."""
        snapshot = RatioSnapshot(active_men=0, active_women=0)
        assert snapshot.ratio == 0.0
        assert next_state(AdmissionState.OPEN, snapshot, UPPER, LOWER) is AdmissionState.OPEN


class TestCeiling:
    """FR-2.5 — admit men up to ~90-95% of the active-women count."""

    def test_ceiling_applies_the_buffer(self) -> None:
        assert ceiling(100, 0.93) == 93

    def test_ceiling_floors_rather_than_rounds(self) -> None:
        """Rounding up would let the ceiling exceed the buffer it exists to enforce."""
        assert ceiling(10, 0.93) == 9  # 9.3 -> 9, not 10

    def test_headroom_never_goes_negative(self) -> None:
        """Women going inactive (FR-2.3) can push men above the ceiling. FR-2.6 forbids
        evicting anyone, so the answer is zero new slots — never a negative count."""
        assert available_slots(RatioSnapshot(active_men=200, active_women=100), BUFFER) == 0


class TestNeverEvict:
    """FR-2.6 (DECIDED): "**Never evict** existing men on ratio dip — freeze new
    admissions only"."""

    def test_over_ceiling_blocks_admission_but_reports_no_removal(self) -> None:
        snapshot = RatioSnapshot(active_men=150, active_women=100)
        assert can_admit_man(AdmissionState.OPEN, snapshot, BUFFER) is False
        assert available_slots(snapshot, BUFFER) == 0

    def test_module_exposes_no_eviction_path(self) -> None:
        """Structural guarantee: there is no function here that can remove an admitted man.
        FR-2.6 is enforced by absence, not by a runtime check that could be bypassed."""
        import sincere.admission.ratio as ratio_module

        forbidden = {"evict", "remove_man", "demote", "revoke_admission", "kick"}
        assert not forbidden & set(dir(ratio_module))


class TestSlotAllocation:
    """FR-2.7 — 60/25/15, and the rounding §24 calls out at small counts."""

    def test_standard_split_at_a_round_number(self) -> None:
        allocation = allocate_slots(100, 0.60, 0.25, 0.15)
        assert (allocation.free, allocation.paid, allocation.auction) == (60, 25, 15)

    @pytest.mark.parametrize("total", list(range(0, 51)))
    def test_parts_always_sum_to_the_total(self, total: int) -> None:
        """The invariant that matters: naive truncation drops slots, naive rounding
        overshoots the FR-2.4 ceiling. Neither is acceptable."""
        allocation = allocate_slots(total, 0.60, 0.25, 0.15)
        assert allocation.total == total

    def test_small_counts_favour_the_free_tier(self) -> None:
        """FR-2.7 gives free the largest share, so scarce slots should land there first —
        the free queue is the fairness promise, the paid tiers are the revenue."""
        allocation = allocate_slots(1, 0.60, 0.25, 0.15)
        assert (allocation.free, allocation.paid, allocation.auction) == (1, 0, 0)

    def test_ten_slots_split_without_loss(self) -> None:
        allocation = allocate_slots(10, 0.60, 0.25, 0.15)
        assert (allocation.free, allocation.paid, allocation.auction) == (6, 3, 1)
        assert allocation.total == 10

    def test_zero_and_negative_totals_are_safe(self) -> None:
        assert allocate_slots(0, 0.60, 0.25, 0.15).total == 0
        assert allocate_slots(-5, 0.60, 0.25, 0.15).total == 0

    def test_allocation_is_deterministic(self) -> None:
        """Ties break in documented tier order, so two runs never disagree."""
        assert allocate_slots(7, 0.60, 0.25, 0.15) == allocate_slots(7, 0.60, 0.25, 0.15)


# ---------------------------------------------------------------------------
# §24 property-based tests
# ---------------------------------------------------------------------------

@given(
    women=st.integers(min_value=0, max_value=5_000),
    admissions=st.lists(st.booleans(), min_size=0, max_size=300),
)
@settings(max_examples=300, deadline=None)
def test_no_admission_sequence_pushes_men_above_ceiling(women: int, admissions: list[bool]) -> None:
    """§24 property: "**no admission sequence may push active_men above ceiling**".

    Replays an arbitrary sequence of admission attempts through the real gate and asserts the
    FR-2.5 ceiling holds at every step. This is the fairness claim the product is sold on.
    """
    men = 0
    state = AdmissionState.OPEN

    for attempt in admissions:
        if not attempt:
            continue
        snapshot = RatioSnapshot(active_men=men, active_women=women)
        state = next_state(state, snapshot, UPPER, LOWER)
        if can_admit_man(state, snapshot, BUFFER):
            men += 1
        assert men <= ceiling(women, BUFFER), (
            f"ceiling breached: {men} men against {women} women (ceiling "
            f"{ceiling(women, BUFFER)})"
        )


@given(
    counts=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=2_000),
            st.integers(min_value=0, max_value=2_000),
        ),
        min_size=1,
        max_size=100,
    )
)
@settings(max_examples=200, deadline=None)
def test_state_machine_never_evicts(counts: list[tuple[int, int]]) -> None:
    """§24 property: the never-evict invariant (FR-2.6).

    However the ratio moves, the machine's only output is OPEN or FROZEN. A frozen region
    still holds every man it admitted — the count is never reduced by the state machine.
    """
    state = AdmissionState.OPEN
    for men, women in counts:
        state = next_state(state, RatioSnapshot(men, women), UPPER, LOWER)
        assert state in {AdmissionState.OPEN, AdmissionState.FROZEN}


@given(
    total=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=300, deadline=None)
def test_slot_allocation_conserves_every_slot(total: int) -> None:
    """§24 property: the three tiers partition the total exactly — no slot invented, none lost."""
    allocation = allocate_slots(total, 0.60, 0.25, 0.15)
    assert allocation.total == total
    assert allocation.free >= 0 and allocation.paid >= 0 and allocation.auction >= 0


@given(
    men=st.integers(min_value=0, max_value=10_000),
    women=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=300, deadline=None)
def test_frozen_state_always_blocks_admission(men: int, women: int) -> None:
    """A frozen region admits nobody, whatever the counts say."""
    assert can_admit_man(AdmissionState.FROZEN, RatioSnapshot(men, women), BUFFER) is False


class TestEngagementPriority:
    """FR-2.10: waitlist priority weighted by engagement quality, **not pure FIFO**."""

    def test_a_complete_profile_outranks_a_longer_wait(self) -> None:
        newcomer = engagement_priority(
            profile_completeness=1.0, days_waiting=1, prior_swipes=0, prior_matches=0
        )
        veteran = engagement_priority(
            profile_completeness=0.2, days_waiting=60, prior_swipes=0, prior_matches=0
        )
        assert newcomer > veteran, "FR-2.10 is explicitly not first-come-first-served"

    def test_waiting_still_counts(self) -> None:
        """Otherwise a queue would never drain for someone who joined early."""
        waited = engagement_priority(
            profile_completeness=0.5, days_waiting=30, prior_swipes=0, prior_matches=0
        )
        fresh = engagement_priority(
            profile_completeness=0.5, days_waiting=0, prior_swipes=0, prior_matches=0
        )
        assert waited > fresh

    def test_priority_stays_in_unit_range(self) -> None:
        maxed = engagement_priority(
            profile_completeness=1.0, days_waiting=9999, prior_swipes=9999, prior_matches=9999
        )
        assert 0.0 <= maxed <= 1.0

    def test_empty_profile_scores_zero_completeness(self) -> None:
        assert profile_completeness({}) == 0.0

    def test_full_profile_scores_one(self) -> None:
        assert profile_completeness(
            {
                "name": "Aditi",
                "dob": "1996-01-01",
                "bio": "hello",
                "photos": [{}, {}],
                "prompts": [{}],
                "tags": ["a", "b", "c"],
            }
        ) == 1.0


def test_launch_defaults_feed_the_state_machine(thresholds: Thresholds) -> None:
    """The bands used above must be the documented ones, not test-invented constants."""
    assert thresholds.ratio_upper_band == UPPER
    assert thresholds.ratio_lower_band == LOWER
    assert thresholds.admission_buffer == BUFFER
