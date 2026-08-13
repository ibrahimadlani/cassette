"""Pre-generate the traces the web replayer serves.

The replayer never runs the simulator. That was a deliberate decision — see
ADR-0005 — and the consequence is this script: a small, hand-picked catalogue
of runs, exported once and committed, so the demo is a static site with no
server, no WebAssembly and no build-time Python.

Run it with `make traces` after anything that changes the trace format.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path

from cassette.kv.config import StoreConfig
from cassette.runner import execute
from cassette.scenario import HARSH, QUIET, STANDARD, Scenario, WorkloadSpec, generate
from cassette.shrink import shrink
from cassette.sim.faults import FaultConfig

OUTPUT = Path("web/public/traces")


@dataclass(frozen=True, slots=True)
class Exhibit:
    """One entry in the catalogue."""

    slug: str
    title: str
    blurb: str
    scenario: Scenario
    shrink_first: bool = False


def broken(store: StoreConfig | None = None) -> StoreConfig:
    """A store with both documented defects switched on."""
    return replace(store or StoreConfig(), stable_versions=False, read_repair=False)


def catalogue() -> list[Exhibit]:
    """The runs worth looking at, in the order the demo should show them."""
    small = WorkloadSpec(clients=3, operations=6)
    return [
        Exhibit(
            slug="minimal-violation",
            title="The bug, reduced",
            blurb=(
                "Four operations, three replicas, no injected faults. Both writes go "
                "through n2 and end up with the same version stamp, so the two reads "
                "disagree about what happened."
            ),
            scenario=generate(77, store=broken(), faults=STANDARD, workload=small),
            shrink_first=True,
        ),
        Exhibit(
            slug="violation-in-the-wild",
            title="The same bug, unreduced",
            blurb=(
                "The seed the fuzzer actually reported: five replicas, three clients, "
                "eighteen operations and every fault switched on. Reproducible, and "
                "unreadable — which is what the shrinker is for."
            ),
            scenario=generate(77, store=broken(), faults=STANDARD, workload=small),
        ),
        Exhibit(
            slug="partition",
            title="A network partition",
            blurb=(
                "The cluster splits, a minority keeps accepting requests it cannot "
                "complete, and the split heals. The fixed store stays linearizable "
                "throughout."
            ),
            scenario=generate(
                8421,
                faults=FaultConfig(
                    latency_ms=(2, 60),
                    partition_rate=0.25,
                    partition_duration_ms=(600, 1_600),
                    tick_ms=200,
                ),
                workload=small,
            ),
        ),
        Exhibit(
            slug="crash-restart",
            title="Nodes crashing and coming back",
            blurb=(
                "Replicas lose their volatile state and restart. Acknowledged writes "
                "survive, because that is what makes them durable state."
            ),
            scenario=generate(
                4242,
                faults=FaultConfig(
                    latency_ms=(2, 50),
                    crash_rate=0.25,
                    crash_duration_ms=(300, 900),
                    tick_ms=200,
                ),
                workload=small,
            ),
        ),
        Exhibit(
            slug="everything-at-once",
            title="Everything at once",
            blurb=(
                "Loss, duplication, partitions, crashes, pauses and clock skew "
                "together. Still linearizable."
            ),
            scenario=generate(1234, faults=HARSH, workload=small),
        ),
        Exhibit(
            slug="healthy",
            title="A healthy cluster",
            blurb="Jitter and reordering only. What the diagram looks like when nothing is wrong.",
            scenario=generate(1, faults=QUIET, workload=small),
        ),
    ]


def build(output: Path) -> list[dict[str, object]]:
    """Write every exhibit and return the catalogue index."""
    output.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []

    for exhibit in catalogue():
        scenario = exhibit.scenario
        if exhibit.shrink_first:
            scenario = shrink(scenario).reduced

        run = execute(scenario)
        trace = run.to_trace()
        path = output / f"{exhibit.slug}.json"
        path.write_text(json.dumps(trace.to_json(), separators=(",", ":")) + "\n", encoding="utf-8")

        verdict = run.verdict
        index.append(
            {
                "slug": exhibit.slug,
                "title": exhibit.title,
                "blurb": exhibit.blurb,
                "seed": scenario.seed,
                "replicas": scenario.store.replicas,
                "operations": scenario.operation_count,
                "events": len(trace.events),
                "faulty": not scenario.store.faithful,
                "linearizable": verdict is None or verdict.linearizable,
                "bytes": path.stat().st_size,
            }
        )
        size_kb = path.stat().st_size / 1024
        print(f"  {exhibit.slug:24s} {len(trace.events):5d} events  {size_kb:6.1f} KiB")

    (output / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> None:
    """Build the catalogue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()

    print(f"writing to {arguments.output}")
    index = build(arguments.output)
    total = sum(int(str(entry["bytes"])) for entry in index)
    print(f"{len(index)} traces, {total / 1024:.0f} KiB total")


if __name__ == "__main__":
    main()
