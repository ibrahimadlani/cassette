"""Version stamps, and the total order over them.

A version is `(counter, node)`. The counter is what actually orders writes; the
node id is there so that two coordinators which independently reached the same
counter still compare unequal. Without that tiebreak two concurrent writes
could look identical to a replica, and one of them would be silently discarded
with no way to tell which.

The order is total and it is arbitrary in the tie case — node 3 beats node 1
for no better reason than that 3 is larger. That is fine. What matters is that
every replica in the cluster agrees on the answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from cassette.sim.types import JsonDict, NodeId


@dataclass(frozen=True, slots=True, order=True)
class Version:
    """A last-writer-wins stamp. Ordered by counter, then by node."""

    counter: int = 0
    node: NodeId = -1

    def next_from(self, node: NodeId) -> Version:
        """The version a coordinator on `node` should use to supersede this one."""
        return Version(self.counter + 1, node)

    def to_json(self) -> list[int]:
        """A two-element list, so a trace stays readable."""
        return [self.counter, self.node]

    @classmethod
    def from_json(cls, data: list[int]) -> Version:
        """Rebuild from the trace form."""
        counter, node = data
        return cls(counter, node)

    def __str__(self) -> str:
        return f"{self.counter}.{self.node}"


ZERO = Version()
"""The version of a key nobody has written yet."""


@dataclass(frozen=True, slots=True)
class Stored:
    """What a replica keeps for one key."""

    value: int | None = None
    version: Version = ZERO

    def to_json(self) -> JsonDict:
        """Render for the trace."""
        return {"value": self.value, "version": self.version.to_json()}


ABSENT = Stored()
"""What a replica returns for a key it has never heard of."""
