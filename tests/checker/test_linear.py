"""T-2: histories whose answer is known by hand.

A checker is only worth what its own tests are worth. Every history here was
worked out on paper first, and half of them are non-linearizable on purpose —
a checker that never says no is indistinguishable from `return True`.
"""

from __future__ import annotations

from cassette.checker.history import CAS, OK, READ, UNKNOWN, WRITE, History, Operation
from cassette.checker.linear import check, check_key
from cassette.kv.messages import Value

KEY = "x"


def op(
    index: int,
    kind: str,
    invoked: int,
    returned: int,
    *,
    client: int = 1,
    argument: Value = None,
    expected: Value = None,
    result: Value = None,
    outcome: str = OK,
    key: str = KEY,
) -> Operation:
    return Operation(
        index=index,
        client=client,
        kind=kind,
        key=key,
        argument=argument,
        expected=expected,
        invoked_ms=invoked,
        returned_ms=returned,
        outcome=outcome,
        result=result,
    )


def verdict(*operations: Operation) -> bool:
    return check_key(KEY, list(operations)).linearizable


# -- sequential histories -------------------------------------------------


def test_an_empty_history_is_linearizable() -> None:
    assert verdict() is True


def test_a_read_of_an_untouched_key_returns_nothing() -> None:
    assert verdict(op(0, READ, 0, 10, result=None)) is True


def test_a_read_of_an_untouched_key_cannot_invent_a_value() -> None:
    assert verdict(op(0, READ, 0, 10, result=7)) is False


def test_write_then_read_sees_the_write() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, READ, 20, 30, result=1),
        )
        is True
    )


def test_write_then_read_cannot_see_the_old_value() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, READ, 20, 30, result=None),
        )
        is False
    )


def test_the_second_write_is_the_one_that_sticks() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, WRITE, 20, 30, argument=2),
            op(2, READ, 40, 50, result=2),
        )
        is True
    )


def test_a_read_cannot_go_backwards_in_time() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, WRITE, 20, 30, argument=2),
            op(2, READ, 40, 50, result=1),
        )
        is False
    )


# -- concurrency ----------------------------------------------------------


def test_a_read_overlapping_a_write_may_see_either_value() -> None:
    before = verdict(
        op(0, WRITE, 0, 100, argument=1, client=1),
        op(1, READ, 50, 60, result=None, client=2),
    )
    after = verdict(
        op(0, WRITE, 0, 100, argument=1, client=1),
        op(1, READ, 50, 60, result=1, client=2),
    )
    assert (before, after) == (True, True)


def test_two_concurrent_writes_can_be_ordered_either_way() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 100, argument=1, client=1),
            op(1, WRITE, 10, 110, argument=2, client=2),
            op(2, READ, 200, 210, result=1, client=3),
        )
        is True
    )


def test_a_value_that_was_never_written_is_still_refused() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 100, argument=1, client=1),
            op(1, WRITE, 10, 110, argument=2, client=2),
            op(2, READ, 200, 210, result=3, client=3),
        )
        is False
    )


def test_once_a_read_sees_the_new_value_no_later_read_may_see_the_old_one() -> None:
    """The canonical stale read. This is the shape of the bug in FINDINGS.md."""
    assert (
        verdict(
            op(0, WRITE, 0, 100, argument=1, client=1),
            op(1, READ, 200, 210, result=1, client=2),
            op(2, READ, 300, 310, result=None, client=3),
        )
        is False
    )


def test_reads_agreeing_on_the_old_value_are_fine() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 400, argument=1, client=1),
            op(1, READ, 100, 110, result=None, client=2),
            op(2, READ, 200, 210, result=None, client=3),
        )
        is True
    )


# -- operations that never came back --------------------------------------


def test_an_unknown_write_may_be_treated_as_having_happened() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1, outcome=UNKNOWN),
            op(1, READ, 20, 30, result=1),
        )
        is True
    )


