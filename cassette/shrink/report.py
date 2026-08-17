"""Reading a reduced scenario out loud.

A minimal scenario is only useful if somebody can look at it and see the
mechanism. Four operations and a stale read should fit on a slide, so this
renders the reduced run as a numbered story with the offending operation marked
— which is the form the bug ends up in when it reaches `docs/FINDINGS.md` or a
README.
"""

from __future__ import annotations

from string import ascii_uppercase

from cassette.checker.history import CAS, READ, WRITE, Operation
from cassette.runner import execute
from cassette.shrink.reduce import Reduction
from cassette.sim.types import NodeId


def label_clients(operations: list[Operation]) -> dict[NodeId, str]:
    """Name the clients A, B, C… in the order they first appear."""
    names: dict[NodeId, str] = {}
    for op in operations:
        if op.client not in names:
            names[op.client] = ascii_uppercase[len(names) % len(ascii_uppercase)]
    return names


def describe(op: Operation, names: dict[NodeId, str], coordinator: NodeId | None) -> str:
    """One operation, as a person would say it."""
    who = f"client {names.get(op.client, str(op.client))}"
    via = f"  via n{coordinator}" if coordinator is not None else ""

    if op.kind == WRITE:
        action = f"writes {op.key}={op.argument}"
    elif op.kind == READ:
        action = f"reads  {op.key}"
    else:
        action = f"cas    {op.key} {op.expected}->{op.argument}"
    # Wide enough for the longest form, `cas    key old->new`, so that four
    # lines of different shapes still read as a table.
    action = action.ljust(14)

    if not op.completed:
        outcome = "(no answer)"
    elif op.kind == READ:
        outcome = f"-> {op.result}"
    elif op.kind == CAS:
        outcome = "-> swapped" if op.result else "-> refused"
    else:
        outcome = "-> ok"

    return f"{who} {action}{via}   {outcome}"


def narrate(reduction: Reduction) -> list[str]:
    """The reduced scenario as a numbered list, with the violation marked."""
    run = execute(reduction.reduced, record=False)
    operations = run.history.operations
    names = label_clients(operations)
    coordinators = _coordinators(reduction)
    guilty = reduction.verdict.operation

    lines: list[str] = []
    for position, op in enumerate(operations, start=1):
        marker = "   <-- no legal order can explain this" if op.index == guilty else ""
        lines.append(f"{position}. {describe(op, names, coordinators.get(op.index))}{marker}")

    for fault in reduction.reduced.schedule or ():
        lines.append(f"   ({fault.describe()} at t={fault.at_ms}ms)")

    return lines


def _coordinators(reduction: Reduction) -> dict[int, NodeId]:
    """Which replica coordinated each operation, by history index.

    Clients issue their plans in order, so the nth operation a client performs
    is the nth entry of its plan.
    """
    scenario = reduction.reduced
    seen: dict[NodeId, int] = {}
    mapping: dict[int, NodeId] = {}
    run = execute(scenario, record=False)
    for op in run.history.operations:
        position = seen.get(op.client, 0)
        seen[op.client] = position + 1
        client_index = op.client - scenario.store.replicas
        if 0 <= client_index < len(scenario.plans):
            plan = scenario.plans[client_index]
            if position < len(plan):
                mapping[op.index] = plan[position].coordinator
    return mapping


def summarise(reduction: Reduction) -> list[str]:
    """The before-and-after table, as plain lines."""
    return [
        f"Original scenario   {reduction.original_size}",
        f"After deletion      {reduction.deleted_size}",
        f"Reduced scenario    {reduction.reduced_size}",
        "",
        f"{reduction.ratio:.0f}x fewer events, {reduction.candidates} candidates evaluated",
    ]
