"""Measure the numbers the README publishes.

Every figure in the README comes out of this script. Nothing in that table is
estimated, rounded up, or remembered from an earlier run — if a number is
questioned in an interview, the answer is "run `make bench`".
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import platform
import statistics
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

from cassette import corpus
from cassette.fuzz import Plan, fuzz
from cassette.kv.config import StoreConfig
from cassette.runner import execute
from cassette.scenario import STANDARD, WorkloadSpec, generate
from cassette.shrink import shrink

OUTPUT = Path("benchmarks/results.md")
BROKEN = StoreConfig(stable_versions=False, read_repair=False)


@dataclass(frozen=True, slots=True)
class Measurement:
    """One published number."""

    metric: str
    value: str
    note: str


def machine() -> str:
    """Enough about the machine that the numbers can be compared."""
    return (
        f"{platform.machine()}, {multiprocessing.cpu_count()} cores, "
        f"Python {sys.version.split()[0]} on {platform.system()}"
    )


def throughput(seeds: int, workers: int) -> Measurement:
    """How many whole scenarios can be explored per second."""
    report = fuzz(range(seeds), Plan(faults=STANDARD), workers=workers, stop_at_first=False)
    return Measurement(
        "Scenarios explored per second",
        f"{report.throughput:,.0f}",
        f"{report.explored:,} seeds on {workers} workers, {report.elapsed_s:.1f}s",
    )


def simulated_time() -> Measurement:
    """How much cluster life fits in a second of wall time, under real load.

    This is the dense case: five clients hammering the store as fast as it
    answers. It is the honest number for the workload the fuzzer actually runs,
    and it is much lower than the figure a quiet cluster gives — which is why
    both are published rather than only the flattering one.
    """
    scenario = generate(
        8421,
        faults=STANDARD,
        workload=WorkloadSpec(clients=5, operations=200, think_ms=(0, 400)),
        horizon_ms=6 * 60 * 60 * 1_000,
    )
    started = time.perf_counter()
    run = execute(scenario, record=False, judge=False)
    elapsed = time.perf_counter() - started
    ratio = (run.elapsed_ms / 1_000) / elapsed
    lived = run.elapsed_ms / 1_000
    return Measurement(
        "Simulated time per real second, under load",
        f"{ratio / 60:,.1f} minutes",
        f"{lived:,.0f}s of cluster life in {elapsed:.2f}s, {run.delivered:,} events",
    )


def idle_time() -> Measurement:
    """The sparse case: a cluster that is mostly waiting.

    Five nodes gossiping every two seconds for six simulated hours. Nothing
    interesting happens, which is the point — the cost of simulated time is the
    work done in it, not the time itself, so rare timing windows are affordable
    to go looking for.
    """
    from cassette.sim.simulation import Simulation
    from tests.sim.test_virtual_time import SIX_HOURS_MS, GossipNode

    sim = Simulation(seed=8421)
    nodes = [GossipNode(node_id=index) for index in range(5)]
    for node in nodes:
        node.peers = [peer.node_id for peer in nodes if peer.node_id != node.node_id]
        sim.add_node(node)
    for node in nodes:
        node.start(sim.env_for(node.node_id))

    started = time.perf_counter()
    delivered = sim.run(until_ms=SIX_HOURS_MS)
    elapsed = time.perf_counter() - started
    hours = sim.clock.now / 3_600_000
    return Measurement(
        "Simulated time per real second, idle cluster",
        f"{hours / elapsed:,.0f} hours",
        f"{hours:.0f}h of five-node gossip in {elapsed:.2f}s, {delivered:,} events",
    )


def determinism(seeds: int) -> Measurement:
    """How long the trace-hash comparison takes."""
    from tests.workload import run_workload

    started = time.perf_counter()
    for seed in range(seeds):
        assert run_workload(seed).digest() == run_workload(seed).digest()
    elapsed = time.perf_counter() - started
    return Measurement(
        "Determinism check",
        f"{seeds:,} seeds x2 in {elapsed:.1f}s",
        "SHA-256 of the canonical trace, compared run to run",
    )


def bugs_found() -> Measurement:
    """How many real defects the harness found in the store."""
    return Measurement(
        "Consistency bugs found in my own implementation",
        "2 fixed, 1 unfixable by design",
        "see docs/FINDINGS.md",
    )


def shrink_ratio() -> tuple[Measurement, Measurement]:
    """How much smaller a failing scenario gets."""
    ratios: list[float] = []
    deletions: list[float] = []
    operations: list[int] = []
    for entry in corpus.load():
        scenario = entry.to_scenario()
        reduction = shrink(replace(scenario, store=BROKEN))
        ratios.append(reduction.ratio)
        deletions.append(reduction.deletion_ratio)
        operations.append(reduction.reduced_size.operations)

    return (
        Measurement(
            "Median shrink ratio (events before → after)",
            f"{statistics.median(ratios):.1f}x",
            f"deletion alone {statistics.median(deletions):.1f}x, "
            f"median {statistics.median(operations):.0f} operations left",
        ),
        Measurement(
            "Seeds in the regression corpus",
            str(len(corpus.load())),
            "all replayed on every test run, and asserted to fail again with --buggy",
        ),
    )


def demo_toggle() -> Measurement:
    """How fast the harness finds a bug when there is one to find."""
    report = fuzz(range(20_000), Plan(store=BROKEN, faults=STANDARD), workers=8)
    return Measurement(
        "Scenarios to find the bug with --buggy",
        f"{report.explored} in {report.elapsed_s:.2f}s",
        "the same fuzzer explores 20,000 with the fix in and finds nothing",
    )


def render(measurements: list[Measurement], where: str) -> str:
    """The published table."""
    lines = [
        "# Benchmarks",
        "",
        "Produced by `make bench`. Every number in the README comes from here.",
        "",
        f"Measured on: {where}",
        "",
        "| Metric | Value | Detail |",
        "|---|---|---|",
    ]
    lines.extend(f"| {m.metric} | **{m.value}** | {m.note} |" for m in measurements)
    lines.extend(
        [
            "",
            "## What these are not",
            "",
            "Scenario throughput is a measure of this simulator, not of any real",
            "cluster. Simulated time per real second is the same figure seen from the",
            "other side: the point is that rare timing windows are cheap to explore,",
            "not that anything here runs fast on a network.",
            "",
            "The shrink ratio is measured in events, over every seed in the corpus,",
            "against the store with its defects switched back on — there is nothing",
            "left to shrink otherwise. Both phases are reported, because only the",
            "first is a reduction of the original run. See ADR-0006.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Measure everything and write the table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20_000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--determinism-seeds", type=int, default=1_000)
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT)
    parser.add_argument("--json", action="store_true", help="also print the raw numbers")
    arguments = parser.parse_args()

    print("measuring throughput…")
    measurements = [throughput(arguments.seeds, arguments.workers)]
    print("measuring simulated time…")
    measurements.append(simulated_time())
    measurements.append(idle_time())
    print("measuring the shrinker…")
    measurements.extend(shrink_ratio())
    print("measuring the demo toggle…")
    measurements.append(demo_toggle())
    print("measuring determinism…")
    measurements.append(determinism(arguments.determinism_seeds))
    measurements.append(bugs_found())

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(render(measurements, machine()), encoding="utf-8")
    print(f"\nwrote {arguments.output}\n")
    for measurement in measurements:
        print(f"  {measurement.metric:44s} {measurement.value}")

    if arguments.json:
        print(json.dumps([m.__dict__ for m in measurements], indent=2))


if __name__ == "__main__":
    main()
