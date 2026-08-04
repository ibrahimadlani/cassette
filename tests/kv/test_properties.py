"""T-4: invariants that should hold for any plan, on a network with no faults.

Hypothesis generates the operations; the simulator's seed stays fixed, so a
failure here is reported as a plan rather than as a seed and reads directly.

These are sanity checks on the store, not the oracle. They cover the case
where nothing goes wrong, which is exactly the case that has to be beyond
doubt before a violation under partition means anything.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cassette.checker.history import OK, History
from cassette.kv.client import Client, PlannedOp
from cassette.kv.config import StoreConfig
from cassette.kv.replica import Replica
from cassette.sim.faults import PERFECT_NETWORK
from cassette.sim.simulation import Simulation

STORE = StoreConfig(replicas=5, read_quorum=3, write_quorum=3)
CLIENT_ID = 5

keys = st.sampled_from(["x", "y"])
values = st.integers(min_value=0, max_value=99)
coordinators = st.integers(min_value=0, max_value=STORE.replicas - 1)
delays = st.integers(min_value=0, max_value=50)

writes = st.builds(
    PlannedOp,
    kind=st.just("write"),
    key=keys,
    argument=values,
    coordinator=coordinators,
    delay_ms=delays,
)
reads = st.builds(
    PlannedOp,
    kind=st.just("read"),
    key=keys,
    coordinator=coordinators,
    delay_ms=delays,
)
plans = st.lists(st.one_of(writes, reads), min_size=1, max_size=25).map(tuple)

PROPERTY_SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def run(plan: tuple[PlannedOp, ...]) -> tuple[History, list[Replica]]:
    history = History()
    sim = Simulation(seed=8421, config=PERFECT_NETWORK)
    replicas = [Replica(node_id, STORE) for node_id in STORE.replica_ids]
    for replica in replicas:
        sim.add_node(replica)
    client = Client(CLIENT_ID, plan, history)
    sim.add_node(client)
    client.start(sim.env_for(CLIENT_ID))
    sim.run(until_ms=600_000)
    return history, replicas


@given(plans)
@PROPERTY_SETTINGS
def test_every_operation_completes_on_a_healthy_network(plan: tuple[PlannedOp, ...]) -> None:
    history, _ = run(plan)
    assert len(history) == len(plan)
    assert all(op.outcome == OK for op in history.operations)


@given(plans)
@PROPERTY_SETTINGS
def test_a_sequential_client_reads_back_its_own_last_write(
    plan: tuple[PlannedOp, ...],
) -> None:
    """One client, no faults: a read must return the last value written to that key."""
    expected: dict[str, int | None] = {}
    history, _ = run(plan)
    for op in history.operations:
        if op.kind == "write":
            expected[op.key] = op.argument
        else:
            assert op.result == expected.get(op.key), op.describe()


@given(plans)
@PROPERTY_SETTINGS
def test_a_read_never_invents_a_value(plan: tuple[PlannedOp, ...]) -> None:
    written = {op.argument for op in plan if op.kind == "write"} | {None}
    history, _ = run(plan)
    assert all(op.result in written for op in history.operations if op.kind == "read")


@given(plans)
@PROPERTY_SETTINGS
def test_every_replica_converges_on_the_last_write(plan: tuple[PlannedOp, ...]) -> None:
    """No faults means no divergence: after the last write, everyone agrees."""
    history, replicas = run(plan)
    last_write: dict[str, int | None] = {}
    for op in history.operations:
        if op.kind == "write":
            last_write[op.key] = op.argument
    for key, value in last_write.items():
        assert [replica.stored(key).value for replica in replicas] == [value] * STORE.replicas


@given(plans)
@PROPERTY_SETTINGS
def test_the_same_plan_produces_the_same_history(plan: tuple[PlannedOp, ...]) -> None:
    assert run(plan)[0].to_json() == run(plan)[0].to_json()
