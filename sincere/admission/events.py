"""Domain events for admission (§14).

Consumes: ``UserVerified``, ``ActiveStatusChanged``, ``PaymentSucceeded``, ``MessageSent``,
``UserBanned``, ``AccountDeletionRequested``.
Emits: ``UserActivated``, ``AuctionClosed`` (both from ``service.py``).

Every handler is idempotent — the outbox replays failures (§14 at-least-once).
"""

from __future__ import annotations

import logging

from sincere.admission import api as admission_api
from sincere.admission import repository as repo
from sincere.identity import api as identity
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.USER_VERIFIED)
async def on_user_verified(event: DomainEvent) -> None:
    """§14: identity -> admission. "Enter admission flow"."""
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    user = await identity.get_user_summary(user_id)
    if user is None or user["status"] in {"active", "banned"}:
        return  # idempotent: already decided

    outcome = await admission_api.admit_or_waitlist(user_id)
    logger.info("admission.verified_routed", extra={"user_id": user_id, "outcome": outcome})


@bus.on(Event.ACTIVE_STATUS_CHANGED)
async def on_active_status_changed(event: DomainEvent) -> None:
    """§14: shared activity tracker -> admission. "Recompute hex ratio -> hysteresis".

    A woman going inactive is the event that actually triggers the FR-2.4 freeze, so this is
    the load-bearing path for the whole ratio guarantee. Draining afterwards lets a *recovered*
    ratio immediately admit from the waitlist rather than waiting for the nightly sweep.
    """
    region = event.payload.get("region")
    if not region:
        return

    snapshot = await admission_api.recount_region(region)
    logger.info(
        "admission.ratio_recomputed",
        extra={
            "region": region,
            "active_men": snapshot.active_men,
            "active_women": snapshot.active_women,
        },
    )
    await admission_api.drain_waitlist(region)


@bus.on(Event.PAYMENT_SUCCEEDED)
async def on_payment_succeeded(event: DomainEvent) -> None:
    """§14: monetization -> admission. "Paid-queue placement".

    FR-2.7: the paid tier draws from the same ratio ceiling, so a successful payment promotes
    the user's tier and then tries to drain — it never bypasses FR-2.4.
    """
    if event.payload.get("purpose") != "queue_entry":
        return  # Pro subscriptions and auction charges are handled elsewhere

    user_id = event.payload.get("user_id")
    if not user_id:
        return

    user = await identity.get_user_summary(user_id)
    if user is None or not user["h3_region"]:
        return

    await admission_api.promote_to_paid_tier(user_id, user["h3_region"])
    await admission_api.drain_waitlist(user["h3_region"])


@bus.on(Event.MESSAGE_SENT)
async def on_message_sent(event: DomainEvent) -> None:
    """§14: chat -> admission, for churn-risk features.

    §14's note: "declining frequency + growing latency -> flag at-risk woman proactively".
    The heavy analysis is a daily scan (§15b); this handler only refreshes the activity
    timestamp that the scan reads, keeping the hot chat path cheap.
    """
    sender_id = event.payload.get("sender_id")
    if sender_id:
        await identity.record_swipe_activity(sender_id)


@bus.on(Event.USER_BANNED)
async def on_user_banned(event: DomainEvent) -> None:
    """§14: antiabuse -> admission. A banned user leaves every pool and queue.

    His ratio slot is released, which correctly makes room for someone else — FR-2.6's
    never-evict rule protects admitted men from *ratio dips*, not from their own conduct.
    """
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    user = await identity.get_user_summary(user_id)
    region = (user or {}).get("h3_region")
    if not region:
        return

    await admission_api.remove_from_queues(user_id, region)
    await admission_api.recount_region(region)
    await admission_api.drain_waitlist(region)


@bus.on(Event.ACCOUNT_DELETION_REQUESTED)
async def on_account_deletion_requested(event: DomainEvent) -> None:
    """§6: "immediate hide + removal from all pools/queues"."""
    user_id = event.payload.get("user_id")
    if not user_id:
        return

    user = await identity.get_user_summary(user_id)
    region = (user or {}).get("h3_region")
    await admission_api.remove_from_queues(user_id, region)

    if region:
        await admission_api.recount_region(region)
        await admission_api.drain_waitlist(region)
    logger.info("admission.removed_for_deletion", extra={"user_id": user_id})


@bus.on(Event.AUCTION_CLOSED)
async def on_auction_closed(event: DomainEvent) -> None:
    """§14: admission -> admission. Losing bidders return to the free queue.

    Without this a loser would sit in the auction tier forever, drawing from the 15% share he
    can no longer win from, and never advancing through the 60% free share.
    """
    region = event.payload.get("region")
    if not region:
        return

    for loser in event.payload.get("losers", []):
        await repo.promote_tier(region, loser["user_id"], "free")
