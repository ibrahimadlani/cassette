from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from tests.fakes import RecordingNode

CLUSTER = 5


def cluster(skew_ms: int) -> Simulation:
    sim = Simulation(seed=8421, config=FaultConfig(latency_ms=(10, 10), clock_skew_ms=skew_ms))
    for node_id in range(CLUSTER):
        sim.add_node(RecordingNode(node_id=node_id))
    return sim


def test_without_skew_every_node_agrees() -> None:
    sim = cluster(skew_ms=0)
    assert {sim.env_for(node_id).now() for node_id in sim.node_ids} == {0}


def test_with_skew_nodes_disagree() -> None:
    sim = cluster(skew_ms=500)
    readings = {sim.env_for(node_id).now() for node_id in sim.node_ids}
    assert len(readings) > 1


def test_skew_stays_inside_the_bound() -> None:
    sim = cluster(skew_ms=500)
    assert all(abs(sim.skew_of(node_id)) <= 500 for node_id in sim.node_ids)


def test_a_node_keeps_its_offset_for_the_whole_run() -> None:
    sim = cluster(skew_ms=500)
    offsets = {node_id: sim.skew_of(node_id) for node_id in sim.node_ids}
    sim.env_for(0).set_timer(10_000, "tick")
    sim.run()
    assert {node_id: sim.skew_of(node_id) for node_id in sim.node_ids} == offsets


def test_skew_never_reads_as_negative_time() -> None:
    sim = cluster(skew_ms=5_000)
    assert all(sim.env_for(node_id).now() >= 0 for node_id in sim.node_ids)


def test_skew_does_not_move_the_scheduler() -> None:
    sim = cluster(skew_ms=5_000)
    sim.env_for(0).set_timer(1_000, "tick")
    sim.run()
    assert sim.clock.now == 1_000


def test_the_same_seed_draws_the_same_offsets() -> None:
    left, right = cluster(skew_ms=500), cluster(skew_ms=500)
    assert [left.skew_of(i) for i in range(CLUSTER)] == [right.skew_of(i) for i in range(CLUSTER)]
