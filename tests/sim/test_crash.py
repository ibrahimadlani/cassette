from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from tests.fakes import Ping, RecordingNode


def cluster(size: int = 3) -> tuple[Simulation, list[RecordingNode]]:
    sim = Simulation(seed=8421, config=FaultConfig(latency_ms=(10, 10)))
    nodes = [RecordingNode(node_id=i) for i in range(size)]
    for node in nodes:
        sim.add_node(node)
    return sim, nodes


def test_a_crash_calls_the_node_back() -> None:
    sim, nodes = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.run()
    assert nodes[1].crashes == 1
    assert nodes[1].restarts == 1


def test_a_crashed_node_is_reported_as_down() -> None:
    sim, _ = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.run(until_ms=0)
    assert sim.is_down(1) is True
    sim.run()
    assert sim.is_down(1) is False


def test_a_crash_clears_volatile_state() -> None:
    sim, nodes = cluster()
    sim.env_for(0).send(1, Ping("before"))
    sim.run(until_ms=10)
    assert len(nodes[1].messages) == 1
    sim.schedule_crash(1, downtime_ms=100)
    sim.run()
    assert nodes[1].messages == []


def test_messages_to_a_crashed_node_are_lost() -> None:
    sim, nodes = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.run(until_ms=0)
    sim.env_for(0).send(1, Ping("into the void"))
    sim.run()
    assert nodes[1].messages == []


def test_messages_sent_after_a_restart_land() -> None:
    sim, nodes = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.run()
    sim.env_for(0).send(1, Ping("welcome back"))
    sim.run()
    assert [text for _, _, text in nodes[1].messages] == ["welcome back"]


def test_timers_do_not_survive_a_crash() -> None:
    sim, nodes = cluster()
    sim.env_for(1).set_timer(500, "election")
    sim.schedule_crash(1, downtime_ms=100)
    sim.run()
    assert nodes[1].timers == []


def test_a_node_can_re_arm_its_timers_on_restart() -> None:
    sim, nodes = cluster()
    sim.env_for(1).set_timer(50, "election")
    sim.schedule_crash(1, downtime_ms=100)
    sim.run(until_ms=100)
    sim.env_for(1).set_timer(50, "election")
    sim.run()
    assert [tag for _, tag in nodes[1].timers] == ["election"]


def test_crashing_a_node_twice_only_kills_it_once() -> None:
    sim, nodes = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.schedule_crash(1, downtime_ms=200)
    sim.run()
    assert nodes[1].crashes == 1


def test_crashing_an_unknown_node_is_harmless() -> None:
    sim, _ = cluster()
    sim.schedule_crash(99, downtime_ms=100)
    sim.run()
    assert sim.is_down(99) is False


def test_other_nodes_keep_working_while_one_is_down() -> None:
    sim, nodes = cluster()
    sim.schedule_crash(1, downtime_ms=100)
    sim.run(until_ms=0)
    sim.env_for(0).send(2, Ping("still here"))
    sim.run()
    assert [text for _, _, text in nodes[2].messages] == ["still here"]
