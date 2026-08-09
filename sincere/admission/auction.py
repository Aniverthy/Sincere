"""Daily ascending-bid auction (FR-2.9, §15a, §16).

FR-2.9 (DECIDED): "live ascending-bid, **once daily, fixed window**, top bidders at close win
that day's auction slots".

Storage follows §15a exactly: live bidding state is a **Redis sorted set** scored by bid
amount, snapshotted and written through to MongoDB at settlement. The sorted set is the right
structure because the two hot operations — "place a bid" and "what is the standing
requirement" — are both O(log n) against it, and §21 pages on auction-close latency.

Two correctness rules that the §24 property test pins down:

* **Ascending only.** A bid must strictly exceed the bidder's own previous bid, and must at
  least meet the minimum. Lowering a bid mid-window would let someone hold a winning slot and
  then cheapen it at the last second.
* **Winners are exactly the top-k bidders at close.** Not "the first k to bid", not "everyone
  above the clearing price" — exactly the top k by amount, ties broken by bid time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sincere.shared import cache
from sincere.shared.errors import ConflictError, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Bid:
    user_id: str
    amount_paise: int
    placed_at: datetime


@dataclass(frozen=True, slots=True)
class Settlement:
    winners: list[Bid]
    losers: list[Bid]
    clearing_bid_paise: int | None
    """The lowest winning bid. Losers are refunded in full (§7 ``GET /auction/result``)."""


def window_for(day: date, start_hour: int, end_hour: int) -> tuple[datetime, datetime]:
    """The fixed daily window (FR-2.9).

    Times are UTC-normalized here; the Celery beat schedule runs in Asia/Kolkata, matching
    the single-city launch (§25 phase 2).
    """
    start = datetime.combine(day, time(hour=start_hour), tzinfo=UTC)
    end = datetime.combine(day, time(hour=end_hour), tzinfo=UTC)
    if end <= start:  # window crossing midnight
        end += timedelta(days=1)
    return start, end


def is_open(now: datetime, window_start: datetime, window_end: datetime) -> bool:
    return window_start <= now < window_end


def _key(region: str, window_end: datetime) -> str:
    return cache.Keys.auction_bids(region, window_end.date().isoformat())


def _meta_key(region: str, window_end: datetime) -> str:
    return cache.Keys.auction_meta(region, window_end.date().isoformat())


async def place_bid(
    *,
    region: str,
    window_end: datetime,
    user_id: str,
    amount_paise: int,
    min_bid_paise: int,
) -> int:
    """Record an ascending bid. Returns the bidder's current rank (1 = highest).

    Raises when the bid is below the floor or does not improve on the bidder's own standing
    bid — FR-2.9's "ascending" is a property of each bidder's sequence, not just the book.
    """
    if amount_paise < min_bid_paise:
        raise ValidationError(
            f"The minimum bid is ₹{min_bid_paise / 100:.0f}."
        )

    redis = cache.get_redis()
    key = _key(region, window_end)

    existing = await redis.zscore(key, user_id)
    if existing is not None and amount_paise <= int(existing):
        raise ConflictError(
            "Bid must increase",
            f"Your current bid is ₹{int(existing) / 100:.0f}. A new bid must be higher.",
        )

    await redis.zadd(key, {user_id: amount_paise})
    # Record placement time separately: the sorted set scores by amount, but ties at close
    # must break by who bid first, which the score alone cannot express.
    await redis.hset(_meta_key(region, window_end), user_id, datetime.now(UTC).isoformat())

    # Expire well after the window so the settlement job can still read the book if it is
    # delayed; the authoritative copy lands in MongoDB at settlement.
    ttl = max(int((window_end - datetime.now(UTC)).total_seconds()) + 86_400, 3_600)
    await redis.expire(key, ttl)
    await redis.expire(_meta_key(region, window_end), ttl)

    rank = await redis.zrevrank(key, user_id)
    logger.info(
        "auction.bid_placed",
        extra={"region": region, "amount_paise": amount_paise, "rank": (rank or 0) + 1},
    )
    return (rank or 0) + 1


async def read_book(region: str, window_end: datetime) -> list[Bid]:
    """The full order book, highest first, ties broken by earliest placement."""
    redis = cache.get_redis()
    raw = await redis.zrevrange(_key(region, window_end), 0, -1, withscores=True)
    if not raw:
        return []

    times = await redis.hgetall(_meta_key(region, window_end))
    bids = [
        Bid(
            user_id=user_id,
            amount_paise=int(score),
            placed_at=_parse_time(times.get(user_id)),
        )
        for user_id, score in raw
    ]
    bids.sort(key=lambda bid: (-bid.amount_paise, bid.placed_at))
    return bids


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(UTC)


async def standing_requirement(region: str, window_end: datetime, slots: int, min_bid: int) -> int:
    """What a new entrant must beat to be in a winning position right now (§7).

    While the book is not yet full, that is simply the minimum bid — every bidder is winning.
    Once full, it is the current lowest winning bid.
    """
    book = await read_book(region, window_end)
    if slots <= 0:
        return min_bid
    if len(book) < slots:
        return min_bid
    return book[slots - 1].amount_paise


async def user_position(
    region: str, window_end: datetime, user_id: str
) -> tuple[int | None, int | None]:
    """Returns ``(amount_paise, rank)`` for one bidder, or ``(None, None)``."""
    book = await read_book(region, window_end)
    for index, bid in enumerate(book, start=1):
        if bid.user_id == user_id:
            return bid.amount_paise, index
    return None, None


def settle(book: list[Bid], slots: int) -> Settlement:
    """Determine winners at close (FR-2.9).

    Pure function over the book so §24's property test — "winners are exactly the top-k
    bidders at close" — can exercise it without Redis.

    Ties at the cut line break by earliest placement, which :func:`read_book` has already
    applied. That rule has to exist: two identical bids for one remaining slot is otherwise
    undefined, and an undefined auction outcome is a dispute.
    """
    if slots <= 0 or not book:
        return Settlement(winners=[], losers=list(book), clearing_bid_paise=None)

    ordered = sorted(book, key=lambda bid: (-bid.amount_paise, bid.placed_at))
    winners = ordered[:slots]
    losers = ordered[slots:]
    clearing = winners[-1].amount_paise if winners else None

    logger.info(
        "auction.settled",
        extra={"winners": len(winners), "losers": len(losers), "clearing_bid_paise": clearing},
    )
    return Settlement(winners=winners, losers=losers, clearing_bid_paise=clearing)


async def clear_book(region: str, window_end: datetime) -> None:
    """Drop the live Redis state after settlement has been written through to MongoDB."""
    redis = cache.get_redis()
    await redis.delete(_key(region, window_end), _meta_key(region, window_end))
