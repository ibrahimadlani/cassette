"""The vocabulary of things the scheduler can deliver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from cassette.sim.types import NodeId, Payload


@dataclass(frozen=True, slots=True)
class DeliverMessage:
    """Hand a message that survived the network to its recipient."""

    sender: NodeId
    msg: Payload
    msg_id: int


@dataclass(frozen=True, slots=True)
class FireTimer:
    """Wake a node that asked to be called back."""

    tag: str


Action: TypeAlias = DeliverMessage | FireTimer


@dataclass(frozen=True, slots=True)
class Event:
    """A scheduled action, stamped with the ordering key it was queued under."""

    time_ms: int
    seq: int
    node: NodeId
    action: Action
