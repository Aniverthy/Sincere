"""Admission business logic (FR-2.1-2.11, §15a).

The single most important function here is :func:`admit_or_waitlist`. It is the only path by
which anyone becomes active, and it is where FR-2.4 (hysteresis), FR-2.5 (buffer) and FR-2.6
(never evict) meet.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sincere.admission import auction
from sincere.admission import repository as repo
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
from sincere.admission.schemas import (
    AuctionBidView,
    AuctionResultResponse,
    AuctionStatus,
    AuctionTodayResponse,
    QueueStatusResponse,
    QueueTier,
    RegionHealthResponse,
)
from sincere.identity import api as identity
from sincere.shared import cache
from sincere.shared.audit import AuditAction, record, record_admission_decision
from sincere.shared.errors import ConflictError, NotFoundError, ValidationError
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)


async def _splits() -> dict[str, float]:
    thresholds = await load_thresholds()
    return {
        "free": thresholds.queue_split_free,
        "paid": thresholds.queue_split_paid,
        "auction": thresholds.queue_split_auction,
    }


async def snapshot_for(region: str) -> tuple[RatioSnapshot, AdmissionState, dict[str, Any]]:
    """Current ratio and state for a hex, creating the queue document on first use."""
    queue = await repo.ensure_queue(region, await _splits())
    snapshot = RatioSnapshot(
        active_men=int(queue.get("active_men", 0)),
        active_women=int(queue.get("active_women", 0)),
    )
    state = AdmissionState(queue.get("admission_state", AdmissionState.OPEN))
    return snapshot, state, queue


# ---------------------------------------------------------------------------
# The admission decision (FR-2.4-2.6)
# ---------------------------------------------------------------------------

async def admit_or_waitlist(user_id: str) -> str:
    """Decide a verified user's fate. Returns ``"active"`` or ``"waitlisted"``.

    §6: **women are admitted immediately**; the ratio ceiling constrains men only. That
    asymmetry is the product, not an oversight — the whole admission system exists to keep
    the pool women-majority.
    """
    user = await identity.get_user_summary(user_id)
    if user is None:
        raise NotFoundError("Account")

    region = user["h3_region"]
    if not region:
        # No location yet, so no admission region. The client posts location on app open
        # (FR-3.3); until then the user waits rather than being assigned to an arbitrary hex.
        logger.info("admission.deferred_no_region", extra={"user_id": user_id})
        await identity.mark_waitlisted(user_id)
        return "waitlisted"

    thresholds = await load_thresholds()
    snapshot, state, _ = await snapshot_for(region)

    if user["gender"] == "female":
        await identity.mark_active(user_id)
        await repo.adjust_count(region, gender="female", delta=1)
        await _refresh_state(region)
        await record_admission_decision(
            user_id=user_id,
            region=region,
            granted=True,
            tier=None,
            active_men=snapshot.active_men,
            active_women=snapshot.active_women,
            ceiling=ceiling(snapshot.active_women, thresholds.admission_buffer),
            admission_state=str(state),
        )
        await bus.emit(Event.USER_ACTIVATED, {"user_id": user_id, "region": region})
        return "active"

    # Men pass through the FR-2.4/2.5 gate.
    state = next_state(state, snapshot, thresholds.ratio_upper_band, thresholds.ratio_lower_band)
    await repo.set_admission_state(region, state)

    if can_admit_man(state, snapshot, thresholds.admission_buffer):
        await _activate_man(user_id, region, QueueTier.FREE, snapshot, state, thresholds)
        return "active"

    await _waitlist(user_id, region, QueueTier.FREE)
    await record_admission_decision(
        user_id=user_id,
        region=region,
        granted=False,
        tier=str(QueueTier.FREE),
        active_men=snapshot.active_men,
        active_women=snapshot.active_women,
        ceiling=ceiling(snapshot.active_women, thresholds.admission_buffer),
        admission_state=str(state),
    )
    return "waitlisted"


async def _activate_man(
    user_id: str,
    region: str,
    tier: QueueTier,
    snapshot: RatioSnapshot,
    state: AdmissionState,
    thresholds: Any,
) -> None:
    await identity.mark_active(user_id)
    await identity.set_entry_tier(user_id, identity.EntryTier(str(tier)))
    await repo.adjust_count(region, gender="male", delta=1)
    await repo.remove_from_waitlist(region, user_id)
    await cache.invalidate(cache.Keys.region_ratio(region))

    await record_admission_decision(
        user_id=user_id,
        region=region,
        granted=True,
        tier=str(tier),
        active_men=snapshot.active_men,
        active_women=snapshot.active_women,
        ceiling=ceiling(snapshot.active_women, thresholds.admission_buffer),
        admission_state=str(state),
    )
    await _refresh_state(region)
    await bus.emit(Event.USER_ACTIVATED, {"user_id": user_id, "region": region, "tier": str(tier)})


async def _waitlist(user_id: str, region: str, tier: QueueTier) -> None:
    priority = await _priority_for(user_id)
    await identity.mark_waitlisted(user_id)
    await repo.add_to_waitlist(
        region, user_id=user_id, tier=str(tier), engagement_priority=priority
    )


async def _priority_for(user_id: str) -> float:
    """FR-2.10 engagement-weighted priority."""
    card = await identity.get_profile_card(user_id)
    summary = await identity.get_user_summary(user_id)
    if card is None or summary is None:
        return 0.0

    created = summary.get("created_at") or datetime.now(UTC)
    days_waiting = max(0, (datetime.now(UTC) - created).days)
    return engagement_priority(
        profile_completeness=profile_completeness(
            {
                "name": card.get("name"),
                "dob": card.get("age"),
                "bio": card.get("bio"),
                "photos": card.get("photos"),
                "prompts": card.get("prompts"),
                "tags": card.get("tags"),
            }
        ),
        days_waiting=days_waiting,
        prior_swipes=0,
        prior_matches=0,
    )


async def _refresh_state(region: str) -> AdmissionState:
    """Re-evaluate the hysteresis state after a count change (§14 ActiveStatusChanged)."""
    thresholds = await load_thresholds()
    snapshot, current, _ = await snapshot_for(region)
    updated = next_state(
        current, snapshot, thresholds.ratio_upper_band, thresholds.ratio_lower_band
    )
    if updated is not current:
        await repo.set_admission_state(region, updated)
        await record(
            AuditAction.ADMISSION_FROZEN
            if updated is AdmissionState.FROZEN
            else AuditAction.ADMISSION_RESUMED,
            region=region,
            context={
                "active_men": snapshot.active_men,
                "active_women": snapshot.active_women,
                "ratio": snapshot.ratio if snapshot.active_women else None,
            },
        )
        logger.info(
            "admission.state_changed",
            extra={"region": region, "from": str(current), "to": str(updated)},
        )
    await cache.invalidate(cache.Keys.region_ratio(region))
    return updated


# ---------------------------------------------------------------------------
# Draining the waitlist (FR-2.7)
# ---------------------------------------------------------------------------

async def drain_waitlist(region: str) -> dict[str, int]:
    """Admit as many waitlisted men as the ceiling allows, respecting the 60/25/15 split.

    Ordering within each tier is FR-2.10's engagement priority, not arrival time. Idempotent:
    re-running simply finds fewer available slots.
    """
    thresholds = await load_thresholds()
    snapshot, state, queue = await snapshot_for(region)

    state = next_state(state, snapshot, thresholds.ratio_upper_band, thresholds.ratio_lower_band)
    await repo.set_admission_state(region, state)
    if state is AdmissionState.FROZEN:
        return {"admitted": 0, "reason_frozen": 1}

    headroom = available_slots(snapshot, thresholds.admission_buffer)
    if headroom <= 0:
        return {"admitted": 0}

    allocation = allocate_slots(
        headroom,
        thresholds.queue_split_free,
        thresholds.queue_split_paid,
        thresholds.queue_split_auction,
    )
    waitlist = queue.get("waitlist", [])
    admitted = 0
    counts = {"free": allocation.free, "paid": allocation.paid, "auction": allocation.auction}

    for tier, quota in counts.items():
        candidates = [entry for entry in waitlist if entry.get("tier") == tier]
        # FR-2.10: engagement priority first; arrival time only breaks ties.
        candidates.sort(
            key=lambda entry: (-entry.get("engagement_priority", 0.0), entry.get("joined_at"))
        )
        for entry in candidates[:quota]:
            current, current_state, _ = await snapshot_for(region)
            if not can_admit_man(current_state, current, thresholds.admission_buffer):
                break  # the ceiling moved under us; FR-2.5 wins over the quota
            await _activate_man(
                entry["user_id"], region, QueueTier(tier), current, current_state, thresholds
            )
            admitted += 1

    logger.info("admission.waitlist_drained", extra={"region": region, "admitted": admitted})
    return {"admitted": admitted}


# ---------------------------------------------------------------------------
# Queue status (§7)
# ---------------------------------------------------------------------------

async def queue_status(user_id: str) -> QueueStatusResponse:
    user = await identity.get_user_summary(user_id)
    if user is None or not user["h3_region"]:
        raise NotFoundError("Region", "Open the app with location enabled to join a queue.")

    region = user["h3_region"]
    thresholds = await load_thresholds()
    snapshot, state, queue = await snapshot_for(region)

    waitlist = queue.get("waitlist", [])
    ordered = sorted(
        waitlist, key=lambda e: (-e.get("engagement_priority", 0.0), e.get("joined_at"))
    )
    position = next(
        (i for i, entry in enumerate(ordered, start=1) if entry["user_id"] == user_id), None
    )
    entry = next((e for e in waitlist if e["user_id"] == user_id), None)
    headroom = available_slots(snapshot, thresholds.admission_buffer)

    return QueueStatusResponse(
        region=region,
        admission_state=state,
        tier=QueueTier(entry["tier"]) if entry else None,
        position=position,
        waitlist_size=len(waitlist),
        slots_available=headroom,
        active_men=snapshot.active_men,
        active_women=snapshot.active_women,
        estimated_days=_estimate_days(position, headroom),
        paid_entry_affects_ranking=False,  # FR-2.11
        message=_queue_message(state, position),
    )


def _estimate_days(position: int | None, daily_slots: int) -> float | None:
    if position is None or daily_slots <= 0:
        return None
    return round(position / daily_slots, 1)


def _queue_message(state: AdmissionState, position: int | None) -> str:
    if position is None:
        return "You are admitted."
    if state is AdmissionState.FROZEN:
        return (
            "Admissions in your area are paused while the community rebalances. "
            "Nobody is removed when this happens — you keep your place."
        )
    return "You are on the list. Places open daily."


# ---------------------------------------------------------------------------
# Auction (FR-2.9)
# ---------------------------------------------------------------------------

async def _today_window(thresholds: Any) -> tuple[datetime, datetime]:
    return auction.window_for(
        datetime.now(UTC).date(),
        thresholds.auction_window_start_hour,
        thresholds.auction_window_end_hour,
    )


async def _auction_slots(region: str, thresholds: Any) -> int:
    snapshot, _, _ = await snapshot_for(region)
    headroom = available_slots(snapshot, thresholds.admission_buffer)
    return allocate_slots(
        headroom,
        thresholds.queue_split_free,
        thresholds.queue_split_paid,
        thresholds.queue_split_auction,
    ).auction


async def auction_today(user_id: str) -> AuctionTodayResponse:
    user = await identity.get_user_summary(user_id)
    if user is None or not user["h3_region"]:
        raise NotFoundError("Region")
    region = user["h3_region"]

    thresholds = await load_thresholds()
    start, end = await _today_window(thresholds)
    slots = await _auction_slots(region, thresholds)
    await repo.upsert_auction(
        region=region,
        window_start=start,
        window_end=end,
        slots=slots,
        min_bid=thresholds.auction_min_bid_paise,
    )

    book = await auction.read_book(region, end)
    requirement = await auction.standing_requirement(
        region, end, slots, thresholds.auction_min_bid_paise
    )
    your_amount, your_rank = await auction.user_position(region, end, user_id)

    now = datetime.now(UTC)
    status = (
        AuctionStatus.OPEN
        if auction.is_open(now, start, end)
        else (AuctionStatus.SCHEDULED if now < start else AuctionStatus.SETTLING)
    )

    return AuctionTodayResponse(
        region=region,
        status=status,
        window_start=start,
        window_end=end,
        slots=slots,
        min_bid_paise=thresholds.auction_min_bid_paise,
        standing_requirement_paise=requirement,
        # §7: anonymized. Rank and amount only — never a user id.
        top_bids=[
            AuctionBidView(
                rank=index,
                amount_paise=bid.amount_paise,
                is_you=bid.user_id == user_id,
            )
            for index, bid in enumerate(book[: max(slots, 5)], start=1)
        ],
        your_bid_paise=your_amount,
        your_rank=your_rank,
    )


async def place_bid(user_id: str, amount_paise: int) -> AuctionTodayResponse:
    """``POST /auction/bid`` — ascending only, inside the window."""
    user = await identity.get_user_summary(user_id)
    if user is None or not user["h3_region"]:
        raise NotFoundError("Region")
    if user["status"] not in {"waitlisted"}:
        raise ConflictError(
            "Not eligible to bid",
            "The auction is for people waiting to join. You are already admitted.",
        )

    region = user["h3_region"]
    thresholds = await load_thresholds()
    start, end = await _today_window(thresholds)

    if not auction.is_open(datetime.now(UTC), start, end):
        raise ValidationError(
            f"Bidding is open between {start:%H:%M} and {end:%H:%M} each day."
        )

    slots = await _auction_slots(region, thresholds)
    if slots <= 0:
        raise ConflictError(
            "No places today",
            "There are no auction places in your area today. Try again tomorrow.",
        )

    await auction.place_bid(
        region=region,
        window_end=end,
        user_id=user_id,
        amount_paise=amount_paise,
        min_bid_paise=thresholds.auction_min_bid_paise,
    )
    return await auction_today(user_id)


async def close_auction(region: str, window_end: datetime) -> dict[str, Any]:
    """Settle one region's auction (§15a). Idempotent — see :func:`repository.settle_auction`.

    §21 pages on failure here: an unsettled auction means charged bidders who were never
    admitted, which is a money problem, not just a bug.
    """
    stored = await repo.get_auction(region, window_end)
    if stored is None or stored.get("status") == "settled":
        return {"region": region, "already_settled": True}

    book = await auction.read_book(region, window_end)
    settlement = auction.settle(book, int(stored.get("slots", 0)))

    await repo.settle_auction(
        region=region,
        window_end=window_end,
        winners=[
            {"user_id": b.user_id, "amount_paise": b.amount_paise, "at": b.placed_at}
            for b in settlement.winners
        ],
        clearing_bid=settlement.clearing_bid_paise,
        losers=[
            {"user_id": b.user_id, "amount_paise": b.amount_paise, "at": b.placed_at}
            for b in settlement.losers
        ],
    )

    # monetization charges winners and refunds losers; admission admits the winners (§14).
    await bus.emit(
        Event.AUCTION_CLOSED,
        {
            "region": region,
            "window_end": window_end.isoformat(),
            "winners": [
                {"user_id": b.user_id, "amount_paise": b.amount_paise} for b in settlement.winners
            ],
            "losers": [
                {"user_id": b.user_id, "amount_paise": b.amount_paise} for b in settlement.losers
            ],
            "clearing_bid_paise": settlement.clearing_bid_paise,
        },
    )

    thresholds = await load_thresholds()
    for bid in settlement.winners:
        snapshot, state, _ = await snapshot_for(region)
        if can_admit_man(state, snapshot, thresholds.admission_buffer):
            await _activate_man(
                bid.user_id, region, QueueTier.AUCTION, snapshot, state, thresholds
            )

    await record(
        AuditAction.AUCTION_SETTLED,
        region=region,
        context={
            "winners": len(settlement.winners),
            "losers": len(settlement.losers),
            "clearing_bid_paise": settlement.clearing_bid_paise,
            "slots": stored.get("slots"),
        },
    )
    await auction.clear_book(region, window_end)
    return {
        "region": region,
        "winners": len(settlement.winners),
        "losers": len(settlement.losers),
        "clearing_bid_paise": settlement.clearing_bid_paise,
    }


async def auction_result(user_id: str) -> AuctionResultResponse:
    user = await identity.get_user_summary(user_id)
    if user is None or not user["h3_region"]:
        raise NotFoundError("Region")
    region = user["h3_region"]

    settled = await repo.latest_settled_auction(region)
    if settled is None:
        return AuctionResultResponse(
            region=region, slots=0, message="No auction has been settled in your area yet."
        )

    winner = next((w for w in settled.get("winners", []) if w["user_id"] == user_id), None)
    loser = next(
        (lo for lo in settled.get("losers", []) if lo["user_id"] == user_id), None
    )

    if winner:
        message = "You won a place. Welcome in."
    elif loser:
        message = "You did not win this time. Your bid has been refunded in full."
    else:
        message = "You did not bid in this auction."

    return AuctionResultResponse(
        region=region,
        settled_at=settled.get("settled_at"),
        slots=int(settled.get("slots", 0)),
        you_won=winner is not None,
        your_bid_paise=(winner or loser or {}).get("amount_paise"),
        clearing_bid_paise=settled.get("clearing_bid_paise"),
        refund_status="refunded" if loser else None,
        message=message,
    )


# ---------------------------------------------------------------------------
# Ratio recount (§19 drift correction) and admin views (FR-8.1)
# ---------------------------------------------------------------------------

async def recount_region(region: str) -> RatioSnapshot:
    """Authoritative recount from ``users`` (§19: "hourly full recount as drift correction")."""
    men = await identity.count_by_region_and_gender(region, identity.Gender.MALE, active_only=True)
    women = await identity.count_by_region_and_gender(
        region, identity.Gender.FEMALE, active_only=True
    )
    await repo.set_counts(region, active_men=men, active_women=women)
    await _refresh_state(region)
    return RatioSnapshot(active_men=men, active_women=women)


async def region_health(region: str) -> RegionHealthResponse:
    thresholds = await load_thresholds()
    snapshot, state, queue = await snapshot_for(region)
    waitlist = queue.get("waitlist", [])

    by_tier: dict[str, int] = {}
    for entry in waitlist:
        by_tier[entry.get("tier", "free")] = by_tier.get(entry.get("tier", "free"), 0) + 1

    return RegionHealthResponse(
        region=region,
        admission_state=state,
        active_men=snapshot.active_men,
        active_women=snapshot.active_women,
        ratio=snapshot.ratio if snapshot.active_women else None,
        ceiling=ceiling(snapshot.active_women, thresholds.admission_buffer),
        slots_available=available_slots(snapshot, thresholds.admission_buffer),
        waitlist_size=len(waitlist),
        waitlist_by_tier=by_tier,
        frozen_since=queue.get("frozen_since"),
    )
