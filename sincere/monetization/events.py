"""Domain events for monetization (§14).

Consumes: ``PaymentSucceeded`` (own emission — subscription activation), ``AuctionClosed``.
Emits: ``PaymentSucceeded`` (from ``service.py``).
"""

from __future__ import annotations

import logging

from sincere.monetization import api as monetization_api
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.PAYMENT_SUCCEEDED)
async def on_payment_succeeded(event: DomainEvent) -> None:
    """Activate a Pro subscription once its payment settles.

    Admission handles the ``queue_entry`` purpose in its own handler; this one deliberately
    ignores that purpose rather than duplicating the placement logic (§3 rule 3).
    """
    if event.payload.get("purpose") != "subscription":
        return

    user_id = event.payload.get("user_id")
    tier = (event.payload.get("metadata") or {}).get("tier")
    if not user_id or not tier:
        return

    await monetization_api.activate_subscription(user_id, tier)


@bus.on(Event.AUCTION_CLOSED)
async def on_auction_closed(event: DomainEvent) -> None:
    """§14: admission -> monetization. "**Charge winners, refund losers**".

    Both halves matter and both are idempotent. §21 pages on auction settlement failure
    because a winner who was admitted but never charged, or a loser charged but never
    refunded, is a money incident.
    """
    region = event.payload.get("region")
    winners = event.payload.get("winners") or []
    losers = event.payload.get("losers") or []

    charged = 0
    for winner in winners:
        try:
            await monetization_api.charge_auction_winner(
                winner["user_id"], int(winner["amount_paise"]), region or ""
            )
            charged += 1
        except Exception:
            # One failed charge must not block the remaining winners or the refunds — a
            # loser left un-refunded is the worse outcome.
            logger.exception("auction.charge_failed", extra={"user_id": winner.get("user_id")})

    # Losers never had money captured — the bid is a commitment, and the charge happens only
    # at settlement for winners. Logged for the audit trail (§22 auction settlements).
    logger.info(
        "auction.settlement_processed",
        extra={"region": region, "charged": charged, "released": len(losers)},
    )