def test_an_unknown_write_may_be_treated_as_never_having_happened() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1, outcome=UNKNOWN),
            op(1, READ, 20, 30, result=None),
        )
        is True
    )


def test_an_unknown_write_does_not_excuse_an_impossible_value() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1, outcome=UNKNOWN),
            op(1, READ, 20, 30, result=9),
        )
        is False
    )


def test_an_unknown_write_never_forces_an_ordering() -> None:
    """It may still be landing, so it cannot make a later read stale."""
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1, outcome=UNKNOWN),
            op(1, READ, 20, 30, result=1),
            op(2, READ, 40, 50, result=1),
        )
        is True
    )


def test_a_history_of_only_unknowns_is_vacuously_linearizable() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1, outcome=UNKNOWN),
            op(1, READ, 20, 30, outcome=UNKNOWN),
        )
        is True
    )


# -- compare-and-swap -----------------------------------------------------


def test_a_swap_on_a_matching_value_succeeds() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, CAS, 20, 30, argument=2, expected=1, result=1),
            op(2, READ, 40, 50, result=2),
        )
        is True
    )


def test_a_swap_on_a_mismatched_value_is_refused() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, CAS, 20, 30, argument=2, expected=9, result=0),
            op(2, READ, 40, 50, result=1),
        )
        is True
    )


def test_a_swap_cannot_claim_to_have_succeeded_against_the_wrong_value() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, CAS, 20, 30, argument=2, expected=9, result=1),
        )
        is False
    )


def test_two_swaps_cannot_both_win_the_same_value() -> None:
    assert (
        verdict(
            op(0, WRITE, 0, 10, argument=1),
            op(1, CAS, 20, 120, argument=2, expected=1, result=1, client=1),
            op(2, CAS, 30, 130, argument=3, expected=1, result=1, client=2),
        )
        is False
    )


# -- keys are independent -------------------------------------------------


def test_a_violation_on_one_key_is_reported_with_that_key() -> None:
    history = History()
    first = history.invoke(1, WRITE, "x", at_ms=0, argument=1)
    history.complete(first, at_ms=10)
    second = history.invoke(1, WRITE, "y", at_ms=20, argument=2)
    history.complete(second, at_ms=30)
    third = history.invoke(1, READ, "y", at_ms=40)
    history.complete(third, at_ms=50, result=99)

    result = check(history)
    assert result.linearizable is False
    assert result.key == "y"
    assert result.operation == third
    assert result.violated is True


def test_a_clean_history_reports_how_much_it_checked() -> None:
    history = History()
    for step in range(4):
        index = history.invoke(1, WRITE, "x", at_ms=step * 10, argument=step)
        history.complete(index, at_ms=step * 10 + 5)
    result = check(history)
    assert result.linearizable is True
    assert result.checked_operations == 4
    assert "linearizable (4 operations)" in str(result)


def test_a_violation_explains_itself_in_english() -> None:
    history = History()
    index = history.invoke(7, READ, "x", at_ms=0)
    history.complete(index, at_ms=10, result=42)
    result = check(history)
    assert "client 7 reads x -> 42" in str(result)
    assert "cannot be placed" in str(result)


def test_a_verdict_renders_for_a_trace() -> None:
    history = History()
    index = history.invoke(1, READ, "x", at_ms=0)
    history.complete(index, at_ms=10, result=1)
    payload = check(history).to_json()
    assert payload["linearizable"] is False
    assert payload["key"] == "x"


# -- the budget -----------------------------------------------------------


def test_an_exhausted_search_is_not_reported_as_a_violation() -> None:
    operations = [op(index, WRITE, 0, 10_000, argument=index, client=index) for index in range(12)]
    operations.append(op(12, READ, 0, 10_000, result=999, client=99))
    result = check_key(KEY, operations, budget=50)
    assert result.exhausted is True
    assert result.violated is False
    assert "budget exhausted" in str(result)
