"""FR-1: virtual time is free.

Six hours of cluster life, gossiped between five nodes, has to fit in a few
seconds of wall time. If it does not, exploring rare timing windows by brute
force stops being affordable and the whole approach falls apart.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from cassette.sim.env import Env
from cassette.sim.simulation import Simulation
from cassette.sim.types import NodeId, Payload
from tests.fakes import Ping

SIX_HOURS_MS = 6 * 60 * 60 * 1_000
HEARTBEAT_MS = 2_000
CLUSTER_SIZE = 5


@dataclass
class GossipNode:
    """Broadcasts on every heartbeat and counts what comes back."""

    node_id: NodeId
    peers: list[NodeId] = field(default_factory=list)
    received: int = 0

    def start(self, env: Env) -> None:
        env.set_timer(HEARTBEAT_MS, "heartbeat")

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        self.received += 1

    def on_timer(self, env: Env, tag: str) -> None:
        for peer in self.peers:
            env.send(peer, Ping("beat"))
        env.set_timer(HEARTBEAT_MS, "heartbeat")

    def on_crash(self) -> None:
        return

    def on_restart(self, env: Env) -> None:
        return


@pytest.mark.slow
def test_six_hours_of_gossip_costs_seconds_of_wall_time() -> None:
    sim = Simulation(seed=8421)
    nodes = [GossipNode(node_id=i) for i in range(CLUSTER_SIZE)]
    for node in nodes:
        node.peers = [peer.node_id for peer in nodes if peer.node_id != node.node_id]
        sim.add_node(node)
    for node in nodes:
        node.start(sim.env_for(node.node_id))

    started = time.perf_counter()
    delivered = sim.run(until_ms=SIX_HOURS_MS)
    elapsed = time.perf_counter() - started

    assert sim.clock.now >= SIX_HOURS_MS - HEARTBEAT_MS
    assert delivered > 200_000
    assert sum(node.received for node in nodes) == delivered - CLUSTER_SIZE * (
        SIX_HOURS_MS // HEARTBEAT_MS
    )
    assert elapsed < 5.0, f"six simulated hours took {elapsed:.1f}s of wall time"
