"""Domain events for feedback_ml (§14).

Consumes: ``MessageSent`` (We-Met trigger check), ``Unmatched`` (stop asking).
Emits: ``WeMetThresholdReached`` (from ``service.py``).
"""

from __future__ import annotations

import logging

from sincere.feedback_ml import api as feedback_api
from sincere.feedback_ml import repository as repo
from sincere.shared.events import DomainEvent, Event, bus

logger = logging.getLogger(__name__)


@bus.on(Event.MESSAGE_SENT)
async def on_message_sent(event: DomainEvent) -> None:
    """§14: chat -> feedback_ml. "We-Met trigger check (20-30 in 3-day window?)".

    Cheap short-circuit first: the trigger cannot fire below the message threshold, so most
    messages cost one integer comparison rather than a window query. Chat is the hottest write
    path in the product (§19).
    """
    match_id = event.payload.get("match_id")
    if not match_id:
        return

    from sincere.shared.threshold_store import load as load_thresholds

    thresholds = await load_thresholds()
    if int(event.payload.get("msg_count", 0)) < thresholds.wemet_trigger_messages:
        return

    if await feedback_api.check_trigger(match_id):
        await feedback_api.fire_prompt(match_id)


@bus.on(Event.UNMATCHED)
async def on_unmatched(event: DomainEvent) -> None:
    """FR-4.3: re-ask "until met **or unmatched**".

    Clearing the schedule here is what honours the "or unmatched" clause — otherwise the
    scheduler would keep asking two people about a match one of them has ended.
    """
    match_id = event.payload.get("match_id")
    if not match_id:
        return

    await repo.set_prompt_state(match_id, triggered_at=None, next_reask_at=None)
    logger.info("wemet.cancelled_on_unmatch", extra={"match_id": match_id})
