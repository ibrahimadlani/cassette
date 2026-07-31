"""A synthetic workload for the determinism test.

The KV store does not exist yet, and waiting for it would be the wrong order:
the determinism contract has to be enforceable before there is anything to
enforce it on. So the workload here is deliberately dumb — five nodes
gossiping — but it exercises every part of the engine that could leak
non-determinism: the queue, the bus, all three timing faults, crash-restart,
pauses and clock skew.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cassette.sim.clock import VirtualClock
from cassette.sim.env import Env
from cassette.sim.faults import FaultConfig
from cassette.sim.injector import FaultInjector
from cassette.sim.recorder import Recorder
from cassette.sim.simulation import Simulation
from cassette.sim.types import JsonDict, NodeId, Payload

CLUSTER_SIZE = 5
HEARTBEAT_MS = 250
HORIZON_MS = 5_000

STRESS = FaultConfig(
    latency_ms=(1, 50),
    drop_rate=0.05,
    dup_rate=0.03,
    partition_rate=0.05,
    partition_duration_ms=(200, 800),
    crash_rate=0.03,
    crash_duration_ms=(100, 600),
    pause_rate=0.03,
    pause_duration_ms=(50, 300),
    clock_skew_ms=100,
    tick_ms=100,
)


@dataclass(frozen=True, slots=True)
class Beat:
    """A heartbeat carrying the sender's own view of the time."""

    sent_at: int

    @property
    def kind(self) -> str:
        return "beat"

    def to_json(self) -> JsonDict:
        return {"sent_at": self.sent_at}


@dataclass
class GossipNode:
    """Broadcasts on a timer and remembers when it last heard from each peer."""

    node_id: NodeId
    peers: tuple[NodeId, ...] = ()
    last_seen: dict[NodeId, int] = field(default_factory=dict)

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        assert isinstance(msg, Beat)
        self.last_seen[sender] = msg.sent_at

    def on_timer(self, env: Env, tag: str) -> None:
        for peer in self.peers:
            env.send(peer, Beat(env.now()))
        env.set_timer(HEARTBEAT_MS, "heartbeat")

    def on_crash(self) -> None:
        self.last_seen.clear()

    def on_restart(self, env: Env) -> None:
        env.set_timer(HEARTBEAT_MS, "heartbeat")


def run_workload(seed: int, config: FaultConfig = STRESS, horizon_ms: int = HORIZON_MS) -> Recorder:
    """Run the gossip cluster under `config` and return what was recorded."""
    clock = VirtualClock()
    recorder = Recorder(clock)
    sim = Simulation(seed=seed, config=config, observer=recorder, clock=clock)

    nodes = [GossipNode(node_id=i) for i in range(CLUSTER_SIZE)]
    for node in nodes:
        node.peers = tuple(peer.node_id for peer in nodes if peer.node_id != node.node_id)
        sim.add_node(node)

    FaultInjector(sim, sim.node_ids).start()
    for node in nodes:
        sim.env_for(node.node_id).set_timer(HEARTBEAT_MS, "heartbeat")

    sim.run(until_ms=horizon_ms)
    return recorder
