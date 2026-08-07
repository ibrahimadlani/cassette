"""Exploring seeds by the thousand.

Each seed is an independent run, which makes this the one place in the project
where parallelism is free: whole scenarios go to separate processes, and each
process is internally single-threaded and deterministic. The seed still decides
everything; the pool only decides who computes what.

Results come back in seed order rather than as they finish. Unordered would be
marginally faster and would mean `--seeds 10000` reported a different first
failure depending on how the machine felt that afternoon, which is precisely
the property this project exists to eliminate.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from cassette.corpus import Entry
from cassette.kv.config import StoreConfig
from cassette.runner import execute
from cassette.scenario import WorkloadSpec, generate
from cassette.sim.faults import FaultConfig

CHUNK_SIZE = 16
"""Seeds handed to a worker at a time. Large enough that the queue is not the
bottleneck, small enough that a fast failure is not stuck behind slow work."""


@dataclass(frozen=True, slots=True)
class Plan:
    """The scenario template every seed is instantiated from."""

    preset: str = "standard"
    store: StoreConfig = field(default_factory=StoreConfig)
    faults: FaultConfig = field(default_factory=FaultConfig)
    workload: WorkloadSpec = field(default_factory=WorkloadSpec)
    horizon_ms: int = 60_000

    def entry_for(self, seed: int, note: str) -> Entry:
        """The corpus line that reproduces this seed."""
        return Entry(
            seed=seed,
            preset=self.preset,
            nodes=self.store.replicas,
            read_quorum=self.store.read_quorum,
            write_quorum=self.store.write_quorum,
            clients=self.workload.clients,
            operations=self.workload.operations,
            horizon_ms=self.horizon_ms,
            note=note,
        )


@dataclass(frozen=True, slots=True)
class Finding:
    """A seed that produced a violation."""

    seed: int
    key: str | None
    operation: int | None
    explanation: str

    def __str__(self) -> str:
        return f"seed {self.seed}: {self.explanation}"


@dataclass(frozen=True, slots=True)
class Report:
    """What a fuzzing session found."""

    explored: int
    findings: list[Finding]
    undecided: int
    elapsed_s: float

    @property
    def throughput(self) -> float:
        """Scenarios explored per second."""
        return self.explored / self.elapsed_s if self.elapsed_s > 0 else 0.0

    @property
    def clean(self) -> bool:
        """Whether every scenario checked out."""
        return not self.findings


def probe(task: tuple[int, Plan]) -> tuple[int, Finding | None, bool]:
    """Run one seed and say what happened.

    Top-level, and taking a single picklable argument, because this is what the
    worker processes call.

    Returns:
        The seed, a finding if it violated linearizability, and whether the
        checker ran out of budget before it could decide.
    """
    seed, plan = task
    scenario = generate(
        seed=seed,
        store=plan.store,
        faults=plan.faults,
        workload=plan.workload,
        horizon_ms=plan.horizon_ms,
    )
    verdict = execute(scenario, record=False).verdict
    if verdict is None or verdict.linearizable:
        return seed, None, False
    if verdict.exhausted:
        return seed, None, True
    return (
        seed,
        Finding(
            seed=seed,
            key=verdict.key,
            operation=verdict.operation,
            explanation=verdict.explanation or "not linearizable",
        ),
        False,
    )


def fuzz(
    seeds: Iterable[int],
    plan: Plan | None = None,
    *,
    workers: int = 1,
    stop_at_first: bool = True,
    on_result: Callable[[int, Finding | None], None] | None = None,
) -> Report:
    """Explore `seeds` and report what broke."""
    plan = Plan() if plan is None else plan
    tasks = [(seed, plan) for seed in seeds]
    started = time.perf_counter()

    findings: list[Finding] = []
    undecided = 0
    explored = 0

    for seed, finding, was_undecided in _results(tasks, workers):
        explored += 1
        undecided += int(was_undecided)
        if finding is not None:
            findings.append(finding)
        if on_result is not None:
            on_result(seed, finding)
        if finding is not None and stop_at_first:
            break

    return Report(
        explored=explored,
        findings=findings,
        undecided=undecided,
        elapsed_s=time.perf_counter() - started,
    )


def _results(
    tasks: list[tuple[int, Plan]], workers: int
) -> Iterator[tuple[int, Finding | None, bool]]:
    if workers <= 1 or len(tasks) < CHUNK_SIZE:
        yield from (probe(task) for task in tasks)
        return
    with mp.Pool(processes=workers) as pool:
        # imap, not imap_unordered: the first failure reported must depend on
        # the seeds, not on which worker happened to finish first.
        yield from pool.imap(probe, tasks, chunksize=CHUNK_SIZE)
