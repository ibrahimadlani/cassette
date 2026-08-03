"""A cluster plus a mailbox, for driving the store by hand from a test."""

from __future__ import annotations

from dataclasses import dataclass, field

from cassette.kv.config import StoreConfig
from cassette.kv.messages import ClientReply, ClientRequest, Key, Value
from cassette.kv.replica import Replica
from cassette.sim.env import Env
from cassette.sim.faults import PERFECT_NETWORK, FaultConfig
from cassette.sim.simulation import Simulation
from cassette.sim.types import NodeId, Payload


@dataclass
class Mailbox:
    """A stand-in client that just collects replies."""

    node_id: NodeId
    replies: list[ClientReply] = field(default_factory=list)

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        assert isinstance(msg, ClientReply)
        self.replies.append(msg)

    def on_timer(self, env: Env, tag: str) -> None:
        return

    def on_crash(self) -> None:
        return

    def on_restart(self, env: Env) -> None:
        return


class Cluster:
    """A store, a mailbox, and helpers to issue one operation at a time."""

    def __init__(
        self,
        store: StoreConfig | None = None,
        faults: FaultConfig = PERFECT_NETWORK,
        seed: int = 8421,
    ) -> None:
        self.store = StoreConfig() if store is None else store
        self.sim = Simulation(seed=seed, config=faults)
        self.replicas = [Replica(node_id, self.store) for node_id in self.store.replica_ids]
        for replica in self.replicas:
            self.sim.add_node(replica)
        self.client_id: NodeId = self.store.replicas
        self.mailbox = Mailbox(node_id=self.client_id)
        self.sim.add_node(self.mailbox)
        self._next_req = 0

    def request(self, op: str, key: Key, value: Value = None, coordinator: NodeId = 0) -> int:
        """Send one client request and return its id."""
        self._next_req += 1
        self.sim.env_for(self.client_id).send(
            coordinator, ClientRequest(self._next_req, op, key, value)
        )
        return self._next_req

    def write(self, key: Key, value: int, coordinator: NodeId = 0) -> ClientReply:
        """Write and run until the coordinator answers."""
        return self._settle(self.request("write", key, value, coordinator))

    def read(self, key: Key, coordinator: NodeId = 0) -> ClientReply:
        """Read and run until the coordinator answers."""
        return self._settle(self.request("read", key, coordinator=coordinator))

    def _settle(self, req: int) -> ClientReply:
        self.sim.run()
        for reply in self.mailbox.replies:
            if reply.req == req:
                return reply
        raise AssertionError(f"request {req} never came back")

    def holdings(self, key: Key) -> list[Value]:
        """What each replica durably holds for `key`, by node id."""
        return [replica.stored(key).value for replica in self.replicas]
