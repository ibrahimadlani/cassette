"""Is this history linearizable?

A history is linearizable when its operations can be laid out in some total
order such that (a) the order respects real time — anything that returned
before another was invoked comes first — and (b) running that order against the
specification produces exactly the results the clients saw.

The search is the one Wing and Gong describe: pick an operation that is allowed
to go next, apply it, recurse, backtrack. Two things keep it affordable.

**Memoisation.** Two different orders that place the same set of operations and
leave the register holding the same value are indistinguishable from there on.
Keying on `(placed, state)` collapses a factorial search into something that
finishes.

**P-compositionality.** A history over independent objects is linearizable
exactly when its restriction to each object is. Keys are independent, so a
twenty-four operation history over two keys is two twelve-operation searches
rather than one twenty-four-operation search — and the difference between those
is the difference between milliseconds and never.

The third thing is a budget. An adversarial history can still blow up, and a
checker that hangs is worse than one that says "I could not tell". When the
budget runs out the verdict is `exhausted`, and an exhausted verdict is never
reported as a violation: a tool that cries wolf is not usable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from cassette.checker.history import UNKNOWN, History, Operation
from cassette.checker.model import ABSENT, apply, matches
from cassette.kv.messages import Key, Value
from cassette.sim.types import JsonDict

DEFAULT_BUDGET = 200_000
"""States explored per key before the search gives up."""


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the checker concluded."""

    linearizable: bool
    key: Key | None = None
    operation: int | None = None
    explanation: str | None = None
    checked_operations: int = 0
    exhausted: bool = False

    @property
    def violated(self) -> bool:
        """Whether this is a genuine counterexample rather than an unclear answer."""
        return not self.linearizable and not self.exhausted

    def to_json(self) -> JsonDict:
        """Render for the trace envelope."""
        return {
            "linearizable": self.linearizable,
            "key": self.key,
            "operation": self.operation,
            "explanation": self.explanation,
            "checked_operations": self.checked_operations,
            "exhausted": self.exhausted,
        }

    def __str__(self) -> str:
        if self.exhausted:
            return f"undecided: search budget exhausted on key {self.key!r}"
        if self.linearizable:
            return f"linearizable ({self.checked_operations} operations)"
        return f"not linearizable: {self.explanation}"


def check(history: History, budget: int = DEFAULT_BUDGET) -> Verdict:
    """Check every key independently and return the first problem found."""
    total = len(history)
    for key, operations in history.by_key().items():
        verdict = check_key(key, operations, budget)
        if not verdict.linearizable:
            return Verdict(
                linearizable=False,
                key=key,
                operation=verdict.operation,
                explanation=verdict.explanation,
                checked_operations=total,
                exhausted=verdict.exhausted,
            )
    return Verdict(linearizable=True, checked_operations=total)


def check_key(key: Key, operations: list[Operation], budget: int = DEFAULT_BUDGET) -> Verdict:
    """Check the operations on one key."""
    outcome = _search(operations, budget)
    if outcome is _EXHAUSTED:
        return Verdict(linearizable=False, key=key, exhausted=True, explanation="budget exhausted")
    if outcome:
        return Verdict(linearizable=True, key=key, checked_operations=len(operations))

    culprit = _blame(operations, budget)
    return Verdict(
        linearizable=False,
        key=key,
        operation=None if culprit is None else culprit.index,
        explanation=_explain(key, culprit),
        checked_operations=len(operations),
    )


class _Exhausted:
    """Sentinel: the search ran out of budget rather than out of options."""

    def __bool__(self) -> bool:
        return False


_EXHAUSTED = _Exhausted()


def _search(operations: list[Operation], budget: int) -> bool | _Exhausted:
    """Try to lay `operations` out in a legal total order."""
    required = frozenset(op.index for op in operations if op.completed)
    if not required:
        return True

    by_index = {op.index: op for op in operations}
    order = sorted(by_index)
    seen: set[tuple[frozenset[int], Value]] = set()
    spent = 0

    def candidates(placed: frozenset[int]) -> list[Operation]:
        pending = [by_index[index] for index in order if index not in placed]
        return [
            op
            for op in pending
            if not any(other.precedes(op) for other in pending if other.index != op.index)
        ]

    def walk(placed: frozenset[int], state: Value) -> bool | _Exhausted:
        nonlocal spent
        if required <= placed:
            return True
        spent += 1
        if spent > budget:
            return _EXHAUSTED
        memo = (placed, state)
        if memo in seen:
            return False
        seen.add(memo)
        for op in candidates(placed):
            next_state, produced = apply(state, op)
            if not matches(op, produced):
                continue
            result = walk(placed | {op.index}, next_state)
            if result is _EXHAUSTED:
                return _EXHAUSTED
            if result:
                return True
        return False

    return walk(frozenset(), ABSENT)


def _blame(operations: list[Operation], budget: int) -> Operation | None:
    """Find the first completed operation that cannot be explained.

    Linearizability is closed under cutting a history at a point in time, so
    replaying with a later and later cut and stopping at the first cut that
    fails names the operation that broke it. That is a much more useful answer
    than "somewhere in these twenty-four operations".
    """
    completions = sorted(
        (op for op in operations if op.completed), key=lambda op: (op.returned_ms, op.index)
    )
    for op in completions:
        if not _search(_cut_at(operations, op.returned_ms), budget):
            return op
    return None


def _cut_at(operations: list[Operation], at_ms: int) -> list[Operation]:
    """The history as it stood at `at_ms`: later returns become unknown."""
    cut: list[Operation] = []
    for op in operations:
        if op.invoked_ms > at_ms:
            continue
        if op.completed and op.returned_ms <= at_ms:
            cut.append(op)
        else:
            cut.append(replace(op, outcome=UNKNOWN))
    return cut


def _explain(key: Key, culprit: Operation | None) -> str:
    if culprit is None:
        return f"no legal ordering exists for key {key!r}"
    return f"{culprit.describe()} cannot be placed in any legal order"
