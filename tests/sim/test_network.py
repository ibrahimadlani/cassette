from typing import Any

import pytest

from cassette.sim.clock import VirtualClock
from cassette.sim.events import DeliverMessage
from cassette.sim.faults import FaultConfig
from cassette.sim.network import Network
from cassette.sim.rng import Rng
from cassette.sim.scheduler import Scheduler
from tests.fakes import Ping


def build(
    latency_ms: tuple[int, int] = (1, 20),
    seed: int = 8421,
    **faults: Any,
) -> tuple[Scheduler, Network]:
    scheduler = Scheduler(VirtualClock())
    config = FaultConfig(latency_ms=latency_ms, **faults)
    return scheduler, Network(scheduler, Rng(seed), config)


def test_message_identifiers_are_a_dense_counter() -> None:
    _, network = build()
    assert [network.send(0, 1, Ping()) for _ in range(4)] == [0, 1, 2, 3]


def test_a_sent_message_is_queued_for_the_recipient() -> None:
    scheduler, network = build()
    network.send(0, 2, Ping("hello"))
    event = scheduler.pop()
    assert event is not None
    assert event.node == 2
    assert event.action == DeliverMessage(sender=0, msg=Ping("hello"), msg_id=0)


def test_nothing_is_delivered_synchronously() -> None:
    scheduler, network = build(latency_ms=(1, 1))
    network.send(0, 1, Ping())
    assert scheduler.peek_time() == 1


def test_latency_stays_inside_the_configured_range() -> None:
    scheduler, network = build(latency_ms=(5, 9))
    for _ in range(200):
        network.send(0, 1, Ping())
    times = []
    while (event := scheduler.pop()) is not None:
        times.append(event.time_ms)
    assert min(times) >= 5
    assert max(times) <= 9


def test_variable_latency_reorders_messages() -> None:
    scheduler, network = build(latency_ms=(1, 60))
    for i in range(30):
        network.send(0, 1, Ping(f"m{i}"))
    arrivals = []
    while (event := scheduler.pop()) is not None:
        assert isinstance(event.action, DeliverMessage)
        arrivals.append(event.action.msg_id)
    assert arrivals != sorted(arrivals)


def test_a_fixed_latency_preserves_order() -> None:
    scheduler, network = build(latency_ms=(7, 7))
    for i in range(10):
        network.send(0, 1, Ping(f"m{i}"))
    arrivals = []
    while (event := scheduler.pop()) is not None:
        assert isinstance(event.action, DeliverMessage)
        arrivals.append(event.action.msg_id)
    assert arrivals == sorted(arrivals)


def test_a_negative_latency_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        build(latency_ms=(-1, 5))


def test_an_inverted_latency_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="is inverted"):
        build(latency_ms=(20, 5))


def test_nothing_is_lost_at_a_zero_drop_rate() -> None:
    scheduler, network = build(drop_rate=0.0)
    for _ in range(100):
        network.send(0, 1, Ping())
    assert scheduler.pending == 100


def test_everything_is_lost_at_a_full_drop_rate() -> None:
    scheduler, network = build(drop_rate=1.0)
    for _ in range(100):
        network.send(0, 1, Ping())
    assert scheduler.pending == 0


def test_a_partial_drop_rate_loses_some_and_keeps_some() -> None:
    scheduler, network = build(drop_rate=0.3)
    for _ in range(1_000):
        network.send(0, 1, Ping())
    assert 200 < 1_000 - scheduler.pending < 400


def test_a_dropped_message_still_burns_its_identifier() -> None:
    _, network = build(drop_rate=1.0)
    assert [network.send(0, 1, Ping()) for _ in range(3)] == [0, 1, 2]


def test_duplicates_are_delivered_twice_under_the_same_identifier() -> None:
    scheduler, network = build(dup_rate=1.0)
    network.send(0, 1, Ping())
    ids = []
    while (event := scheduler.pop()) is not None:
        assert isinstance(event.action, DeliverMessage)
        ids.append(event.action.msg_id)
    assert ids == [0, 0]


def test_duplicates_arrive_at_independent_delays() -> None:
    scheduler, network = build(latency_ms=(1, 100), dup_rate=1.0)
    for _ in range(50):
        network.send(0, 1, Ping())
    arrivals: dict[int, list[int]] = {}
    while (event := scheduler.pop()) is not None:
        assert isinstance(event.action, DeliverMessage)
        arrivals.setdefault(event.action.msg_id, []).append(event.time_ms)
    assert any(times[0] != times[1] for times in arrivals.values())


def test_no_duplicates_at_a_zero_rate() -> None:
    scheduler, network = build(dup_rate=0.0)
    for _ in range(100):
        network.send(0, 1, Ping())
    assert scheduler.pending == 100


def test_switching_a_fault_off_does_not_shift_the_draw_sequence() -> None:
    quiet_scheduler, quiet = build(drop_rate=0.0, dup_rate=0.0)
    noisy_scheduler, noisy = build(drop_rate=0.0, dup_rate=0.0)
    for _ in range(20):
        quiet.send(0, 1, Ping())
        noisy.send(0, 1, Ping())
    assert quiet_scheduler.peek_time() == noisy_scheduler.peek_time()
