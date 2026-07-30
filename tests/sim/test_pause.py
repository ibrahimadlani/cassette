from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from tests.fakes import Ping, RecordingNode


def cluster(size: int = 3) -> tuple[Simulation, list[RecordingNode]]:
    sim = Simulation(seed=8421, config=FaultConfig(latency_ms=(10, 10)))
    nodes = [RecordingNode(node_id=i) for i in range(size)]
    for node in nodes:
        sim.add_node(node)
    return sim, nodes


def test_a_paused_node_is_reported_as_frozen() -> None:
    sim, _ = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    assert sim.is_paused(1) is True
    sim.run()
    assert sim.is_paused(1) is False


def test_a_pause_keeps_the_node_alive() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run()
    assert nodes[1].crashes == 0


def test_messages_queue_up_instead_of_being_lost() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    sim.env_for(0).send(1, Ping("held"))
    sim.run()
    assert [text for _, _, text in nodes[1].messages] == ["held"]


def test_held_messages_land_on_the_far_side_of_the_pause() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    sim.env_for(0).send(1, Ping("held"))
    sim.run()
    assert [when for when, _, _ in nodes[1].messages] == [500]


def test_a_burst_arrives_all_at_once() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    for i in range(5):
        sim.env_for(0).send(1, Ping(f"m{i}"))
    sim.run()
    assert [when for when, _, _ in nodes[1].messages] == [500] * 5


def test_timers_are_deferred_rather_than_dropped() -> None:
    sim, nodes = cluster()
    sim.env_for(1).set_timer(100, "election")
    sim.schedule_pause(1, duration_ms=500)
    sim.run()
    assert nodes[1].timers == [(500, "election")]


def test_a_timer_cancelled_during_a_pause_never_fires() -> None:
    sim, nodes = cluster()
    sim.env_for(1).set_timer(100, "election")
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=100)
    sim.env_for(1).cancel_timer("election")
    sim.run()
    assert nodes[1].timers == []


def test_overlapping_pauses_extend_the_freeze() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=200)
    sim.run(until_ms=0)
    sim.schedule_pause(1, duration_ms=600)
    sim.env_for(0).send(1, Ping("held"))
    sim.run()
    assert [when for when, _, _ in nodes[1].messages] == [600]


def test_a_crash_cancels_a_pause() -> None:
    sim, _ = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    sim.schedule_crash(1, downtime_ms=50)
    sim.run(until_ms=0)
    assert sim.is_paused(1) is False
    assert sim.is_down(1) is True


def test_pausing_an_unknown_node_is_harmless() -> None:
    sim, _ = cluster()
    sim.schedule_pause(99, duration_ms=100)
    sim.run()
    assert sim.is_paused(99) is False


def test_other_nodes_are_unaffected() -> None:
    sim, nodes = cluster()
    sim.schedule_pause(1, duration_ms=500)
    sim.run(until_ms=0)
    sim.env_for(0).send(2, Ping("unblocked"))
    sim.run()
    assert [when for when, _, _ in nodes[2].messages] == [10]
