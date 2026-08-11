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

from dataclasses import dataclass, field

from cassette.kv.config import StoreConfig
from cassette.kv.messages import (
    ClientReply,
    ClientRequest,
    Key,
    ReadReply,
    ReadRequest,
    Value,
    WriteAck,
    WriteRequest,
)
from cassette.kv.version import ABSENT, ZERO, Stored, Version
from cassette.sim.env import Env
from cassette.sim.types import NodeId, Payload

READ_OP = "read"
WRITE_OP = "write"
CAS_OP = "cas"

SWAPPED = 1
NOT_SWAPPED = 0
"""What a compare-and-swap reports back through ClientReply.value."""

READ_PHASE = "read"
WRITE_PHASE = "write"


def timer_tag(req: int) -> str:
    """The timer a coordinator arms while a round is outstanding."""
    return f"round:{req}"


@dataclass
class Round:
    """A client request this replica is coordinating. Volatile by design."""

    req: int
    client: NodeId
    op: str
    key: Key
    value: Value = None
    expected: Value = None
    phase: str = READ_PHASE
    version: Version = ZERO
    result: Value = None
    """What a read will answer once its write-back has been acknowledged."""
    replies: dict[NodeId, Stored] = field(default_factory=dict)
    acks: set[NodeId] = field(default_factory=set)

    def newest(self) -> Stored:
        """The most recent value any replica reported in phase one.

        Sorted by node id before taking the maximum, so the answer never
        depends on the order the replies happened to arrive in.
        """
        return max(
            (held for _, held in sorted(self.replies.items())),
            key=lambda held: held.version,
            default=ABSENT,
        )


