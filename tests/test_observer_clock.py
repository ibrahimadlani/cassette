"""Whose clock stamps the history.

Linearizability is defined against real time. If the timestamps that define
"real time" come from a drifting clock, the checker reports violations that
are artefacts of the measurement rather than of the system — and a checker with
false positives is worse than no checker, because it teaches you to ignore it.
"""

from __future__ import annotations

from cassette.kv.client import Client, PlannedOp
from cassette.runner import execute
from cassette.scenario import generate
from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from tests.fakes import RecordingNode

SKEWED = FaultConfig(latency_ms=(1, 1), clock_skew_ms=500)


def test_a_node_registered_as_unskewed_reads_the_true_clock() -> None:
    sim = Simulation(seed=8421, config=SKEWED)
    sim.add_node(RecordingNode(node_id=0), skewed=False)
    sim.add_node(RecordingNode(node_id=1))
    assert sim.skew_of(0) == 0


def test_exempting_a_node_still_draws_its_offset() -> None:
    """Otherwise turning skew off for one node would move every later decision."""
    skewed = Simulation(seed=8421, config=SKEWED)
    unskewed = Simulation(seed=8421, config=SKEWED)
    skewed.add_node(RecordingNode(node_id=0))
    unskewed.add_node(RecordingNode(node_id=0), skewed=False)
    skewed.add_node(RecordingNode(node_id=1))
    unskewed.add_node(RecordingNode(node_id=1))
    assert skewed.skew_of(1) == unskewed.skew_of(1)


def test_replicas_still_drift() -> None:
    sim = Simulation(seed=8421, config=SKEWED)
    for node_id in range(5):
        sim.add_node(RecordingNode(node_id=node_id))
    assert len({sim.env_for(node_id).now() for node_id in sim.node_ids}) > 1


def test_clients_agree_on_the_time_even_under_heavy_skew() -> None:
    scenario = generate(8421, faults=FaultConfig(latency_ms=(1, 5), clock_skew_ms=2_000))
    run = execute(scenario, record=False, judge=False)
    assert all(op.invoked_ms >= 0 for op in run.history.operations)
    assert all(op.returned_ms >= op.invoked_ms for op in run.history.operations if op.completed)


def test_an_operation_cannot_return_before_it_was_invoked() -> None:
    """The symptom the drifting stamps produced: negative-length operations."""
    scenario = generate(4242, faults=FaultConfig(latency_ms=(1, 30), clock_skew_ms=1_000))
    for op in execute(scenario, record=False, judge=False).history.operations:
        if op.completed:
            assert op.returned_ms >= op.invoked_ms, op.describe()


def test_two_clients_stamps_are_comparable() -> None:
    """A sequential write then read across two clients must not appear reversed."""
    from cassette.checker.history import History
    from cassette.kv.config import StoreConfig
    from cassette.kv.replica import Replica

    store = StoreConfig()
    history = History()
    sim = Simulation(seed=1, config=FaultConfig(latency_ms=(1, 1), clock_skew_ms=5_000))
    for node_id in store.replica_ids:
        sim.add_node(Replica(node_id, store))

    writer = Client(5, (PlannedOp("write", "x", 1),), history)
    reader = Client(6, (PlannedOp("read", "x", delay_ms=1_000),), history)
    sim.add_node(writer, skewed=False)
    sim.add_node(reader, skewed=False)
    writer.start(sim.env_for(5))
    reader.start(sim.env_for(6))
    sim.run(until_ms=30_000)

    write_op, read_op = history.operations
    assert write_op.returned_ms < read_op.invoked_ms
    assert read_op.result == 1
