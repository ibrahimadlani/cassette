"""A replica: a store, and a coordinator for other people's requests.

Any replica can coordinate. There is no leader, no election and no log — a
client picks a node, that node assembles a quorum, and the quorum rule is the
only thing standing between the cluster and an inconsistency.

The split that matters here is durable versus volatile. `_store` survives a
crash; `_rounds` does not, because the process that was tracking those rounds
is gone. Getting that boundary wrong is one of the easiest ways to build a
store that looks correct until a node reboots.
"""

from __future__ import annotations

from cassette.kv.config import StoreConfig
from cassette.kv.messages import Key, ReadReply, ReadRequest, WriteAck, WriteRequest
from cassette.kv.version import ABSENT, Stored
from cassette.sim.env import Env
from cassette.sim.types import NodeId, Payload


class Replica:
    """One node of the cluster."""

    def __init__(self, node_id: NodeId, config: StoreConfig | None = None) -> None:
        self.node_id = node_id
        self.config = StoreConfig() if config is None else config
        self._store: dict[Key, Stored] = {}

    # -- inspection -----------------------------------------------------

    def stored(self, key: Key) -> Stored:
        """What this replica holds for `key`, durable state only."""
        return self._store.get(key, ABSENT)

    @property
    def keys(self) -> list[Key]:
        """Every key this replica knows about, sorted."""
        return sorted(self._store)

    # -- the storage role -----------------------------------------------

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        """Route an incoming message to its handler."""
        match msg:
            case ReadRequest():
                self._on_read_request(env, sender, msg)
            case WriteRequest():
                self._on_write_request(env, sender, msg)
            case _:
                return

    def _on_read_request(self, env: Env, sender: NodeId, msg: ReadRequest) -> None:
        held = self.stored(msg.key)
        env.send(sender, ReadReply(msg.req, msg.key, held.value, held.version))

    def _on_write_request(self, env: Env, sender: NodeId, msg: WriteRequest) -> None:
        held = self.stored(msg.key)
        if msg.version > held.version:
            self._store[msg.key] = Stored(msg.value, msg.version)
        # Acknowledged either way. A replica that already holds something newer
        # has still seen this write, and refusing to say so would stall a
        # coordinator that has done nothing wrong.
        env.send(sender, WriteAck(msg.req, msg.key, msg.version))

    # -- lifecycle ------------------------------------------------------

    def on_timer(self, env: Env, tag: str) -> None:
        """No timers yet; the coordinator role adds them."""
        return

    def on_crash(self) -> None:
        """Lose everything volatile. `_store` is what a real node would have on disk."""
        return

    def on_restart(self, env: Env) -> None:
        """Come back up with the durable store intact."""
        return
