"""WebSocket presence and cross-replica fan-out (§16, §20).

§16: "WebSocket presence (match → connected sockets) — chat routing across API replicas
(Redis pub/sub)". §20: "WebSocket fan-out via Redis pub/sub so chat scales across replicas".

The problem this solves: with two API replicas behind a load balancer, Alice's socket may be
on replica A and Bob's on replica B. A message Alice sends arrives at A, which holds no socket
for Bob. Publishing to a Redis channel both replicas subscribe to is what closes that gap —
without it, chat silently works in dev (one process) and silently fails in production.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from sincere.shared import cache

logger = logging.getLogger(__name__)

#: Sockets held by *this* process, keyed by user id. A user may have several (phone + tablet).
_local: dict[str, set[WebSocket]] = defaultdict(set)

_subscriber_task: asyncio.Task[None] | None = None
_subscribed: set[str] = set()


async def register(user_id: str, websocket: WebSocket) -> None:
    _local[user_id].add(websocket)
    logger.debug("chat.socket_registered", extra={"user_id": user_id})


async def unregister(user_id: str, websocket: WebSocket) -> None:
    _local[user_id].discard(websocket)
    if not _local[user_id]:
        _local.pop(user_id, None)


def is_online(user_id: str) -> bool:
    """Whether this process holds a socket for the user.

    Deliberately process-local: it decides whether *this* replica can deliver directly. A
    globally-online user on another replica is reached through the pub/sub channel instead.
    """
    return bool(_local.get(user_id))


async def send_local(user_id: str, frame: dict[str, Any]) -> int:
    """Push a frame to this process's sockets for a user. Returns how many received it."""
    sockets = list(_local.get(user_id, ()))
    delivered = 0
    for socket in sockets:
        try:
            await socket.send_json(frame)
            delivered += 1
        except Exception:  # noqa: BLE001 — a dead socket must not break the fan-out
            logger.debug("chat.socket_send_failed", extra={"user_id": user_id})
            await unregister(user_id, socket)
    return delivered


async def publish(match_id: str, frame: dict[str, Any]) -> None:
    """Broadcast a frame to every replica subscribed to this match's channel (§20)."""
    try:
        await cache.get_redis().publish(
            cache.Keys.chat_channel(match_id), json.dumps(frame, default=str)
        )
    except Exception:  # noqa: BLE001 — Redis down must not fail the message write
        logger.warning("chat.publish_failed", extra={"match_id": match_id})


async def subscribe(match_id: str) -> None:
    """Ensure this process listens on a match's channel."""
    if match_id in _subscribed:
        return
    _subscribed.add(match_id)
    await _ensure_subscriber()


async def _ensure_subscriber() -> None:
    global _subscriber_task
    if _subscriber_task is not None and not _subscriber_task.done():
        return
    _subscriber_task = asyncio.create_task(_listen())


async def _listen() -> None:
    """Relay pub/sub frames to locally-held sockets.

    Pattern-subscribes to ``chat:*`` rather than one channel per match: a single subscription
    covers every conversation this replica serves, instead of one Redis subscription per
    active match.
    """
    try:
        pubsub = cache.get_redis().pubsub()
        await pubsub.psubscribe("chat:*")

        async for message in pubsub.listen():
            if message.get("type") != "pmessage":
                continue
            try:
                frame = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            # `recipients` is added by the publisher so a replica knows who to push to
            # without re-reading the match document.
            for user_id in frame.pop("recipients", []):
                if is_online(user_id):
                    await send_local(user_id, frame)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("chat.subscriber_failed — cross-replica delivery is degraded")


async def shutdown() -> None:
    global _subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _subscriber_task
    _subscriber_task = None
    _subscribed.clear()
    _local.clear()
