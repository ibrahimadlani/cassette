"""The message bus.

Every message a node sends passes through here, gets an identifier, and is
handed back to the scheduler as a future delivery. Nothing is ever delivered
synchronously, even between two healthy nodes: latency is drawn from the
seeded source, so reordering is the normal case rather than a fault that has
to be switched on.
"""

from __future__ import annotations

from cassette.sim.events import DeliverMessage
from cassette.sim.rng import Rng
from cassette.sim.scheduler import Scheduler
from cassette.sim.types import NodeId, Payload


class Network:
    """An in-memory bus with variable latency."""

    __slots__ = ("_latency_ms", "_next_msg_id", "_rng", "_scheduler")

    def __init__(
        self,
        scheduler: Scheduler,
        rng: Rng,
        latency_ms: tuple[int, int] = (1, 20),
    ) -> None:
        low, high = latency_ms
        if low < 0:
            raise ValueError("latency cannot be negative")
        if high < low:
            raise ValueError(f"latency range {latency_ms} is inverted")
        self._scheduler = scheduler
        self._rng = rng
        self._latency_ms = latency_ms
        self._next_msg_id = 0

    def send(self, sender: NodeId, recipient: NodeId, msg: Payload) -> int:
        """Queue `msg` for delivery and return its identifier.

        The identifier is a plain counter rather than a uuid: it has to be
        reproducible, and it has to be readable in a trace.
        """
        msg_id = self._next_msg_id
        self._next_msg_id += 1
        delay_ms = self._rng.randint(*self._latency_ms)
        self._scheduler.schedule(delay_ms, recipient, DeliverMessage(sender, msg, msg_id))
        return msg_id
