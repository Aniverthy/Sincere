"""HTTP and WebSocket routes for chat (§7 Chat)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from sincere.chat import presence, service
from sincere.chat.schemas import (
    MessageListResponse,
    MessageOut,
    ReportRequest,
    ReportResponse,
    SendMessageRequest,
    WsEventType,
)
from sincere.shared.auth import (
    CHAT_SCOPES,
    Principal,
    principal_from_websocket,
    require_scopes,
)
from sincere.shared.errors import ProblemException
from sincere.shared.ratelimit import check as rate_limit_check
from sincere.shared.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# §5: only an ACTIVE token reaches chat. §24 asserts a waitlisted token cannot.
ChatPrincipal = Annotated[Principal, Depends(require_scopes(*CHAT_SCOPES))]


@router.get(
    "/matches/{match_id}/messages",
    response_model=MessageListResponse,
    summary="History, or the reconnect delta when ?after= is supplied",
)
async def messages(
    match_id: str,
    principal: ChatPrincipal,
    after: Annotated[
        datetime | None, Query(description="ISO timestamp; returns later messages")
    ] = None,
) -> MessageListResponse:
    return await service.history(match_id, principal.user_id, after=after)


@router.post(
    "/matches/{match_id}/messages",
    response_model=MessageOut,
    summary="REST fallback for sending (the WebSocket is the primary path)",
    dependencies=[Depends(rate_limit("message"))],
)
async def send(
    match_id: str, payload: SendMessageRequest, principal: ChatPrincipal
) -> MessageOut:
    return await service.send_message(
        match_id, principal.user_id, payload.body, payload.client_id
    )


@router.post(
    "/matches/{match_id}/report",
    response_model=ReportResponse,
    summary="Harassment report — pauses this conversation's retention clock",
)
async def report(
    match_id: str, payload: ReportRequest, principal: ChatPrincipal
) -> ReportResponse:
    return await service.report(match_id, principal.user_id, payload.reason)


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    """§7 ``WS /ws/chat`` — send/receive, delivery + read receipts.

    §5: "access JWT presented at connect; connection dropped on expiry, client silently
    reconnects after refresh". Authentication happens before ``accept()`` so an unauthorized
    socket is never established.
    """
    principal = await principal_from_websocket(websocket)
    if principal is None:
        # 1008 = policy violation. The client treats this as "refresh and retry once".
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    await presence.register(principal.user_id, websocket)
    logger.info("chat.socket_open", extra={"user_id": principal.user_id})

    try:
        while True:
            frame = await websocket.receive_json()
            await _handle_frame(websocket, principal, frame)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("chat.socket_error", extra={"user_id": principal.user_id})
    finally:
        await presence.unregister(principal.user_id, websocket)
        logger.info("chat.socket_closed", extra={"user_id": principal.user_id})


async def _handle_frame(websocket: WebSocket, principal: Principal, frame: dict) -> None:
    kind = frame.get("type")
    match_id = frame.get("match_id")

    if kind == str(WsEventType.MESSAGE) and match_id:
        body = (frame.get("data") or {}).get("body", "")
        if not body or len(body) > 2_000:
            await websocket.send_json(
                {"type": str(WsEventType.ERROR), "data": {"detail": "Invalid message body."}}
            )
            return
        try:
            # §18 rate-limits message velocity on the socket path too — otherwise the
            # WebSocket would be an unmetered bypass of the REST limit.
            await rate_limit_check("message", principal.user_id)
            await service.send_message(
                match_id, principal.user_id, body, (frame.get("data") or {}).get("client_id")
            )
        except ProblemException as exc:
            await websocket.send_json(
                {
                    "type": str(WsEventType.ERROR),
                    "match_id": match_id,
                    "data": {"title": exc.title, "detail": exc.detail},
                }
            )
        return

    if kind == str(WsEventType.READ) and match_id:
        await service.history(match_id, principal.user_id)
        return

    if kind == str(WsEventType.TYPING) and match_id:
        # Ephemeral: never persisted, and deliberately not an event — §22 keeps chat metadata
        # minimal, and a typing indicator is not engagement data.
        await presence.publish(
            match_id,
            {
                "type": str(WsEventType.TYPING),
                "match_id": match_id,
                "data": {"user_id": principal.user_id},
                "recipients": [],
            },
        )
