"""What the clients saw.

A history is a list of operations, each with the logical time it was invoked
and the logical time it came back. Everything the checker knows about the run
is in here — the store's internals are deliberately not, because an oracle
that inspects the implementation cannot catch the implementation being wrong.

## Operations that did not come back

Three things can happen to a request. It succeeds, and the client knows what it
got. It fails, and the client knows nothing. Or the run ends with it still in
flight, and the client will never know.

The last two are the same case, and getting it right is what separates a
checker from a source of false alarms. A write the client was told had failed
may have reached some replicas anyway, and may surface in a read minutes later.
It cannot be dropped from the history — that would make a perfectly real stale
read look like a violation. It cannot be treated as having happened either.

So an unknown operation is one the checker *may* place anywhere, or leave out
entirely, whichever lets the rest of the history make sense. It is never
allowed to force an ordering on anything, which is why its return time is
infinite rather than the moment the client gave up: replicas do not stop
applying a write because a client lost patience.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from cassette.kv.messages import Key, Value
from cassette.sim.types import JsonDict, NodeId

READ = "read"
WRITE = "write"
CAS = "cas"

OK = "ok"
UNKNOWN = "unknown"

NEVER = -1
"""The return stamp of an operation that never came back."""


@dataclass(frozen=True, slots=True)
class Operation:
    """One client-visible operation, and what became of it."""

    index: int
    client: NodeId
    kind: str
    key: Key
    argument: Value = None
    expected: Value = None
    invoked_ms: int = 0
    returned_ms: int = NEVER
    outcome: str = UNKNOWN
    result: Value = None

    @property
    def completed(self) -> bool:
        """Whether the client was told what happened."""
        return self.outcome == OK

    @property
    def bounded(self) -> bool:
        """Whether this operation can force another one to come after it.

        Only a completed operation can. An unknown one may still be landing
        somewhere, so it constrains nothing.
        """
        return self.outcome == OK and self.returned_ms != NEVER

    def precedes(self, other: Operation) -> bool:
        """Whether this operation provably finished before `other` started."""
        return self.bounded and self.returned_ms < other.invoked_ms

    def to_json(self) -> JsonDict:
        """Render for the trace."""
        return {
            "index": self.index,
            "client": self.client,
            "kind": self.kind,
            "key": self.key,
            "argument": self.argument,
            "expected": self.expected,
            "invoked": self.invoked_ms,
            "returned": self.returned_ms,
            "outcome": self.outcome,
            "result": self.result,
        }

    def describe(self) -> str:
        """One line, the way it would be written on a whiteboard."""
        who = f"client {self.client}"
        if self.kind == WRITE:
            what = f"writes {self.key}={self.argument}"
        elif self.kind == READ:
            what = f"reads {self.key}"
        else:
            what = f"cas {self.key} {self.expected} -> {self.argument}"
        if self.outcome == UNKNOWN:
            return f"{who} {what} (unknown)"
        if self.kind == READ:
            return f"{who} {what} -> {self.result}"
        if self.kind == CAS:
            return f"{who} {what} -> {'swapped' if self.result else 'refused'}"
        return f"{who} {what} -> ok"


class History:
    """Operations in invocation order, filled in as they return."""

    __slots__ = ("_operations",)

    def __init__(self) -> None:
        self._operations: list[Operation] = []

    def invoke(
        self,
        client: NodeId,
        kind: str,
        key: Key,
        at_ms: int,
        argument: Value = None,
        expected: Value = None,
    ) -> int:
        """Record that `client` started an operation. Returns its index."""
        index = len(self._operations)
        self._operations.append(
            Operation(
                index=index,
                client=client,
                kind=kind,
                key=key,
                argument=argument,
                expected=expected,
                invoked_ms=at_ms,
            )
        )
        return index

    def complete(self, index: int, at_ms: int, result: Value = None) -> None:
        """Record a successful return."""
        self._operations[index] = replace(
            self._operations[index], returned_ms=at_ms, outcome=OK, result=result
        )

    def give_up(self, index: int) -> None:
        """Record that the client will never know what happened."""
        self._operations[index] = replace(self._operations[index], outcome=UNKNOWN)

    @property
    def operations(self) -> list[Operation]:
        """Every operation, in invocation order."""
        return list(self._operations)

    @property
    def completed(self) -> list[Operation]:
        """Only the operations the client got an answer for."""
        return [op for op in self._operations if op.completed]

    def by_key(self) -> dict[Key, list[Operation]]:
        """Operations grouped by key, keys sorted.

        Linearizability is compositional over independent objects: a history is
        linearizable exactly when its restriction to each key is. Checking key
        by key turns one intractable search into several small ones.
        """
        grouped: dict[Key, list[Operation]] = {}
        for op in self._operations:
            grouped.setdefault(op.key, []).append(op)
        return {key: grouped[key] for key in sorted(grouped)}

    def to_json(self) -> list[JsonDict]:
        """Render for the trace."""
        return [op.to_json() for op in self._operations]

    def __len__(self) -> int:
        return len(self._operations)
