import pytest

from cassette.sim.clock import VirtualClock
from cassette.sim.events import Event, FireTimer
from cassette.sim.scheduler import Scheduler


def drain(scheduler: Scheduler) -> list[Event]:
    events: list[Event] = []
    while (event := scheduler.pop()) is not None:
        events.append(event)
    return events


def tags(events: list[Event]) -> list[str]:
    return [e.action.tag for e in events if isinstance(e.action, FireTimer)]


def test_an_empty_queue_pops_nothing() -> None:
    assert Scheduler(VirtualClock()).pop() is None


def test_events_come_back_in_timestamp_order() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.schedule(30, 1, FireTimer("late"))
    scheduler.schedule(10, 1, FireTimer("early"))
    scheduler.schedule(20, 1, FireTimer("middle"))
    assert tags(drain(scheduler)) == ["early", "middle", "late"]


def test_ties_are_broken_by_insertion_order() -> None:
    scheduler = Scheduler(VirtualClock())
    for i in range(8):
        scheduler.schedule(5, 8 - i, FireTimer(f"t{i}"))
    assert tags(drain(scheduler)) == [f"t{i}" for i in range(8)]


def test_popping_advances_the_clock() -> None:
    clock = VirtualClock()
    scheduler = Scheduler(clock)
    scheduler.schedule(250, 1, FireTimer("t"))
    scheduler.pop()
    assert clock.now == 250


def test_the_clock_only_moves_when_an_event_is_taken() -> None:
    clock = VirtualClock()
    scheduler = Scheduler(clock)
    scheduler.schedule(250, 1, FireTimer("t"))
    assert clock.now == 0


def test_scheduling_is_relative_to_the_current_time() -> None:
    clock = VirtualClock()
    scheduler = Scheduler(clock)
    scheduler.schedule(100, 1, FireTimer("first"))
    scheduler.pop()
    scheduler.schedule(50, 1, FireTimer("second"))
    event = scheduler.pop()
    assert event is not None
    assert event.time_ms == 150


def test_a_zero_delay_event_still_runs_after_the_current_one() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.schedule(0, 1, FireTimer("now"))
    event = scheduler.pop()
    assert event is not None
    assert event.time_ms == 0


def test_cancelled_events_are_skipped() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.schedule(10, 1, FireTimer("kept"))
    handle = scheduler.schedule(20, 1, FireTimer("dropped"))
    scheduler.schedule(30, 1, FireTimer("also-kept"))
    scheduler.cancel(handle)
    assert tags(drain(scheduler)) == ["kept", "also-kept"]


def test_cancelling_an_unknown_handle_is_harmless() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.cancel(999)
    scheduler.schedule(10, 1, FireTimer("kept"))
    assert tags(drain(scheduler)) == ["kept"]


def test_pending_counts_queued_entries() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.schedule(10, 1, FireTimer("a"))
    scheduler.schedule(20, 1, FireTimer("b"))
    assert scheduler.pending == 2
    assert len(scheduler) == 2


def test_events_carry_their_ordering_key() -> None:
    scheduler = Scheduler(VirtualClock())
    scheduler.schedule(10, 3, FireTimer("a"))
    event = scheduler.pop()
    assert event == Event(time_ms=10, seq=0, node=3, action=FireTimer("a"))


def test_a_negative_delay_is_rejected() -> None:
    scheduler = Scheduler(VirtualClock())
    with pytest.raises(ValueError, match="in the past"):
        scheduler.schedule(-1, 1, FireTimer("t"))


def test_scheduling_before_the_current_time_is_rejected() -> None:
    scheduler = Scheduler(VirtualClock(500))
    with pytest.raises(ValueError, match="already at 500"):
        scheduler.schedule_at(499, 1, FireTimer("t"))
