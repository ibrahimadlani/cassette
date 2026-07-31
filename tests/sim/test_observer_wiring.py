"""An empty Recorder is falsy, which `observer or NullObserver()` swallowed.

Keeping the regression here rather than in test_recorder.py: the defect was in
how the engine picked its collaborators, not in the recorder itself.
"""

from cassette.sim.clock import VirtualClock
from cassette.sim.faults import FaultConfig
from cassette.sim.recorder import Recorder
from cassette.sim.simulation import Simulation
from tests.fakes import Ping, RecordingNode


def test_an_empty_recorder_is_still_installed() -> None:
    clock = VirtualClock()
    recorder = Recorder(clock)
    assert not recorder.events

    sim = Simulation(seed=1, config=FaultConfig(latency_ms=(1, 1)), observer=recorder, clock=clock)
    sim.add_node(RecordingNode(node_id=0))
    sim.add_node(RecordingNode(node_id=1))
    sim.env_for(0).send(1, Ping())
    sim.run()

    assert [entry["type"] for entry in recorder.events] == ["msg_send", "msg_deliver"]


def test_an_explicit_clock_is_shared_with_the_engine() -> None:
    clock = VirtualClock(start_ms=1_000)
    sim = Simulation(seed=1, clock=clock)
    sim.add_node(RecordingNode(node_id=0))
    sim.env_for(0).set_timer(500, "t")
    sim.run()
    assert clock.now == 1_500
