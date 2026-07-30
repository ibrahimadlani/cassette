"""The message bus, and the faults that live on the wire.

Every message a node sends passes through here, gets an identifier, and is
handed back to the scheduler as a future delivery. Nothing is ever delivered
synchronously, even between two healthy nodes: latency is drawn from the
seeded source, so reordering is the normal case rather than a fault that has
to be switched on.

Reachability is evaluated at delivery time, not at send time. A message that
leaves before a partition opens and arrives after it has is therefore dropped,
which is what a broken link actually does to a packet already in flight.
"""

from __future__ import annotations

from cassette.sim.events import DeliverMessage
from cassette.sim.faults import FaultConfig
from cassette.sim.observer import NullObserver, Observer
from cassette.sim.rng import Rng
from cassette.sim.scheduler import Scheduler
from cassette.sim.types import NodeId, Payload

PartitionGroups = tuple[frozenset[NodeId], ...]


class Network:
    """An in-memory bus with variable latency, loss, duplication and partitions."""

    __slots__ = ("_config", "_next_msg_id", "_observer", "_partition", "_rng", "_scheduler")

    def __init__(
        self,
        scheduler: Scheduler,
        rng: Rng,
        config: FaultConfig | None = None,
        observer: Observer | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._rng = rng
        self._config = config or FaultConfig()
        self._observer = observer or NullObserver()
        self._partition: PartitionGroups | None = None
        self._next_msg_id = 0

    # -- sending --------------------------------------------------------

    def send(self, sender: NodeId, recipient: NodeId, msg: Payload) -> int:
        """Queue `msg` for delivery and return its identifier.

        The identifier is a plain counter rather than a uuid: it has to be
        reproducible, and it has to be readable in a trace. Both dice are
        rolled unconditionally so that switching a fault off does not shift
        every decision taken after it.
        """
        msg_id = self._next_msg_id
        self._next_msg_id += 1

        lost = self._rng.chance(self._config.drop_rate)
        doubled = self._rng.chance(self._config.dup_rate)

        if lost:
            self._observer.record(
                "msg_drop", id=msg_id, sender=sender, to=recipient, kind=msg.kind, reason="loss"
            )
            return msg_id

        copies = 2 if doubled else 1
        for _ in range(copies):
            delay_ms = self._rng.randint(*self._config.latency_ms)
            self._scheduler.schedule(delay_ms, recipient, DeliverMessage(sender, msg, msg_id))

        self._observer.record(
            "msg_send",
            id=msg_id,
            sender=sender,
            to=recipient,
            kind=msg.kind,
            body=msg.to_json(),
            copies=copies,
        )
        return msg_id

    def report_drop(self, sender: NodeId, recipient: NodeId, msg_id: int, reason: str) -> None:
        """Note a message that died after it was already on the wire."""
        self._observer.record("msg_drop", id=msg_id, sender=sender, to=recipient, reason=reason)

    # -- partitions -----------------------------------------------------

    @property
    def partition(self) -> PartitionGroups | None:
        """The current split, or None when the cluster is whole."""
        return self._partition

    def partition_into(self, groups: PartitionGroups) -> None:
        """Cut the cluster so nodes only reach members of their own group."""
        if len(groups) < 2:
            raise ValueError("a partition needs at least two groups")
        self._partition = groups
        self._observer.record("partition_start", groups=[sorted(group) for group in groups])

    def heal(self) -> None:
        """Restore full connectivity. Healing a whole cluster is a no-op."""
        if self._partition is None:
            return
        self._partition = None
        self._observer.record("partition_end")

    def can_reach(self, sender: NodeId, recipient: NodeId) -> bool:
        """Whether a link exists right now between these two.

        Participants absent from every group — clients, in practice — stay
        reachable. Splitting the cluster is a statement about the replicas, and
        a client that could reach nobody would just stall without teaching the
        checker anything.
        """
        if self._partition is None:
            return True
        sender_group = self._group_of(sender)
        recipient_group = self._group_of(recipient)
        if sender_group is None or recipient_group is None:
            return True
        return sender_group == recipient_group

    def _group_of(self, node: NodeId) -> int | None:
        for index, group in enumerate(self._partition or ()):
            if node in group:
                return index
        return None
