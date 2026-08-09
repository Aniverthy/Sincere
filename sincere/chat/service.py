"""Chat business logic (FR-4.1-4.2, §7, §17).

FR-4.1 puts chat in MVP scope explicitly because it is the data source for engagement,
reciprocity training and churn signals — not merely a feature. Every message therefore fans
out to three consumers (§14: matching, feedback_ml, admission).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sincere.chat import presence
from sincere.chat import repository as repo
from sincere.chat.schemas import (
    MessageListResponse,
    MessageOut,
    ReportResponse,
    WsEventType,
)
from sincere.matching import api as matching
from sincere.shared.audit import AuditAction, record
from sincere.shared.errors import ConflictError, ForbiddenError, NotFoundError
from sincere.shared.events import Event, bus

logger = logging.getLogger(__name__)

HISTORY_PAGE_SIZE = 50


async def _authorize(match_id: str, user_id: str) -> dict[str, Any]:
    match = await matching.get_match(match_id)
    if match is None:
        raise NotFoundError("Conversation")
    if user_id not in match.get("users", []):
        # 403 rather than 404: the caller is authenticated, and pretending the match does not
        # exist would still leak its existence through timing.
        raise ForbiddenError("Not your conversation", "You are not part of this match.")
    return match


async def send_message(
    match_id: str, sender_id: str, body: str, client_id: str | None = None
) -> MessageOut:
    """Persist and fan out a message.

    §19: "WebSocket + single insert; aggregates updated async". The insert is synchronous;
    engagement aggregates and the We-Met trigger ride the ``MessageSent`` event.
    """
    match = await _authorize(match_id, sender_id)

    if match.get("status") != "active":
        raise ConflictError(
            "Conversation ended", "You can no longer send messages to this match."
        )

    doc = await repo.insert_message(
        match_id=match_id, sender_id=sender_id, body=body, client_id=client_id
    )

    recipients = [uid for uid in match["users"] if uid != sender_id]
    total, avg_latency = await repo.response_latency_stats(match_id)

    frame = {
        "type": str(WsEventType.MESSAGE),
        "match_id": match_id,
        "data": {
            "message_id": doc["_id"],
            "sender_id": sender_id,
            "body": body,
            "sent_at": doc["sent_at"].isoformat(),
            "client_id": client_id,
        },
    }

    # Deliver on this replica, then publish so any replica holding the recipient's socket
    # also delivers (§20). Both paths are needed: local-only breaks multi-replica, and
    # publish-only would round-trip through Redis for the common same-replica case.
    delivered_here = await presence.send_local(recipients[0], frame) if recipients else 0
    await presence.publish(match_id, {**frame, "recipients": recipients})

    if delivered_here:
        await repo.mark_delivered([doc["_id"]])

    # §14's three-way ripple: matching (engagement), feedback_ml (We-Met), admission (churn).
    await bus.emit(
        Event.MESSAGE_SENT,
        {
            "match_id": match_id,
            "sender_id": sender_id,
            "recipients": recipients,
            "sent_at": doc["sent_at"],
            "msg_count": total,
            "avg_response_latency_s": avg_latency,
            # Deliberately NOT the body — §22 forbids message bodies leaving chat.
        },
    )

    return MessageOut(
        message_id=doc["_id"],
        match_id=match_id,
        sender_id=sender_id,
        body=body,
        sent_at=doc["sent_at"],
        delivered_at=doc.get("delivered_at"),
        mine=True,
    )


async def history(
    match_id: str, user_id: str, *, after: datetime | None = None
) -> MessageListResponse:
    """``GET /matches/:id/messages?after=`` — history, or the reconnect delta (§4)."""
    await _authorize(match_id, user_id)

    messages = await repo.list_messages(match_id, after=after, limit=HISTORY_PAGE_SIZE + 1)
    has_more = len(messages) > HISTORY_PAGE_SIZE
    page = messages[:HISTORY_PAGE_SIZE]

    # Opening the thread marks the other side's messages read (§7 read receipts).
    changed = await repo.mark_read(match_id, user_id)
    if changed:
        await _notify_read(match_id, user_id)

    return MessageListResponse(
        match_id=match_id,
        messages=[
            MessageOut(
                message_id=doc["_id"],
                match_id=match_id,
                sender_id=doc["sender_id"],
                body=doc["body"],
                sent_at=doc["sent_at"],
                delivered_at=doc.get("delivered_at"),
                read_at=doc.get("read_at"),
                mine=doc["sender_id"] == user_id,
            )
            for doc in page
        ],
        has_more=has_more,
        next_after=page[-1]["sent_at"].isoformat() if page else None,
    )


async def _notify_read(match_id: str, reader_id: str) -> None:
    match = await matching.get_match(match_id)
    if match is None:
        return
    recipients = [uid for uid in match["users"] if uid != reader_id]
    frame = {
        "type": str(WsEventType.READ),
        "match_id": match_id,
        "data": {"reader_id": reader_id, "at": datetime.now(UTC).isoformat()},
    }
    for recipient in recipients:
        await presence.send_local(recipient, frame)
    await presence.publish(match_id, {**frame, "recipients": recipients})


async def report(match_id: str, reporter_id: str, reason: str) -> ReportResponse:
    """``POST /matches/:id/report`` — harassment report.

    §7 and §18: the report **pauses that conversation's retention clock** so the evidence
    survives the 90-day purge while the case is open.
    """
    await _authorize(match_id, reporter_id)

    held = await repo.apply_retention_hold(match_id)
    now = datetime.now(UTC)

    await bus.emit(
        Event.HARASSMENT_REPORTED,
        {"match_id": match_id, "reporter_id": reporter_id, "reason": reason, "at": now},
    )
    await record(
        AuditAction.RETENTION_HOLD_APPLIED,
        actor_id=reporter_id,
        context={"match_id": match_id, "messages_held": held, "reason": reason},
    )
    logger.info("chat.reported", extra={"match_id": match_id, "messages_held": held})

    return ReportResponse(
        match_id=match_id,
        reported_at=now,
        retention_hold=True,
        message=(
            "Thank you. We have preserved this conversation for review and a person will "
            "look at it. You can unmatch at any time."
        ),
    )


async def open_conversation(match_id: str, users: list[str]) -> None:
    """§14: matching -> chat on ``MatchFormed``. "Open conversation".

    There is no conversation document to create — the match *is* the conversation. What this
    does is subscribe the replica to the channel and push a toast to whoever is online (§17:
    "match-formed toast").
    """
    await presence.subscribe(match_id)

    frame = {
        "type": str(WsEventType.MATCH_FORMED),
        "match_id": match_id,
        "data": {"match_id": match_id},
    }
    for user_id in users:
        await presence.send_local(user_id, frame)
    await presence.publish(match_id, {**frame, "recipients": users})


async def engagement_for(match_id: str) -> tuple[int, float | None]:
    return await repo.response_latency_stats(match_id)
