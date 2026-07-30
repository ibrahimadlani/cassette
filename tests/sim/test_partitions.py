import pytest

from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from tests.fakes import Ping, RecordingNode

MINORITY = frozenset({0})
MAJORITY = frozenset({1, 2})


def cluster(size: int = 3) -> tuple[Simulation, list[RecordingNode]]:
    sim = Simulation(seed=8421, config=FaultConfig(latency_ms=(10, 10)))
    nodes = [RecordingNode(node_id=i) for i in range(size)]
    for node in nodes:
        sim.add_node(node)
    return sim, nodes


def test_a_whole_cluster_reaches_everyone() -> None:
    sim, _ = cluster()
    assert sim.network.can_reach(0, 2) is True
    assert sim.network.partition is None


def test_a_split_cuts_across_groups() -> None:
    sim, _ = cluster()
    sim.network.partition_into((MINORITY, MAJORITY))
    assert sim.network.can_reach(0, 1) is False
    assert sim.network.can_reach(1, 2) is True
    assert sim.network.can_reach(0, 0) is True


def test_participants_outside_every_group_stay_reachable() -> None:
    sim, _ = cluster()
    sim.network.partition_into((MINORITY, MAJORITY))
    assert sim.network.can_reach(0, 99) is True
    assert sim.network.can_reach(99, 1) is True


def test_healing_restores_connectivity() -> None:
    sim, _ = cluster()
    sim.network.partition_into((MINORITY, MAJORITY))
    sim.network.heal()
    assert sim.network.can_reach(0, 1) is True
    assert sim.network.partition is None


def test_healing_a_whole_cluster_is_a_no_op() -> None:
    sim, _ = cluster()
    sim.network.heal()
    assert sim.network.partition is None


def test_a_partition_needs_two_groups() -> None:
    sim, _ = cluster()
    with pytest.raises(ValueError, match="at least two groups"):
        sim.network.partition_into((frozenset({0, 1, 2}),))


def test_messages_across_the_split_never_land() -> None:
    sim, nodes = cluster()
    sim.network.partition_into((MINORITY, MAJORITY))
    sim.env_for(0).send(1, Ping("across"))
    sim.env_for(1).send(2, Ping("within"))
    sim.run()
    assert nodes[1].messages == []
    assert [text for _, _, text in nodes[2].messages] == ["within"]


def test_a_partition_opening_mid_flight_kills_the_message() -> None:
    sim, nodes = cluster()
    sim.env_for(0).send(1, Ping("in flight"))
    sim.network.partition_into((MINORITY, MAJORITY))
    sim.run()
    assert nodes[1].messages == []


def test_a_scheduled_partition_opens_and_closes_on_time() -> None:
    sim, nodes = cluster()
    sim.schedule_partition((MINORITY, MAJORITY), duration_ms=100)
    sim.env_for(0).send(1, Ping("during"))
    sim.run(until_ms=150)
    assert sim.clock.now == 100
    sim.env_for(0).send(1, Ping("after"))
    sim.run()
    assert [text for _, _, text in nodes[1].messages] == ["after"]


def test_the_reserved_control_id_cannot_be_registered() -> None:
    sim, _ = cluster()
    with pytest.raises(ValueError, match="reserved for fault events"):
        sim.add_node(RecordingNode(node_id=-1))
