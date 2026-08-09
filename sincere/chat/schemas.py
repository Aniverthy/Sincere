"""Request/response models for chat (§7 Chat)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    """One message. **The body is never logged** (§22) — only metadata."""

    message_id: str
    match_id: str
    sender_id: str
    body: str
    sent_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    mine: bool = False


class SendMessageRequest(BaseModel):
    """``POST /matches/:id/messages`` — the REST fallback for the WebSocket."""

    body: str = Field(min_length=1, max_length=2_000)
    client_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Client-generated id echoed back on delivery, so an optimistic bubble can be "
            "reconciled after a reconnect without duplicating."
        ),
    )


class MessageListResponse(BaseModel):
    """``GET /matches/:id/messages?after=`` — paginated history / reconnect delta (§4)."""

    match_id: str
    messages: list[MessageOut]
    has_more: bool = False
    next_after: str | None = None


class ReportRequest(BaseModel):
    """``POST /matches/:id/report`` — harassment report."""

    reason: str = Field(max_length=1_000)


class ReportResponse(BaseModel):
    match_id: str
    reported_at: datetime
    retention_hold: bool
    message: str


class WsEventType(StrEnum):
    """WebSocket frame types on ``/ws/chat`` (§7)."""

    MESSAGE = "message"
    DELIVERED = "delivered"
    READ = "read"
    TYPING = "typing"
    MATCH_FORMED = "match_formed"
    ERROR = "error"


class WsFrame(BaseModel):
    type: WsEventType
    match_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