class Replica:
    """One node of the cluster."""

    def __init__(self, node_id: NodeId, config: StoreConfig | None = None) -> None:
        self.node_id = node_id
        self.config = StoreConfig() if config is None else config
        self._store: dict[Key, Stored] = {}
        self._issued: dict[Key, Version] = {}
        self._rounds: dict[int, Round] = {}

    # -- inspection -----------------------------------------------------

    def stored(self, key: Key) -> Stored:
        """What this replica holds for `key`, durable state only."""
        return self._store.get(key, ABSENT)

    @property
    def keys(self) -> list[Key]:
        """Every key this replica knows about, sorted."""
        return sorted(self._store)

    @property
    def open_rounds(self) -> int:
        """How many client requests this replica is still coordinating."""
        return len(self._rounds)

    # -- routing --------------------------------------------------------

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        """Route an incoming message to its handler."""
        match msg:
            case ClientRequest():
                self._on_client_request(env, sender, msg)
            case ReadRequest():
                self._on_read_request(env, sender, msg)
            case WriteRequest():
                self._on_write_request(env, sender, msg)
            case ReadReply():
                self._on_read_reply(env, sender, msg)
            case WriteAck():
                self._on_write_ack(env, sender, msg)
            case _:
                return

    # -- the storage role -----------------------------------------------

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

    # -- the coordinator role -------------------------------------------

    def _on_client_request(self, env: Env, client: NodeId, msg: ClientRequest) -> None:
        if msg.req in self._rounds:
            return
        self._rounds[msg.req] = Round(
            req=msg.req,
            client=client,
            op=msg.op,
            key=msg.key,
            value=msg.value,
            expected=msg.expected,
        )
        self._broadcast(env, ReadRequest(msg.req, msg.key))
        env.set_timer(self.config.request_timeout_ms, timer_tag(msg.req))

    def _on_read_reply(self, env: Env, sender: NodeId, msg: ReadReply) -> None:
        round_ = self._rounds.get(msg.req)
        if round_ is None or round_.phase != READ_PHASE or round_.key != msg.key:
            return
        round_.replies[sender] = Stored(msg.value, msg.version)
        if len(round_.replies) < self.config.read_quorum:
            return
        self._on_read_quorum(env, round_)

    def _on_read_quorum(self, env: Env, round_: Round) -> None:
        newest = round_.newest()
        if round_.op == READ_OP:
            if not self.config.read_repair or newest.version == ZERO:
                self._finish(env, round_, ok=True, value=newest.value)
                return
            # Phase two of ABD. The quorum this read saw is not necessarily the
            # quorum the next read will see, so returning now can let a later
            # read observe an older value. Writing the winner back to W
            # replicas first makes what this read reports durable, and reads
            # stop going backwards.
            round_.phase = WRITE_PHASE
            round_.result = newest.value
            round_.version = newest.version
            self._broadcast(env, WriteRequest(round_.req, round_.key, newest.value, newest.version))
            env.set_timer(self.config.request_timeout_ms, timer_tag(round_.req))
            return
        if round_.op == CAS_OP and newest.value != round_.expected:
            self._finish(env, round_, ok=True, value=NOT_SWAPPED)
            return
        round_.phase = WRITE_PHASE
        round_.version = self._mint(round_.key, newest.version)
        self._broadcast(env, WriteRequest(round_.req, round_.key, round_.value, round_.version))
        # Phase two gets its own budget. A round that spent almost all of the
        # timeout gathering reads would otherwise abandon the write it has
        # already started, and abandoning a write is the worst outcome
        # available: the client is told nothing while replicas keep applying it.
        env.set_timer(self.config.request_timeout_ms, timer_tag(round_.req))

    def _mint(self, key: Key, observed: Version) -> Version:
        """A version strictly newer than anything this node has seen or issued.

        The observed maximum is not enough on its own. Two rounds this replica
        is coordinating at the same time both read the quorum before either
        writes, both see the same maximum, and both derive the same successor —
        identical stamp, different value. Replicas keep whichever arrives first
        and reject the other while still acknowledging it, so the second write
        is reported successful and is silently lost on part of the cluster.

        Remembering what this node has already issued closes it. The record is
        durable for the same reason a Raft term is: a node that forgot it
        across a restart could mint a stamp it had already used.
        """
        if not self.config.stable_versions:
            return observed.next_from(self.node_id)
        highest = max(observed, self._issued.get(key, ZERO))
        minted = highest.next_from(self.node_id)
        self._issued[key] = minted
        return minted

    def _on_write_ack(self, env: Env, sender: NodeId, msg: WriteAck) -> None:
        round_ = self._rounds.get(msg.req)
        if round_ is None or round_.phase != WRITE_PHASE or round_.version != msg.version:
            return
        round_.acks.add(sender)
        if len(round_.acks) < self.config.write_quorum:
            return
        self._finish(env, round_, ok=True, value=self._answer(round_))

    @staticmethod
    def _answer(round_: Round) -> Value:
        if round_.op == READ_OP:
            return round_.result
        if round_.op == CAS_OP:
            return SWAPPED
        return None

    def _finish(self, env: Env, round_: Round, *, ok: bool, value: Value = None) -> None:
        del self._rounds[round_.req]
        env.cancel_timer(timer_tag(round_.req))
        env.send(round_.client, ClientReply(round_.req, ok, value))

    def _broadcast(self, env: Env, msg: Payload) -> None:
        for peer in self.config.replica_ids:
            env.send(peer, msg)

    # -- lifecycle ------------------------------------------------------

    def on_timer(self, env: Env, tag: str) -> None:
        """Give up on a round that never reached its quorum.

        The client is told the request failed, which is weaker than it sounds:
        a write that could not gather W acknowledgements may still have reached
        some replicas, and may still surface later. The history records the
        outcome as unknown for exactly that reason.
        """
        _, _, raw = tag.partition(":")
        round_ = self._rounds.get(int(raw))
        if round_ is not None:
            self._finish(env, round_, ok=False)

    def on_crash(self) -> None:
        """Lose everything volatile.

        `_store` and `_issued` are what a real node would have on disk. Rounds
        are not: the process tracking them is gone.
        """
        self._rounds.clear()

    def on_restart(self, env: Env) -> None:
        """Come back up with the durable store intact and no memory of any round."""
        return
