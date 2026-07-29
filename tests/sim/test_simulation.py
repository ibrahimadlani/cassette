import pytest

from cassette.sim.simulation import Simulation
from tests.fakes import EchoNode, Ping, RecordingNode


def test_registering_the_same_id_twice_is_rejected() -> None:
    sim = Simulation(seed=1)
    sim.add_node(RecordingNode(node_id=0))
    with pytest.raises(ValueError, match="already registered"):
        sim.add_node(RecordingNode(node_id=0))


def test_node_ids_come_back_sorted() -> None:
    sim = Simulation(seed=1)
    for node_id in (4, 1, 3):
        sim.add_node(RecordingNode(node_id=node_id))
    assert sim.node_ids == [1, 3, 4]


def test_a_message_reaches_its_recipient() -> None:
    sim = Simulation(seed=1)
    sender, recipient = RecordingNode(node_id=0), RecordingNode(node_id=1)
    sim.add_node(sender)
    sim.add_node(recipient)
    sim.env_for(0).send(1, Ping("hello"))
    sim.run()
    assert [text for _, _, text in recipient.messages] == ["hello"]


def test_messages_to_an_unknown_node_are_dropped_on_the_floor() -> None:
    sim = Simulation(seed=1)
    sim.add_node(RecordingNode(node_id=0))
    sim.env_for(0).send(99, Ping())
    assert sim.run() == 1


def test_a_conversation_runs_until_the_queue_drains() -> None:
    sim = Simulation(seed=1)
    left, right = EchoNode(node_id=0, budget=3), EchoNode(node_id=1, budget=3)
    sim.add_node(left)
    sim.add_node(right)
    sim.env_for(0).send(1, Ping("open"))
    sim.run()
    assert (left.seen, right.seen) == (3, 4)


def test_a_timer_fires_after_its_delay() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    sim.env_for(0).set_timer(500, "election")
    sim.run()
    assert node.timers == [(500, "election")]


def test_setting_the_same_tag_again_replaces_the_pending_timer() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    env = sim.env_for(0)
    env.set_timer(500, "election")
    env.set_timer(900, "election")
    sim.run()
    assert node.timers == [(900, "election")]


def test_timers_with_different_tags_coexist() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    env = sim.env_for(0)
    env.set_timer(200, "heartbeat")
    env.set_timer(500, "election")
    sim.run()
    assert node.timers == [(200, "heartbeat"), (500, "election")]


def test_a_cancelled_timer_never_fires() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    env = sim.env_for(0)
    env.set_timer(500, "election")
    env.cancel_timer("election")
    sim.run()
    assert node.timers == []


def test_cancelling_an_unknown_tag_is_harmless() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    sim.env_for(0).cancel_timer("never-set")
    sim.run()
    assert node.timers == []


def test_run_stops_at_the_event_budget() -> None:
    sim = Simulation(seed=1)
    left, right = EchoNode(node_id=0, budget=50), EchoNode(node_id=1, budget=50)
    sim.add_node(left)
    sim.add_node(right)
    sim.env_for(0).send(1, Ping("open"))
    assert sim.run(max_events=5) == 5


def test_run_stops_at_the_time_horizon() -> None:
    sim = Simulation(seed=1)
    node = RecordingNode(node_id=0)
    sim.add_node(node)
    env = sim.env_for(0)
    env.set_timer(100, "soon")
    env.set_timer(10_000, "later")
    sim.run(until_ms=1_000)
    assert node.timers == [(100, "soon")]
    assert sim.clock.now == 100


def test_env_random_draws_from_the_seeded_source() -> None:
    left, right = Simulation(seed=7), Simulation(seed=7)
    left.add_node(RecordingNode(node_id=0))
    right.add_node(RecordingNode(node_id=0))
    assert left.env_for(0).random() == right.env_for(0).random()


def test_step_reports_when_the_queue_is_empty() -> None:
    sim = Simulation(seed=1)
    sim.add_node(RecordingNode(node_id=0))
    assert sim.step() is False
