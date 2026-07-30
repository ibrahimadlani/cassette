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


@dataclass(frozen=True, slots=True)
class StartPartition:
    """Cut the cluster into groups that cannot see each other."""

    groups: tuple[frozenset[NodeId], ...]


@dataclass(frozen=True, slots=True)
class HealPartition:
    """Put the cluster back together."""


Action: TypeAlias = DeliverMessage | FireTimer | StartPartition | HealPartition

CONTROL: NodeId = -1
"""The pseudo-node that owns fault events. No participant may claim this id."""


@dataclass(frozen=True, slots=True)
class Event:
    """A scheduled action, stamped with the ordering key it was queued under."""

    time_ms: int
    seq: int
    node: NodeId
    action: Action
