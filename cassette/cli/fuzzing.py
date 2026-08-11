"""`cassette fuzz` and `cassette regress`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from cassette import corpus
from cassette.cli.options import build_scenario, scenario_options
from cassette.fuzz import Finding, Plan, Report, fuzz
from cassette.runner import execute
from cassette.scenario import WorkloadSpec

console = Console()


def _plan_from(seed: int, params: dict[str, Any]) -> Plan:
    template = build_scenario(seed, **params)
    return Plan(
        preset=str(params["preset"]) + ("-buggy" if params.get("buggy") else ""),
        store=template.store,
        faults=template.faults,
        workload=_workload_of(params),
        horizon_ms=int(params["horizon_ms"]),
    )


def _workload_of(params: dict[str, Any]) -> WorkloadSpec:
    return WorkloadSpec(
        clients=params["clients"],
        operations=params["ops"],
        keys=tuple(key.strip() for key in str(params["keys"]).split(",") if key.strip()),
        read_ratio=params["read_ratio"],
        cas_ratio=params["cas_ratio"],
    )


@click.command("fuzz")
@click.option("--seeds", type=int, default=1_000, show_default=True, help="How many to explore.")
@click.option("--start", type=int, default=0, show_default=True, help="First seed.")
@click.option("--workers", type=int, default=1, show_default=True, help="Processes to spread over.")
@click.option("--all", "explore_all", is_flag=True, help="Keep going past the first violation.")
@click.option(
    "--corpus",
    "corpus_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=corpus.DEFAULT_PATH,
    show_default=True,
    help="Where known failures live.",
)
@click.option("--no-record", is_flag=True, help="Do not add new failures to the corpus.")
@scenario_options
def fuzz_command(
    seeds: int,
    start: int,
    workers: int,
    explore_all: bool,
    corpus_path: Path,
    no_record: bool,
    **params: Any,
) -> None:
    """Explore many seeds looking for a violation.

    Exits non-zero only on a violation that is not already in the corpus. A
    known failure is reported and tolerated, so this can run on every push
    without going red for a bug that is already written down.
    """
    plan = _plan_from(start, params)
    known = {(entry.preset, entry.seed) for entry in corpus.load(corpus_path)}

    columns = (
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("[cyan]{task.fields[rate]}[/cyan]"),
        TimeElapsedColumn(),
    )
    with Progress(*columns, console=console, transient=True) as progress:
        task = progress.add_task("fuzzing", total=seeds, rate="")
        state = {"done": 0}

        def tick(seed: int, finding: Finding | None) -> None:
            state["done"] += 1
            elapsed = progress.tasks[task].elapsed or 1e-9
            progress.update(task, completed=state["done"], rate=f"{state['done'] / elapsed:.0f}/s")

        report = fuzz(
            range(start, start + seeds),
            plan,
            workers=workers,
            stop_at_first=not explore_all,
            on_result=tick,
        )

    fresh = [f for f in report.findings if (plan.preset, f.seed) not in known]
    _report(report, fresh, len(report.findings) - len(fresh))

    if fresh and not no_record:
        added = corpus.add([plan.entry_for(f.seed, f.explanation) for f in fresh], corpus_path)
        console.print(f"[dim]added {added} seed(s) to {corpus_path}[/dim]")

    if fresh:
        raise SystemExit(1)


def _report(report: Report, fresh: list[Finding], known_count: int) -> None:
    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_column(style="dim")
    summary.add_column()
    summary.add_row("explored", f"{report.explored} scenarios")
    summary.add_row("throughput", f"{report.throughput:.0f} scenarios/s")
    if report.undecided:
        summary.add_row("undecided", f"{report.undecided} (checker budget exhausted)")
    console.print(summary)
    console.print()

    if not report.findings:
        console.print("[green]no violations[/green]")
        return

    for finding in fresh:
        console.print(f"[bold red]NEW[/bold red]      {finding}")
    if known_count:
        console.print(f"[yellow]{known_count} known failure(s) reproduced[/yellow]")


@click.command("regress")
@click.option(
    "--corpus",
    "corpus_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=corpus.DEFAULT_PATH,
    show_default=True,
)
def regress_command(corpus_path: Path) -> None:
    """Replay every seed in the regression corpus.

    Exits non-zero if any of them still violates linearizability.
    """
    entries = corpus.load(corpus_path)
    if not entries:
        console.print(f"[dim]{corpus_path} is empty[/dim]")
        return

    still_failing = []
    for entry in entries:
        verdict = execute(entry.to_scenario(), record=False).verdict
        assert verdict is not None
        if verdict.violated:
            still_failing.append((entry, verdict))
            console.print(f"[red]FAIL[/red]  seed {entry.seed}  {verdict.explanation}")
        else:
            console.print(f"[green]ok[/green]    seed {entry.seed}")

    console.print()
    console.print(f"{len(entries) - len(still_failing)}/{len(entries)} clean")
    if still_failing:
        raise SystemExit(1)
