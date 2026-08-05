"""`cassette` — run, explore, reduce and replay simulated clusters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from cassette import __version__
from cassette.cli.options import build_scenario, describe_faults, scenario_options
from cassette.runner import Run, execute

console = Console()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="cassette")
def main() -> None:
    """Deterministic simulation testing for distributed systems.

    Every command takes a seed. The same seed, on any machine, produces the
    same run down to the byte.
    """


@main.command("run")
@click.option("--seed", type=int, required=True, help="The integer the run comes from.")
@click.option("--json", "as_json", is_flag=True, help="Emit the trace on stdout instead.")
@scenario_options
def run_command(seed: int, as_json: bool, **params: Any) -> None:
    """Run one simulation and report what happened."""
    scenario = build_scenario(seed, **params)
    run = execute(scenario)

    if as_json:
        click.echo(json.dumps(run.to_trace().to_json(), separators=(",", ":")))
        return

    _report(run)


@main.command("export")
@click.option("--seed", type=int, required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Where to write the trace.",
)
@scenario_options
def export_command(seed: int, output: Path, **params: Any) -> None:
    """Write a run's trace to a file, for the replayer or for a bug report."""
    scenario = build_scenario(seed, **params)
    run = execute(scenario)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(run.to_trace().to_json(), separators=(",", ":")) + "\n", encoding="utf-8"
    )
    size_kb = output.stat().st_size / 1024
    console.print(f"[green]wrote[/green] {output} ({size_kb:.1f} KiB, {len(run.events)} events)")


def _report(run: Run) -> None:
    scenario = run.scenario
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="dim")
    table.add_column()

    table.add_row("seed", str(scenario.seed))
    table.add_row(
        "cluster",
        f"{scenario.store.replicas} replicas, "
        f"R={scenario.store.read_quorum} W={scenario.store.write_quorum}"
        + ("" if scenario.store.quorums_overlap else "  [yellow](R+W ≤ N)[/yellow]"),
    )
    table.add_row("faults", describe_faults(scenario.faults))
    table.add_row("clients", f"{len(scenario.plans)}, {scenario.operation_count} operations")
    table.add_row("simulated", f"{run.elapsed_ms} ms in {run.delivered} events")

    completed = len(run.history.completed)
    unknown = len(run.history) - completed
    table.add_row("history", f"{completed} completed, {unknown} unknown")

    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    main()
