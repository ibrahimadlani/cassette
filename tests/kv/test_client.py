from cassette.checker.history import OK, UNKNOWN, History
from cassette.kv.client import Client, PlannedOp
from cassette.kv.config import StoreConfig
from cassette.kv.replica import Replica
from cassette.sim.faults import PERFECT_NETWORK, FaultConfig
from cassette.sim.simulation import Simulation


def run(
    plans: dict[int, tuple[PlannedOp, ...]],
    store: StoreConfig | None = None,
    faults: FaultConfig = PERFECT_NETWORK,
    horizon_ms: int = 60_000,
) -> History:
    store = StoreConfig() if store is None else store
    history = History()
    sim = Simulation(seed=8421, config=faults)
    for node_id in store.replica_ids:
        sim.add_node(Replica(node_id, store))
    clients = [Client(node_id, plan, history) for node_id, plan in sorted(plans.items())]
    for client in clients:
        sim.add_node(client)
    for client in clients:
        client.start(sim.env_for(client.node_id))
    sim.run(until_ms=horizon_ms)
    return history


def test_a_plan_runs_in_order() -> None:
    plan = (
        PlannedOp("write", "x", 1),
        PlannedOp("write", "x", 2),
        PlannedOp("read", "x"),
    )
    history = run({5: plan})
    assert [op.kind for op in history.operations] == ["write", "write", "read"]
    assert history.operations[-1].result == 2


def test_every_operation_completes_on_a_healthy_cluster() -> None:
    plan = tuple(PlannedOp("write", "x", value) for value in range(6))
    history = run({5: plan})
    assert all(op.outcome == OK for op in history.operations)


def test_operations_are_stamped_with_logical_time() -> None:
    plan = (PlannedOp("write", "x", 1, delay_ms=100), PlannedOp("read", "x", delay_ms=100))
    history = run({5: plan})
    first, second = history.operations
    assert first.invoked_ms == 100
    assert first.returned_ms > first.invoked_ms
    assert second.invoked_ms >= first.returned_ms + 100


def test_a_client_waits_for_its_own_reply_before_moving_on() -> None:
    plan = (PlannedOp("write", "x", 1), PlannedOp("write", "x", 2))
    history = run({5: plan})
    first, second = history.operations
    assert first.returned_ms <= second.invoked_ms


def test_two_clients_overlap() -> None:
    plan = tuple(PlannedOp("write", "x", value) for value in range(4))
    history = run({5: plan, 6: plan})
    by_client: dict[int, list[int]] = {}
    for op in history.operations:
        by_client.setdefault(op.client, []).append(op.invoked_ms)
    assert sorted(by_client) == [5, 6]
    assert any(
        left.invoked_ms < right.returned_ms and right.invoked_ms < left.returned_ms
        for left in history.operations
        for right in history.operations
        if left.client != right.client
    )


def test_clients_carry_their_own_request_ids() -> None:
    plan = (PlannedOp("write", "x", 1),)
    history = run({5: plan, 6: plan})
    assert {op.client for op in history.operations} == {5, 6}
    assert all(op.outcome == OK for op in history.operations)


def test_an_unanswerable_request_is_recorded_as_unknown() -> None:
    store = StoreConfig(replicas=3, read_quorum=2, write_quorum=2, request_timeout_ms=200)
    history = History()
    sim = Simulation(seed=1, config=PERFECT_NETWORK)
    for node_id in store.replica_ids:
        sim.add_node(Replica(node_id, store))
    client = Client(3, (PlannedOp("write", "x", 1),), history)
    sim.add_node(client)
    for node_id in (1, 2):
        sim.schedule_crash(node_id, downtime_ms=100_000)
    sim.run(until_ms=0)
    client.start(sim.env_for(3))
    sim.run(until_ms=60_000)
    assert history.operations[0].outcome == UNKNOWN


def test_a_client_moves_on_after_an_unknown_operation() -> None:
    store = StoreConfig(replicas=3, read_quorum=2, write_quorum=2, request_timeout_ms=200)
    history = History()
    sim = Simulation(seed=1, config=PERFECT_NETWORK)
    for node_id in store.replica_ids:
        sim.add_node(Replica(node_id, store))
    plan = (PlannedOp("write", "x", 1), PlannedOp("write", "x", 2))
    client = Client(3, plan, history)
    sim.add_node(client)
    for node_id in (1, 2):
        sim.schedule_crash(node_id, downtime_ms=100_000)
    sim.run(until_ms=0)
    client.start(sim.env_for(3))
    sim.run(until_ms=60_000)
    assert len(history) == 2
    assert client.finished is True


def test_a_lost_reply_is_survived_by_the_client_patience_timer() -> None:
    plan = (PlannedOp("write", "x", 1), PlannedOp("read", "x"))
    history = run({5: plan}, faults=FaultConfig(latency_ms=(1, 20), drop_rate=0.3))
    assert len(history) == 2


def test_a_planned_operation_round_trips_through_json() -> None:
    planned = PlannedOp("cas", "x", argument=2, expected=1, coordinator=3, delay_ms=40)
    assert PlannedOp.from_json(planned.to_json()) == planned


def test_a_planned_operation_with_no_argument_round_trips() -> None:
    planned = PlannedOp("read", "x")
    assert PlannedOp.from_json(planned.to_json()) == planned
