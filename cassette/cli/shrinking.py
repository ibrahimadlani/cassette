"""`cassette shrink`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from cassette.cli.options import build_scenario, scenario_options
from cassette.runner import execute
from cassette.shrink import shrink
from cassette.shrink.reduce import DEFAULT_BUDGET, Reduction
from cassette.shrink.report import narrate

console = Console()


@click.command("shrink")
@click.option("--seed", type=int, required=True, help="A seed that produces a violation.")
@click.option(
    "--budget",
    type=int,
    default=DEFAULT_BUDGET,
    show_default=True,
    help="Candidate scenarios to evaluate before giving up.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the reduced scenario's trace here.",
)
@scenario_options
def shrink_command(seed: int, budget: int, output: Path | None, **params: Any) -> None:
    """Reduce a failing seed to the smallest scenario that still fails.

    Exits non-zero if the seed does not actually violate anything — shrinking
    a run that works is a question with no answer.
    """
    scenario = build_scenario(seed, **params)
    try:
        reduction = shrink(scenario, budget=budget)
    except ValueError as reason:
        console.print(f"[yellow]{reason}[/yellow]")
        raise SystemExit(2) from reason

    _print_sizes(reduction)
    console.print()
    for line in narrate(reduction):
        # No extra indent: the widened operation column plus the violation marker
        # already reaches an 80-column terminal, and a wrapped counterexample is
        # not a readable one.
        console.print(line)
    console.print()
    console.print(f"[dim]{reduction.verdict.explanation}[/dim]")

    if output is not None:
        trace = execute(reduction.reduced).to_trace()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(trace.to_json(), separators=(",", ":")) + "\n", encoding="utf-8"
        )
        console.print(f"[green]wrote[/green] {output}")


def _print_sizes(reduction: Reduction) -> None:
    table = Table(box=None, pad_edge=False)
    table.add_column("", style="dim")
    table.add_column("events", justify="right")
    table.add_column("replicas", justify="right")
    table.add_column("clients", justify="right")
    table.add_column("operations", justify="right")
    table.add_column("faults", justify="right")

    for label, size in (
        ("original", reduction.original_size),
        ("after deletion", reduction.deleted_size),
        ("reduced", reduction.reduced_size),
    ):
        table.add_row(
            label,
            str(size.events),
            str(size.replicas),
            str(size.clients),
            str(size.operations),
            str(size.faults),
        )

    console.print(table)
    console.print(
        f"[bold]{reduction.ratio:.0f}x[/bold] fewer events "
        f"({reduction.candidates} candidates evaluated)"
    )
