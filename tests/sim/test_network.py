import pytest

from cassette.sim.clock import VirtualClock
from cassette.sim.events import DeliverMessage
from cassette.sim.network import Network
from cassette.sim.rng import Rng
from cassette.sim.scheduler import Scheduler
from tests.fakes import Ping


def build(latency_ms: tuple[int, int] = (1, 20), seed: int = 8421) -> tuple[Scheduler, Network]:
    scheduler = Scheduler(VirtualClock())
    return scheduler, Network(scheduler, Rng(seed), latency_ms)


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
