"""Delta debugging over a failing scenario.

A seed that fails tells you almost nothing. Four hundred events, five replicas,
twenty-four operations, three injected faults, and somewhere in there a reason.
The seed is a perfect reproduction and a useless explanation.

So: take things away and see whether it still breaks.

The scenario is a list of lists — client operations, injected faults — and
every reduction is the same move. Try without this piece. If the violation
survives, the piece was not load-bearing and is gone for good. Loop until
nothing more can be removed.

## Why this is a search and not a derivation

The predicate is not monotone. Deleting an operation changes how many messages
exist, which changes every latency draw after it, which changes the run. A
scenario with one operation removed is not the original minus an operation; it
is a different run that happens to be smaller.

That is fine, and it is worth being explicit about rather than glossing over.
The shrinker does not claim to isolate the cause of *this* failure. It claims
to find the smallest scenario it can that still fails the same way — same key,
same shape of violation. In practice that is enough to see the mechanism,
which is the entire point.

Two things stop it wandering. Every candidate is verified before it is
accepted, so the result is always a real failure. And the search is bounded by
a budget of attempts, keeping the best it has found, because a shrinker that
runs forever gets switched off.

## Why deletion alone is not enough

Deletion stalls around a third of the original size, and the reason is worth
stating plainly: the bug needs two operations to overlap, and whether they
overlap depends on the load around them. Delete the surrounding traffic and the
two rounds no longer collide. There is no sequence of deletions from a large
random scenario that lands on the two-writer case, because the two-writer case
is not a subset of it — it is a different arrangement.

So there is a second phase. Once deletion stops making progress, the shrinker
searches directly over small scenario shapes — three replicas, two or three
clients, a handful of operations, all on the key that failed — and keeps the
first that fails the same way. That is not a reduction of the original run and
is never reported as one: `Reduction` carries both numbers, what deletion
achieved and what the search found, so the two are never confused.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

from cassette.checker.linear import Verdict
from cassette.kv.client import PlannedOp
from cassette.kv.config import StoreConfig
from cassette.kv.messages import Key
from cassette.runner import Run, execute
from cassette.scenario import Scenario, WorkloadSpec, generate
from cassette.sim.faults import InjectedFault

DEFAULT_BUDGET = 3_000
"""Candidate scenarios evaluated before the search gives up."""

SEARCH_SEEDS = 150
"""Seeds tried per shape in the second phase."""


@dataclass(frozen=True, slots=True)
class Size:
    """How big a scenario is, in the dimensions that matter to a reader."""

    replicas: int
    clients: int
    operations: int
    faults: int
    events: int

    @property
    def weight(self) -> int:
        """A single number to minimise.

        Operations are weighted heaviest because they are what a reader has to
        hold in their head. Events are the tie-break: between two scenarios
        with the same shape, the quieter one is easier to follow.
        """
        return (
            self.operations * 100
            + self.faults * 50
            + self.clients * 20
            + self.replicas * 10
            + self.events
        )

    def __str__(self) -> str:
        return (
            f"{self.events} events, {self.replicas} replicas, "
            f"{self.clients} clients, {self.operations} operations, "
            f"{self.faults} injected faults"
        )


@dataclass(frozen=True, slots=True)
class Reduction:
    """The before and after of a shrinking run."""

    original: Scenario
    original_size: Size
    deleted_size: Size
    reduced: Scenario
    reduced_size: Size
    verdict: Verdict
    candidates: int
    rebuilt: bool
    """Whether the final scenario came from the search phase rather than deletion."""

    @property
    def ratio(self) -> float:
        """How many times smaller the scenario got, counted in events."""
        return self._ratio(self.reduced_size)

    @property
    def deletion_ratio(self) -> float:
        """How far deletion alone got, before the search phase."""
        return self._ratio(self.deleted_size)

    def _ratio(self, size: Size) -> float:
        return self.original_size.events / max(size.events, 1)


def _size(run: Run) -> Size:
    scenario = run.scenario
    return Size(
        replicas=scenario.store.replicas,
        clients=len(scenario.plans),
        operations=scenario.operation_count,
        faults=len(run.schedule),
        events=run.delivered,
    )


def _fails_the_same_way(run: Run, like: Verdict) -> bool:
    """Whether this run reproduces the failure we are chasing.

    Same key, and a genuine violation rather than an undecided search. Not the
    same operation index — indices move as operations are deleted, and
    insisting on them would reject every useful reduction.
    """
    verdict = run.verdict
    return verdict is not None and verdict.violated and verdict.key == like.key


def shrink(scenario: Scenario, budget: int = DEFAULT_BUDGET) -> Reduction:
    """Reduce `scenario` to the smallest failing version this can find.

    Raises:
        ValueError: if the scenario does not actually fail.
    """
    original = execute(scenario, record=False)
    if not original.violated:
        raise ValueError("nothing to shrink: this scenario is linearizable")
    assert original.verdict is not None

    target = original.verdict
    best = original.pinned()
    best_run = execute(best, record=False)
    best_size = _size(best_run)
    spent = 0

    def accept(candidate: Scenario) -> bool:
        nonlocal best, best_run, best_size, spent
        if spent >= budget:
            return False
        spent += 1
        run = execute(candidate, record=False)
        if not _fails_the_same_way(run, target):
            return False
        size = _size(run)
        if size.weight >= best_size.weight:
            return False
        best, best_run, best_size = candidate, run, size
        return True

    moves = (
        _only_the_failing_key,
        _fewer_faults,
        _fewer_operations,
        _fewer_clients,
        _smaller_cluster,
        _no_thinking,
        _plainer_values,
    )
    changed = True
    while changed and spent < budget:
        changed = False
        for produce in moves:
            for candidate in produce(best, target.key):
                if accept(candidate):
                    changed = True
                    break

    deleted_size = best_size
    rebuilt = False
    for candidate in _small_shapes(target.key, scenario):
        if spent >= budget:
            break
        if accept(candidate):
            # Shapes are produced smallest first, so the first one that fails is
            # the smallest one that does. Nothing later can beat it.
            rebuilt = True
            break

    # Pin whatever survived. A scenario handed to a user, a corpus or the web
    # replayer should carry its faults explicitly, so that nothing about it
    # still depends on an adversary deciding at run time.
    pinned = best_run.pinned()
    pinned_run = execute(pinned, record=False)
    if _fails_the_same_way(pinned_run, target):
        best, best_run = pinned, pinned_run

    assert best_run.verdict is not None
    return Reduction(
        original=scenario,
        original_size=_size(original),
        deleted_size=deleted_size,
        reduced=best,
        reduced_size=best_size,
        verdict=best_run.verdict,
        candidates=spent,
        rebuilt=rebuilt,
    )


# -- the moves ------------------------------------------------------------


def _only_the_failing_key(scenario: Scenario, key: Key | None) -> list[Scenario]:
    """Throw away every operation on a key that is not the one that broke.

    Not a guess. Linearizability is compositional over independent objects,
    so a history is linearizable exactly when its restriction to each key
    is — operations on other keys cannot be the reason. Usually the single
    largest reduction available, and the only one that is a theorem rather
    than an experiment.
    """
    if key is None:
        return []
    plans = tuple(tuple(op for op in plan if op.key == key) for plan in scenario.plans)
    if plans == scenario.plans:
        return []
    return [replace(scenario, plans=plans)]


def _no_thinking(scenario: Scenario, key: Key | None) -> list[Scenario]:
    """Remove the pauses between operations. Shorter runs, tighter overlap."""
    plans = tuple(tuple(replace(op, delay_ms=0) for op in plan) for plan in scenario.plans)
    return [] if plans == scenario.plans else [replace(scenario, plans=plans)]


def _plainer_values(scenario: Scenario, key: Key | None) -> list[Scenario]:
    """Renumber the written values 1, 2, 3.

    Purely cosmetic, and worth a candidate: "writes x=1 then x=2" reads
    better on a slide than "writes x=7 then x=3".
    """
    seen: dict[int, int] = {}
    for plan in scenario.plans:
        for op in plan:
            if op.argument is not None and op.argument not in seen:
                seen[op.argument] = len(seen) + 1
    if not seen or all(before == after for before, after in seen.items()):
        return []
    plans = tuple(
        tuple(op if op.argument is None else replace(op, argument=seen[op.argument]) for op in plan)
        for plan in scenario.plans
    )
    return [replace(scenario, plans=plans)]


def _fewer_faults(scenario: Scenario, key: Key | None = None) -> list[Scenario]:
    """Drop injected faults, halves first, then one at a time."""
    schedule = list(scenario.schedule or ())
    if not schedule:
        return []
    candidates = [replace(scenario, schedule=())]
    if len(schedule) > 2:
        middle = len(schedule) // 2
        candidates.append(replace(scenario, schedule=tuple(schedule[:middle])))
        candidates.append(replace(scenario, schedule=tuple(schedule[middle:])))
    candidates.extend(
        replace(scenario, schedule=tuple(schedule[:index] + schedule[index + 1 :]))
        for index in range(len(schedule))
    )
    return candidates


def _fewer_operations(scenario: Scenario, key: Key | None = None) -> list[Scenario]:
    """Drop client operations, halves first, then one at a time."""
    candidates: list[Scenario] = []
    for client, plan in enumerate(scenario.plans):
        if len(plan) > 2:
            middle = len(plan) // 2
            candidates.append(_with_plan(scenario, client, plan[:middle]))
            candidates.append(_with_plan(scenario, client, plan[middle:]))
        candidates.extend(
            _with_plan(scenario, client, plan[:index] + plan[index + 1 :])
            for index in range(len(plan))
        )
    return candidates


def _fewer_clients(scenario: Scenario, key: Key | None = None) -> list[Scenario]:
    """Drop whole clients, emptied ones first."""
    plans = scenario.plans
    if len(plans) <= 1:
        return []
    empty = tuple(plan for plan in plans if plan)
    candidates = [] if empty == plans else [replace(scenario, plans=empty)]
    candidates.extend(
        replace(scenario, plans=plans[:index] + plans[index + 1 :]) for index in range(len(plans))
    )
    return candidates


def _smaller_cluster(scenario: Scenario, key: Key | None = None) -> list[Scenario]:
    """Try a smaller cluster, keeping the quorum rule intact.

    Three replicas with R=W=2 is the smallest configuration where quorums still
    overlap, and a bug that survives down to three is much easier to draw.
    """
    store = scenario.store
    candidates: list[Scenario] = []
    for size in range(3, store.replicas):
        majority = size // 2 + 1
        smaller = StoreConfig(
            replicas=size,
            read_quorum=majority,
            write_quorum=majority,
            request_timeout_ms=store.request_timeout_ms,
        )
        candidates.append(
            replace(
                scenario,
                store=smaller,
                plans=tuple(tuple(_rehome(op, size) for op in plan) for plan in scenario.plans),
                schedule=_confine(scenario.schedule, size),
            )
        )
    return candidates


def _with_plan(scenario: Scenario, client: int, plan: tuple[PlannedOp, ...]) -> Scenario:
    plans = list(scenario.plans)
    plans[client] = plan
    return replace(scenario, plans=tuple(plans))


def _rehome(op: PlannedOp, replicas: int) -> PlannedOp:
    """Point an operation at a coordinator that still exists."""
    return replace(op, coordinator=op.coordinator % replicas)


def _confine(
    schedule: tuple[InjectedFault, ...] | None, replicas: int
) -> tuple[InjectedFault, ...] | None:
    """Drop faults aimed at replicas the smaller cluster no longer has."""
    if schedule is None:
        return None
    kept = []
    for fault in schedule:
        targets = tuple(node for node in fault.targets if node < replicas)
        if targets:
            kept.append(replace(fault, targets=targets))
    return tuple(kept)


def _small_shapes(key: Key | None, like: Scenario) -> Iterator[Scenario]:
    """Candidate scenarios built from scratch, smallest first.

    The second phase. Deletion cannot reach the two-writer case from a large
    random scenario, because the two-writer case is not contained in one — the
    operations have to be arranged, not merely selected. So this arranges them,
    smallest shape first, and lets `accept` do the verifying.
    """
    if key is None:
        return
    store = StoreConfig(
        replicas=3, read_quorum=2, write_quorum=2, request_timeout_ms=like.store.request_timeout_ms
    )
    quiet = like.faults.without_faults()
    # How wide the jitter is decides whether two rounds overlap at all, so it is
    # part of the shape rather than a detail to inherit.
    profiles = _unique(quiet.latency_ms, (1, 20), (1, 40))

    for operations in (2, 3, 4):
        for clients in (2, 3):
            for latency in profiles:
                for seed in range(SEARCH_SEEDS):
                    yield generate(
                        seed=seed,
                        store=store,
                        faults=quiet.but(latency_ms=latency),
                        workload=WorkloadSpec(
                            clients=clients,
                            operations=operations,
                            keys=(key,),
                            value_range=(1, 3),
                            read_ratio=0.5,
                            think_ms=(0, 20),
                        ),
                        horizon_ms=like.horizon_ms,
                    )


def _unique(*profiles: tuple[int, int]) -> list[tuple[int, int]]:
    """Keep the order, drop the repeats."""
    seen: list[tuple[int, int]] = []
    for profile in profiles:
        if profile not in seen:
            seen.append(profile)
    return seen
