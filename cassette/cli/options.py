"""Shared command-line options.

Every command that runs something needs the same twenty knobs. Declaring them
once keeps `cassette run --drop-rate 0.1` and `cassette fuzz --drop-rate 0.1`
from drifting apart, which they would within a week otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import click

from cassette.kv.config import StoreConfig
from cassette.scenario import PRESETS, Scenario, WorkloadSpec, generate
from cassette.sim.faults import FaultConfig

F = TypeVar("F", bound=Callable[..., Any])


def scenario_options(command: F) -> F:
    """Attach every cluster, workload and fault option to a command."""
    options = [
        click.option(
            "--preset",
            type=click.Choice(sorted(PRESETS)),
            default="standard",
            show_default=True,
            help="Fault profile to start from.",
        ),
        click.option("--nodes", type=int, default=5, show_default=True, help="Replica count."),
        click.option("--read-quorum", type=int, default=None, help="Default: a majority."),
        click.option("--write-quorum", type=int, default=None, help="Default: a majority."),
        click.option(
            "--timeout-ms",
            type=int,
            default=400,
            show_default=True,
            help="How long a coordinator waits for a quorum.",
        ),
        click.option("--clients", type=int, default=3, show_default=True),
        click.option(
            "--ops", type=int, default=8, show_default=True, help="Operations issued per client."
        ),
        click.option("--keys", default="x,y", show_default=True, help="Comma-separated key space."),
        click.option("--read-ratio", type=float, default=0.5, show_default=True),
        click.option(
            "--cas-ratio",
            type=float,
            default=0.0,
            show_default=True,
            help="Compare-and-swap is not linearizable here; see docs/FINDINGS.md.",
        ),
        click.option(
            "--latency-ms", nargs=2, type=int, default=None, help="Min and max delivery delay."
        ),
        click.option("--drop-rate", type=float, default=None),
        click.option("--dup-rate", type=float, default=None),
        click.option("--partition-rate", type=float, default=None),
        click.option("--crash-rate", type=float, default=None),
        click.option("--pause-rate", type=float, default=None),
        click.option("--clock-skew-ms", type=int, default=None),
        click.option(
            "--buggy",
            is_flag=True,
            help="Re-enable both fixed defects. See docs/FINDINGS.md.",
        ),
        click.option(
            "--horizon-ms",
            type=int,
            default=60_000,
            show_default=True,
            help="Simulated time budget for the run.",
        ),
    ]
    for option in reversed(options):
        command = option(command)
    return command


def build_scenario(seed: int, **params: Any) -> Scenario:
    """Turn parsed options into a scenario."""
    nodes = int(params["nodes"])
    majority = nodes // 2 + 1
    faithful = not params.get("buggy", False)
    store = StoreConfig(
        replicas=nodes,
        read_quorum=params["read_quorum"] or majority,
        write_quorum=params["write_quorum"] or majority,
        request_timeout_ms=params["timeout_ms"],
        stable_versions=faithful,
        read_repair=faithful,
    )

    faults = PRESETS[params["preset"]]
    overrides: dict[str, Any] = {}
    if params["latency_ms"]:
        overrides["latency_ms"] = tuple(params["latency_ms"])
    for name in ("drop_rate", "dup_rate", "partition_rate", "crash_rate", "pause_rate"):
        if params[name] is not None:
            overrides[name] = params[name]
    if params["clock_skew_ms"] is not None:
        overrides["clock_skew_ms"] = params["clock_skew_ms"]
    if overrides:
        faults = faults.but(**overrides)

    workload = WorkloadSpec(
        clients=params["clients"],
        operations=params["ops"],
        keys=tuple(key.strip() for key in str(params["keys"]).split(",") if key.strip()),
        read_ratio=params["read_ratio"],
        cas_ratio=params["cas_ratio"],
    )

    return generate(
        seed=seed,
        store=store,
        faults=faults,
        workload=workload,
        horizon_ms=params["horizon_ms"],
    )


def describe_faults(faults: FaultConfig) -> str:
    """A one-line summary of what was switched on."""
    parts = [f"latency {faults.latency_ms[0]}-{faults.latency_ms[1]}ms"]
    for label, rate in (
        ("drop", faults.drop_rate),
        ("dup", faults.dup_rate),
        ("partition", faults.partition_rate),
        ("crash", faults.crash_rate),
        ("pause", faults.pause_rate),
    ):
        if rate:
            parts.append(f"{label} {rate:g}")
    if faults.clock_skew_ms:
        parts.append(f"skew ±{faults.clock_skew_ms}ms")
    return ", ".join(parts)
