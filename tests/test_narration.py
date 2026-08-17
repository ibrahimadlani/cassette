"""The reduced scenario has to read correctly for every kind of operation.

The narration is what a bug looks like by the time it reaches FINDINGS.md or a
README, so its edge cases — a compare-and-swap, an operation nobody got an
answer for, an injected fault still in the schedule — are worth pinning
directly rather than only through whatever the shrinker happens to produce.
"""

from __future__ import annotations

from cassette.checker.history import CAS, OK, READ, UNKNOWN, WRITE, Operation
from cassette.shrink.report import describe, label_clients
from cassette.sim.types import NodeId

NAMES: dict[NodeId, str] = {5: "A", 6: "B"}


def op(kind: str, **overrides: object) -> Operation:
    fields: dict[str, object] = {
        "index": 0,
        "client": 5,
        "kind": kind,
        "key": "x",
        "outcome": OK,
    }
    fields.update(overrides)
    return Operation(**fields)  # type: ignore[arg-type]


def test_clients_are_labelled_in_order_of_appearance() -> None:
    operations = [op(WRITE, client=9), op(READ, client=4), op(READ, client=9)]
    assert label_clients(operations) == {9: "A", 4: "B"}


def test_a_write_reads_as_a_write() -> None:
    line = describe(op(WRITE, argument=1), NAMES, 2)
    assert line.startswith("client A writes x=1")
    assert line.endswith("via n2   -> ok")


def test_a_read_shows_what_it_returned() -> None:
    assert "-> 7" in describe(op(READ, result=7), NAMES, 0)


def test_a_read_of_an_absent_key_shows_nothing() -> None:
    assert describe(op(READ, result=None), NAMES, 0).endswith("-> None")


def test_a_successful_swap_says_swapped() -> None:
    line = describe(op(CAS, argument=2, expected=1, result=1), NAMES, 1)
    assert "cas    x 1->2" in line
    assert line.endswith("-> swapped")


def test_a_refused_swap_says_refused() -> None:
    line = describe(op(CAS, argument=2, expected=9, result=0), NAMES, 1)
    assert line.endswith("-> refused")


def test_an_operation_with_no_answer_says_so() -> None:
    assert describe(op(WRITE, argument=1, outcome=UNKNOWN), NAMES, 3).endswith("(no answer)")


def test_an_unknown_client_falls_back_to_its_id() -> None:
    assert describe(op(READ, client=99, result=1), NAMES, 0).startswith("client 99")


def test_an_unknown_coordinator_is_left_out() -> None:
    assert "via" not in describe(op(READ, result=1), NAMES, None)


def test_columns_line_up_across_kinds() -> None:
    """Four lines of different shapes still have to read as a table."""
    lines = [
        describe(op(WRITE, argument=1), NAMES, 2),
        describe(op(READ, result=2), NAMES, 0),
        describe(op(CAS, argument=3, expected=2, result=1), NAMES, 1),
    ]
    assert len({line.index("via") for line in lines}) == 1
