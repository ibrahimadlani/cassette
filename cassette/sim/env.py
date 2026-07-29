"""The interface a node is given, and the interface a node must offer.

This module is the whole point of the project. A replica never imports the
scheduler, the network or the clock; it receives an `Env` and can only reach
the outside world through it. Determinism then stops being a discipline the
author has to remember and becomes a property of the architecture: there is no
other door to open.

Swapping the `Env` implementation is also how the same replica code could one
day run over real sockets without a single change.
"""

from __future__ import annotations

from typing import Protocol

from cassette.sim.types import NodeId, Payload


class Env(Protocol):
    """Everything a node is allowed to do."""

    def now(self) -> int:
        """The node's current view of logical time, in milliseconds.

        Clock skew is applied here, so two nodes asked at the same instant can
        legitimately disagree.
        """

    def send(self, to: NodeId, msg: Payload) -> None:
        """Hand a message to the network.

        Delivery is best effort: the message may be delayed, reordered,
        duplicated or dropped entirely.
        """

    def set_timer(self, delay_ms: int, tag: str) -> None:
        """Ask to be woken with `tag` after `delay_ms` of logical time.

        Setting a timer that is already pending replaces it, which keeps the
        common "restart my timeout" case from piling up wakeups.
        """

    def cancel_timer(self, tag: str) -> None:
        """Drop a pending timer. Cancelling an unknown tag is a no-op."""

    def random(self) -> float:
        """Draw from the simulation's seeded source."""


class Node(Protocol):
    """Everything the simulator expects a participant to handle."""

    @property
    def node_id(self) -> NodeId:
        """This node's identifier."""

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        """React to a delivered message."""

    def on_timer(self, env: Env, tag: str) -> None:
        """React to a timer set earlier through `Env.set_timer`."""

    def on_crash(self) -> None:
        """Discard volatile state. Whatever survives here is the durable state."""

    def on_restart(self, env: Env) -> None:
        """Come back up. Timers set before the crash are gone."""
