"""Domain event bus — cross-cutting plumbing only, no business logic.

Implements TECHNICAL_IMPLEMENTATION_PLAN.md §14: an **in-process bus at MVP**, broker-backed
later. Cross-module *reactions* travel through here rather than through direct calls (§3 rule 3),
which is what keeps the microservice extraction cheap.

Delivery semantics: at-least-once via an outbox. ``emit()`` writes the event to the ``outbox``
collection in the same request as the state change, then dispatches to in-process handlers.
If dispatch fails or the process dies, the outbox sweeper re-dispatches. Handlers must
therefore be **idempotent** — the same requirement §15 places on scheduled jobs.

Handler failures never propagate to the emitter. A module that reacts to another module's
event must not be able to fail that module's write; that coupling is exactly what the event
boundary exists to prevent.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Event(StrEnum):
    """The domain events of §14. Emitter and consumers are noted per event."""

    USER_VERIFIED = "UserVerified"
    """identity -> admission. Enter admission flow (women and buffer-space men activate,
    everyone else waitlists)."""

    USER_ACTIVATED = "UserActivated"
    """admission -> matching. Include in next scoring batch; start freshness boost."""

    ACTIVE_STATUS_CHANGED = "ActiveStatusChanged"
    """shared activity tracker -> admission. Recompute hex ratio -> hysteresis state machine."""

    SWIPE_RECORDED = "SwipeRecorded"
    """matching -> antiabuse, matching. Dwell-rule evaluation; graduation counters."""

    MATCH_FORMED = "MatchFormed"
    """matching -> chat. Open conversation."""

    MESSAGE_SENT = "MessageSent"
    """chat -> matching, feedback_ml, admission. Engagement aggregates; We-Met trigger;
    churn-signal input. The three-way ripple diagrammed at §14."""

    WEMET_THRESHOLD_REACHED = "WeMetThresholdReached"
    """feedback_ml -> feedback_ml. Schedule prompt (20-30 msgs / 3 days)."""

    UNMATCHED = "Unmatched"
    """matching -> chat. Start the 90-day message-retention clock."""

    HARASSMENT_REPORTED = "HarassmentReported"
    """chat -> chat, admin. Retention hold; surface to review."""

    PAYMENT_SUCCEEDED = "PaymentSucceeded"
    """monetization -> admission. Paid-queue placement / bid validity / Pro activation."""

    AUCTION_CLOSED = "AuctionClosed"
    """admission -> monetization, admission. Charge winners, refund losers, admit winners."""

    WARNING_ISSUED = "WarningIssued"
    """antiabuse -> identity, admission. Ledger update."""

    USER_BANNED = "UserBanned"
    """antiabuse -> identity, admission. Removes from pools; embedding is RETAINED (§6) so a
    re-signup is caught by the duplicate check."""

    ACCOUNT_DELETION_REQUESTED = "AccountDeletionRequested"
    """identity -> all modules. Immediate hide + pool/queue removal; schedule 30-day cascade."""


@dataclass(slots=True)
class DomainEvent:
    """An emitted event plus the metadata the outbox and audit trail need."""

    name: Event
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.event_id,
            "event_name": str(self.name),
            "payload": self.payload,
            "occurred_at": self.occurred_at,
            "correlation_id": self.correlation_id,
            "status": "pending",
            "attempts": 0,
            "created_at": self.occurred_at,
        }


Handler = Callable[[DomainEvent], Awaitable[None] | None]


class EventBus:
    """In-process publish/subscribe with an outbox for at-least-once delivery."""

    def __init__(self) -> None:
        self._handlers: dict[Event, list[Handler]] = defaultdict(list)

    def subscribe(self, event: Event, handler: Handler) -> None:
        self._handlers[event].append(handler)
        logger.debug(
            "event.subscribed",
            extra={"event": str(event), "handler": getattr(handler, "__qualname__", "?")},
        )

    def on(self, event: Event) -> Callable[[Handler], Handler]:
        """Decorator form. Used by each module's ``events.py`` at import time."""

        def decorator(handler: Handler) -> Handler:
            self.subscribe(event, handler)
            return handler

        return decorator

    def handlers_for(self, event: Event) -> list[Handler]:
        return list(self._handlers[event])

    async def emit(
        self,
        name: Event,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
        persist: bool = True,
    ) -> DomainEvent:
        """Record and dispatch an event.

        The outbox write happens *before* dispatch so a crash mid-dispatch leaves a
        replayable record. Handler exceptions are logged and swallowed — see module docstring.
        """
        event = DomainEvent(name=name, payload=payload, correlation_id=correlation_id)

        if persist:
            try:
                from sincere.shared.db import C, collection

                await collection(C.OUTBOX).insert_one(event.to_document())
            except Exception:
                logger.exception("outbox.write_failed", extra={"event": str(name)})

        await self._dispatch(event)
        return event

    async def _dispatch(self, event: DomainEvent) -> None:
        handlers = self._handlers[event.name]
        if not handlers:
            logger.debug("event.no_handlers", extra={"event": str(event.name)})
            await self._mark(event, "processed")
            return

        results = await asyncio.gather(
            *(self._run(handler, event) for handler in handlers), return_exceptions=True
        )
        failed = [r for r in results if isinstance(r, Exception)]
        await self._mark(event, "failed" if failed else "processed")

    @staticmethod
    async def _run(handler: Handler, event: DomainEvent) -> None:
        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception(
                "event.handler_failed",
                extra={
                    "event": str(event.name),
                    "event_id": event.event_id,
                    "handler": getattr(handler, "__qualname__", "?"),
                },
            )
            raise

    @staticmethod
    async def _mark(event: DomainEvent, status: str) -> None:
        try:
            from sincere.shared.db import C, collection

            await collection(C.OUTBOX).update_one(
                {"_id": event.event_id},
                {
                    "$set": {"status": status, "processed_at": datetime.now(UTC)},
                    "$inc": {"attempts": 1},
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("outbox.mark_failed", extra={"event_id": event.event_id})


#: Application-wide bus. Each module's ``events.py`` registers its handlers against this
#: at import time; ``sincere.main`` imports every module so registration happens on boot.
bus = EventBus()


async def replay_pending(limit: int = 500) -> int:
    """Re-dispatch outbox entries left pending or failed.

    Backstop for the at-least-once guarantee, run by the outbox sweeper job (§15b). Returns
    the number of events re-dispatched. Handlers are idempotent, so replay is always safe.
    """
    from sincere.shared.db import C, collection

    cursor = (
        collection(C.OUTBOX)
        .find({"status": {"$in": ["pending", "failed"]}, "attempts": {"$lt": 10}})
        .sort("created_at", 1)
        .limit(limit)
    )
    count = 0
    async for doc in cursor:
        event = DomainEvent(
            name=Event(doc["event_name"]),
            payload=doc["payload"],
            event_id=doc["_id"],
            occurred_at=doc["occurred_at"],
            correlation_id=doc.get("correlation_id"),
        )
        await bus._dispatch(event)  # noqa: SLF001
        count += 1
    if count:
        logger.info("outbox.replayed", extra={"count": count})
    return count
