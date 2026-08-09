"""Event bus tests.

The load-bearing property (§3 rule 3, §14): a consumer's failure must never fail the
emitter. If a chat handler can break an identity write, the modules are coupled again and
the microservice extraction stops being cheap.
"""

from __future__ import annotations

import pytest

from sincere.shared.events import Event, EventBus


class TestDispatch:
    async def test_handler_receives_the_event(self, event_bus: EventBus) -> None:
        seen = []
        event_bus.subscribe(Event.USER_VERIFIED, lambda e: seen.append(e))

        await event_bus.emit(Event.USER_VERIFIED, {"user_id": "u1"}, persist=False)

        assert len(seen) == 1
        assert seen[0].payload == {"user_id": "u1"}

    async def test_sync_and_async_handlers_both_run(self, event_bus: EventBus) -> None:
        calls = []

        def sync_handler(event) -> None:
            calls.append("sync")

        async def async_handler(event) -> None:
            calls.append("async")

        event_bus.subscribe(Event.MATCH_FORMED, sync_handler)
        event_bus.subscribe(Event.MATCH_FORMED, async_handler)
        await event_bus.emit(Event.MATCH_FORMED, {}, persist=False)

        assert sorted(calls) == ["async", "sync"]

    async def test_all_consumers_of_message_sent_are_reached(self, event_bus: EventBus) -> None:
        """§14 diagrams MessageSent fanning out to matching, feedback_ml AND admission.
        A partial fan-out would silently break engagement scores or the We-Met trigger."""
        reached = set()
        for consumer in ("matching", "feedback_ml", "admission"):
            event_bus.subscribe(Event.MESSAGE_SENT, lambda e, c=consumer: reached.add(c))

        await event_bus.emit(Event.MESSAGE_SENT, {"match_id": "m1"}, persist=False)

        assert reached == {"matching", "feedback_ml", "admission"}


class TestFailureIsolation:
    async def test_a_failing_handler_does_not_break_the_emitter(self, event_bus: EventBus) -> None:
        def explodes(event) -> None:
            raise RuntimeError("consumer is broken")

        event_bus.subscribe(Event.USER_VERIFIED, explodes)

        # Must not raise — §3 rule 3's whole purpose.
        event = await event_bus.emit(Event.USER_VERIFIED, {"user_id": "u1"}, persist=False)
        assert event.payload == {"user_id": "u1"}

    async def test_one_failing_handler_does_not_stop_the_others(self, event_bus: EventBus) -> None:
        survived = []

        def explodes(event) -> None:
            raise RuntimeError("boom")

        event_bus.subscribe(Event.MESSAGE_SENT, explodes)
        event_bus.subscribe(Event.MESSAGE_SENT, lambda e: survived.append(1))

        await event_bus.emit(Event.MESSAGE_SENT, {}, persist=False)
        assert survived == [1]

    async def test_event_with_no_handlers_is_harmless(self, event_bus: EventBus) -> None:
        await event_bus.emit(Event.AUCTION_CLOSED, {"region": "8928308280fffff"}, persist=False)


class TestEventCatalogue:
    def test_every_section_14_event_exists(self) -> None:
        """The §14 table is the contract between modules; a missing name means a documented
        reaction has no way to fire."""
        documented = {
            "UserVerified",
            "UserActivated",
            "ActiveStatusChanged",
            "SwipeRecorded",
            "MatchFormed",
            "MessageSent",
            "WeMetThresholdReached",
            "Unmatched",
            "HarassmentReported",
            "PaymentSucceeded",
            "AuctionClosed",
            "WarningIssued",
            "UserBanned",
            "AccountDeletionRequested",
        }
        assert {str(e) for e in Event} == documented

    def test_events_carry_documentation(self) -> None:
        import inspect

        source = inspect.getsource(Event)
        for event in Event:
            assert str(event) in source


class TestOutbox:
    async def test_emit_persists_to_the_outbox(self, database, event_bus: EventBus) -> None:
        """§14 at-least-once: the outbox row is what makes replay possible after a crash."""
        from sincere.shared.db import C

        await event_bus.emit(Event.USER_VERIFIED, {"user_id": "u1"})

        doc = await database[C.OUTBOX].find_one({"event_name": "UserVerified"})
        assert doc is not None
        assert doc["payload"] == {"user_id": "u1"}

    async def test_failed_dispatch_is_marked_for_replay(
        self, database, event_bus: EventBus
    ) -> None:
        from sincere.shared.db import C

        def explodes(event) -> None:
            raise RuntimeError("boom")

        event_bus.subscribe(Event.USER_VERIFIED, explodes)
        await event_bus.emit(Event.USER_VERIFIED, {"user_id": "u1"})

        doc = await database[C.OUTBOX].find_one({"event_name": "UserVerified"})
        assert doc["status"] == "failed"

    async def test_successful_dispatch_is_marked_processed(
        self, database, event_bus: EventBus
    ) -> None:
        from sincere.shared.db import C

        event_bus.subscribe(Event.USER_VERIFIED, lambda e: None)
        await event_bus.emit(Event.USER_VERIFIED, {"user_id": "u1"})

        doc = await database[C.OUTBOX].find_one({"event_name": "UserVerified"})
        assert doc["status"] == "processed"


@pytest.mark.parametrize(
    ("event", "expected_emitter"),
    [
        (Event.USER_VERIFIED, "identity"),
        (Event.USER_ACTIVATED, "admission"),
        (Event.MATCH_FORMED, "matching"),
        (Event.MESSAGE_SENT, "chat"),
        (Event.USER_BANNED, "antiabuse"),
        (Event.PAYMENT_SUCCEEDED, "monetization"),
        (Event.WEMET_THRESHOLD_REACHED, "feedback_ml"),
    ],
)
def test_event_documents_its_emitter(event: Event, expected_emitter: str) -> None:
    """Each event's docstring records emitter -> consumers, mirroring the §14 table."""
    import inspect

    source = inspect.getsource(Event)
    marker = f'{event.name} = "{event.value}"'
    tail = source.split(marker, 1)[1]
    docstring = tail.split('"""')[1]
    assert expected_emitter in docstring
