"""The specification the store is judged against.

One key is one register. A read returns what is there, a write replaces it, a
compare-and-swap replaces it only if it already holds the expected value. Four
lines of truth, and the whole point of the exercise is that four lines of truth
are hard to implement across five machines and a broken network.
"""

from __future__ import annotations

from cassette.checker.history import CAS, READ, WRITE, Operation
from cassette.kv.messages import Value

SWAPPED = 1
NOT_SWAPPED = 0

ABSENT: Value = None
"""What a register holds before anybody writes to it."""


def apply(state: Value, op: Operation) -> tuple[Value, Value]:
    """Apply `op` to a register holding `state`.

    Returns:
        The new state, and what the operation should have returned.
    """
    if op.kind == READ:
        return state, state
    if op.kind == WRITE:
        return op.argument, None
    if op.kind == CAS:
        if state == op.expected:
            return op.argument, SWAPPED
        return state, NOT_SWAPPED
    raise ValueError(f"unknown operation kind {op.kind!r}")


def matches(op: Operation, produced: Value) -> bool:
    """Whether `produced` is an acceptable answer for `op`.

    An operation whose outcome is unknown accepts anything: nobody ever found
    out what it returned, so no result can contradict it.
    """
    if not op.completed:
        return True
    if op.kind == WRITE:
        return True
    return produced == op.result
