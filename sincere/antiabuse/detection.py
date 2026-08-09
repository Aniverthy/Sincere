"""Dwell-time abuse detection (FR-5.1-5.3). Pure functions.

FR-5.2 (DECIDED launch defaults): flag **<10 s dwell on >70% of right-swipes** over a rolling
window.

FR-5.3 (DECIDED): **3 in-app warnings on separate occasions, then ban** — a dedicated
warning/ban track, separate from identity's bot-risk routing.

§11 states the principle behind keeping this out of scoring: "low-intent swiping is a
**conduct problem, not a ranking penalty**". Nothing here feeds §12.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DwellVerdict:
    """Outcome of evaluating one user's rolling swipe window."""

    tripped: bool
    right_swipes: int
    fast_right_swipes: int
    ratio: float
    evaluated: bool
    """False when there were too few swipes to establish a pattern."""

    reason: str = ""


def effective_dwell(claimed_ms: int, server_ms: int | None) -> int:
    """Reconcile the client's dwell claim with the server's own timing (§18).

    §18: "client-reported ``dwell_ms`` is cross-checked server-side (profile-payload fetch
    time vs. swipe time) since **the client is untrusted**."

    The server figure is an upper bound on how long the profile could have been visible, so a
    claim exceeding it is a lie and gets clamped. A claim *below* it is plausible — the user
    may have left the app open — so it is taken at face value. Taking the minimum implements
    both cases in one expression.
    """
    if server_ms is None:
        return max(0, claimed_ms)
    return max(0, min(claimed_ms, server_ms))


def evaluate_window(
    swipes: list[dict[str, Any]],
    *,
    dwell_threshold_ms: int,
    dwell_ratio: float,
    min_swipes: int,
) -> DwellVerdict:
    """Apply the FR-5.2 rule to a rolling window of swipes.

    The denominator is **right-swipes only**, not all swipes. That is what FR-5.2 says, and it
    matters: fast left-swipes are how a discerning person uses the product, while fast
    right-swipes are indiscriminate liking. Counting both would punish exactly the behaviour
    the product wants.
    """
    right_swipes = [s for s in swipes if s.get("direction") == "right"]

    if len(right_swipes) < min_swipes:
        return DwellVerdict(
            tripped=False,
            right_swipes=len(right_swipes),
            fast_right_swipes=0,
            ratio=0.0,
            evaluated=False,
            reason=f"needs at least {min_swipes} right-swipes to evaluate a pattern",
        )

    fast = sum(
        1
        for s in right_swipes
        if effective_dwell(int(s.get("dwell_ms", 0)), s.get("server_dwell_ms"))
        < dwell_threshold_ms
    )
    ratio = fast / len(right_swipes)
    tripped = ratio > dwell_ratio

    return DwellVerdict(
        tripped=tripped,
        right_swipes=len(right_swipes),
        fast_right_swipes=fast,
        ratio=round(ratio, 4),
        evaluated=True,
        reason=(
            f"{fast} of {len(right_swipes)} right-swipes were under "
            f"{dwell_threshold_ms / 1000:.0f}s ({ratio:.0%})"
            if tripped
            else ""
        ),
    )


def is_separate_occasion(
    last_warning_at: datetime | None, now: datetime, occasion_window_hours: int
) -> bool:
    """FR-5.3: warnings must be on **separate occasions**.

    Without this, one bad session would issue three warnings in as many minutes and ban a user
    who never had the chance to change their behaviour. The window is what makes the escalation
    a genuine three-strikes process rather than a single-session trap.
    """
    if last_warning_at is None:
        return True
    return now - last_warning_at >= timedelta(hours=occasion_window_hours)


def next_action(
    warning_count: int, warnings_before_ban: int
) -> str:
    """What the next escalation step is: ``"warn"`` or ``"ban"`` (FR-5.3)."""
    return "ban" if warning_count + 1 >= warnings_before_ban else "warn"


def warning_message(occasion_no: int, warnings_before_ban: int) -> str:
    """Copy for the FR-5.3 interstitials. §4 renders these distinctly from a ban notice.

    Deliberately explains the behaviour rather than accusing: most people tripping this are
    swiping carelessly, not maliciously, and the goal is to change the habit.
    """
    remaining = warnings_before_ban - occasion_no
    if remaining <= 0:
        return (
            "Your account has been suspended for repeatedly liking profiles without reading "
            "them. This makes matches meaningless for everyone."
        )
    return (
        f"You are liking profiles faster than they can be read. Sincère is built on people "
        f"actually considering each other — please slow down. "
        f"({occasion_no} of {warnings_before_ban}; "
        f"{remaining} more and your account will be suspended.)"
    )
