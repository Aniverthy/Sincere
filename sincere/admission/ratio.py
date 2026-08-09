"""Ratio tracking, hysteresis state machine, and slot allocation (FR-2.3-2.7).

Pure functions — no I/O, no database. This is the load-bearing fairness logic of the whole
product, so it is kept side-effect free and exhaustively testable (§24 puts it under both
"Unit" and "Property-based").

The three rules this file implements, all **(DECIDED)**:

* **FR-2.4 hysteresis.** Freeze male admissions when ``active_men > active_women * 1.05``;
  resume only once the ratio recovers below ``* 0.95``. The gap between the two thresholds is
  the entire point — a single threshold would flap on every admission.
* **FR-2.6 never evict.** A ratio dip freezes *new* admissions. It never removes an admitted
  man. The state machine has no transition that can.
* **FR-2.7 slot split.** 60% free / 25% paid / 15% auction, all drawn from one ratio ceiling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class AdmissionState(StrEnum):
    """§8 ``queues.admission_state``."""

    OPEN = "open"
    FROZEN = "frozen"


@dataclass(frozen=True, slots=True)
class RatioSnapshot:
    """Ratio inputs at a decision point.

    §22 requires admission decisions to be audited "with the ratio inputs at decision time",
    so this is the value that gets recorded alongside every decision.
    """

    active_men: int
    active_women: int

    @property
    def ratio(self) -> float:
        """Men per woman. Infinite when there are men but no women — which correctly reads
        as "maximally over-admitted" rather than as a divide-by-zero error."""
        if self.active_women == 0:
            return float("inf") if self.active_men > 0 else 0.0
        return self.active_men / self.active_women


@dataclass(frozen=True, slots=True)
class SlotAllocation:
    """FR-2.7's three tiers for one admission cycle."""

    free: int
    paid: int
    auction: int

    @property
    def total(self) -> int:
        return self.free + self.paid + self.auction


def ceiling(active_women: int, buffer: float) -> int:
    """FR-2.5: the maximum admitted men for the current active-women count.

    "Admit men up to ~90-95% of active-women count" — the buffer keeps the pool slightly
    women-majority, which is the product's core promise. Floored, not rounded: rounding up
    would let the ceiling exceed the buffer it exists to enforce.
    """
    return int(active_women * buffer)


def next_state(
    current: AdmissionState, snapshot: RatioSnapshot, upper_band: float, lower_band: float
) -> AdmissionState:
    """The FR-2.4 hysteresis transition.

    Deliberately asymmetric:

    * ``OPEN -> FROZEN`` when the ratio exceeds ``upper_band`` (1.05).
    * ``FROZEN -> OPEN`` only when it falls below ``lower_band`` (0.95).

    Between the bands, **the state does not change**. That dead zone is what stops the
    oscillation a single threshold would produce: freeze, admit nobody, ratio drifts down a
    hair, unfreeze, admit one, freeze again.
    """
    ratio = snapshot.ratio

    if current is AdmissionState.OPEN:
        return AdmissionState.FROZEN if ratio > upper_band else AdmissionState.OPEN

    return AdmissionState.OPEN if ratio < lower_band else AdmissionState.FROZEN


def can_admit_man(
    state: AdmissionState, snapshot: RatioSnapshot, buffer: float
) -> bool:
    """Whether one more man may be admitted right now (FR-2.4, FR-2.5).

    Two independent gates, both of which must pass:
      1. the hysteresis state must be OPEN, and
      2. admitting him must not push the count past the FR-2.5 buffer ceiling.

    The second gate is what §24's property test asserts can never be violated by *any*
    admission sequence.
    """
    if state is AdmissionState.FROZEN:
        return False
    return snapshot.active_men + 1 <= ceiling(snapshot.active_women, buffer)


def available_slots(snapshot: RatioSnapshot, buffer: float) -> int:
    """How many men the ceiling still has room for. Never negative.

    A negative headroom is possible in reality — women can go inactive (FR-2.3) and push the
    count above the ceiling. FR-2.6 forbids evicting anyone to fix that, so the correct
    response is zero new admissions until the ratio recovers, not a negative slot count.
    """
    return max(0, ceiling(snapshot.active_women, buffer) - snapshot.active_men)


def allocate_slots(
    total: int, free_share: float, paid_share: float, auction_share: float
) -> SlotAllocation:
    """Split ``total`` daily slots across FR-2.7's three tiers.

    Uses **largest-remainder** apportionment rather than naive rounding, for a reason that
    only shows up at the small slot counts a single-city launch actually produces: with
    ``total=10``, naive ``int()`` truncation yields 6/2/1 = 9 and silently drops a slot,
    while naive ``round()`` can yield 6/3/2 = 11 and overshoot the ratio ceiling. Overshooting
    is an FR-2.4 violation; dropping is lost revenue and a longer queue.

    Largest-remainder guarantees the parts sum to exactly ``total`` while staying as close as
    possible to the intended shares. §24 calls out "slot allocation rounding (60/25/15 over
    small daily slot counts)" as a unit-test target for precisely this reason.
    """
    if total <= 0:
        return SlotAllocation(free=0, paid=0, auction=0)

    exact = {
        "free": total * free_share,
        "paid": total * paid_share,
        "auction": total * auction_share,
    }
    floors = {tier: int(value) for tier, value in exact.items()}
    remainder = total - sum(floors.values())

    # Hand the leftover slots to the largest fractional parts. Ties break in the documented
    # tier order (free, paid, auction) so the outcome is deterministic and reviewable.
    order = ["free", "paid", "auction"]
    by_fraction = sorted(order, key=lambda tier: (-(exact[tier] - floors[tier]), order.index(tier)))
    for tier in by_fraction[:remainder]:
        floors[tier] += 1

    return SlotAllocation(free=floors["free"], paid=floors["paid"], auction=floors["auction"])


def engagement_priority(
    *,
    profile_completeness: float,
    days_waiting: int,
    prior_swipes: int,
    prior_matches: int,
) -> float:
    """FR-2.10: free-queue priority weighted by **engagement quality, not pure FIFO**.

    Wait time still counts — a queue that ignored it would never drain for a new joiner — but
    it is one input among several rather than the only one. Returns a 0-1 score; higher goes
    first.

    Completeness dominates because it is the signal available before a man has ever used the
    product, which is the situation of everyone in the free queue.
    """
    completeness = max(0.0, min(1.0, profile_completeness))
    # Saturating: 30 days waiting and 60 both mean "has waited a long time".
    patience = days_waiting / (days_waiting + 14.0) if days_waiting > 0 else 0.0
    engagement = min(1.0, (prior_swipes / 50.0) * 0.5 + (prior_matches / 5.0) * 0.5)

    return round(0.50 * completeness + 0.30 * patience + 0.20 * engagement, 6)


def profile_completeness(profile: dict) -> float:
    """Fraction of the profile a user has actually filled in. Feeds FR-2.10 priority."""
    checks = (
        bool(profile.get("name")),
        bool(profile.get("dob")),
        bool(profile.get("bio")),
        len(profile.get("photos") or []) >= 2,
        len(profile.get("prompts") or []) >= 1,
        len(profile.get("tags") or []) >= 3,
    )
    return sum(checks) / len(checks)
