"""Auction settlement tests (FR-2.9, §15a).

§24 property: "auction: **winners are exactly the top-k bidders at close**". That phrasing
rules out three plausible-but-wrong implementations — first-k-to-bid, everyone-above-a-price,
and top-k-with-undefined-ties — so each is tested against explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from sincere.admission.auction import Bid, is_open, settle, window_for

BASE = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def bid(user: str, amount: int, minutes: int = 0) -> Bid:
    return Bid(user_id=user, amount_paise=amount, placed_at=BASE + timedelta(minutes=minutes))


class TestSettlement:
    def test_top_k_win(self) -> None:
        book = [bid("a", 50_000), bid("b", 30_000), bid("c", 20_000), bid("d", 10_000)]
        result = settle(book, slots=2)

        assert [w.user_id for w in result.winners] == ["a", "b"]
        assert [x.user_id for x in result.losers] == ["c", "d"]
        assert result.clearing_bid_paise == 30_000

    def test_bid_order_does_not_decide_winners(self) -> None:
        """Not "first k to bid" — a late high bid beats an early low one."""
        book = [bid("early_low", 10_000, minutes=0), bid("late_high", 90_000, minutes=59)]
        result = settle(book, slots=1)
        assert [w.user_id for w in result.winners] == ["late_high"]

    def test_ties_break_by_earliest_bid(self) -> None:
        """Two identical bids for one slot must have a defined outcome, or it is a dispute."""
        book = [bid("second", 40_000, minutes=10), bid("first", 40_000, minutes=5)]
        result = settle(book, slots=1)
        assert [w.user_id for w in result.winners] == ["first"]

    def test_fewer_bidders_than_slots_means_everyone_wins(self) -> None:
        result = settle([bid("a", 20_000), bid("b", 15_000)], slots=5)
        assert len(result.winners) == 2
        assert result.losers == []
        assert result.clearing_bid_paise == 15_000

    def test_empty_book_settles_cleanly(self) -> None:
        result = settle([], slots=3)
        assert result.winners == [] and result.losers == []
        assert result.clearing_bid_paise is None

    def test_zero_slots_means_nobody_wins(self) -> None:
        """A frozen region (FR-2.4) can leave zero auction slots — every bidder must lose and
        be refunded, not silently admitted."""
        result = settle([bid("a", 99_000), bid("b", 88_000)], slots=0)
        assert result.winners == []
        assert len(result.losers) == 2

    def test_clearing_bid_is_the_lowest_winning_bid(self) -> None:
        book = [bid("a", 50_000), bid("b", 40_000), bid("c", 30_000)]
        assert settle(book, slots=3).clearing_bid_paise == 30_000

    def test_settlement_is_deterministic(self) -> None:
        book = [bid("a", 10_000, 1), bid("b", 10_000, 2), bid("c", 10_000, 3)]
        first = [w.user_id for w in settle(book, 2).winners]
        second = [w.user_id for w in settle(list(reversed(book)), 2).winners]
        assert first == second == ["a", "b"]


class TestWindow:
    def test_window_spans_the_configured_hours(self) -> None:
        start, end = window_for(BASE.date(), 19, 20)
        assert start.hour == 19 and end.hour == 20

    def test_window_crossing_midnight_rolls_forward(self) -> None:
        """A 23:00-01:00 window must not produce an end before its start."""
        start, end = window_for(BASE.date(), 23, 1)
        assert end > start
        assert (end - start) == timedelta(hours=2)

    def test_is_open_is_half_open(self) -> None:
        start, end = window_for(BASE.date(), 19, 20)
        assert is_open(start, start, end) is True
        assert is_open(end - timedelta(seconds=1), start, end) is True
        # Closed at exactly the end instant, so the settlement job cannot race a final bid.
        assert is_open(end, start, end) is False
        assert is_open(start - timedelta(seconds=1), start, end) is False


# ---------------------------------------------------------------------------
# §24 property test
# ---------------------------------------------------------------------------

@given(
    amounts=st.lists(st.integers(min_value=1, max_value=1_000_000), min_size=0, max_size=60),
    slots=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=300, deadline=None)
def test_winners_are_exactly_the_top_k_bidders(amounts: list[int], slots: int) -> None:
    """§24: "winners are exactly the top-k bidders at close"."""
    book = [bid(f"u{i}", amount, minutes=i) for i, amount in enumerate(amounts)]
    result = settle(book, slots)

    expected_count = min(slots, len(book))
    assert len(result.winners) == expected_count
    assert len(result.winners) + len(result.losers) == len(book)

    # No loser may have outbid a winner.
    if result.winners and result.losers:
        assert min(w.amount_paise for w in result.winners) >= max(
            x.amount_paise for x in result.losers
        )

    # Winners and losers partition the book exactly — nobody duplicated, nobody dropped.
    assert {w.user_id for w in result.winners} | {x.user_id for x in result.losers} == {
        b.user_id for b in book
    }
    assert not ({w.user_id for w in result.winners} & {x.user_id for x in result.losers})


@given(
    amounts=st.lists(st.integers(min_value=1, max_value=100_000), min_size=1, max_size=40),
    slots=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=200, deadline=None)
def test_clearing_bid_is_never_above_any_winner(amounts: list[int], slots: int) -> None:
    """The clearing price must be payable by every winner."""
    book = [bid(f"u{i}", amount, minutes=i) for i, amount in enumerate(amounts)]
    result = settle(book, slots)
    if result.clearing_bid_paise is not None:
        assert all(w.amount_paise >= result.clearing_bid_paise for w in result.winners)
