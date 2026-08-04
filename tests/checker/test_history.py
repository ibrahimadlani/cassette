from cassette.checker.history import NEVER, OK, READ, UNKNOWN, WRITE, History, Operation


def test_an_invoked_operation_starts_unknown() -> None:
    history = History()
    index = history.invoke(client=9, kind=WRITE, key="x", at_ms=0, argument=1)
    op = history.operations[index]
    assert op.outcome == UNKNOWN
    assert op.returned_ms == NEVER
    assert op.completed is False


def test_completing_records_the_result_and_the_time() -> None:
    history = History()
    index = history.invoke(client=9, kind=READ, key="x", at_ms=0)
    history.complete(index, at_ms=40, result=7)
    op = history.operations[index]
    assert (op.outcome, op.returned_ms, op.result) == (OK, 40, 7)
    assert op.completed is True


def test_giving_up_leaves_the_operation_unknown() -> None:
    history = History()
    index = history.invoke(client=9, kind=WRITE, key="x", at_ms=0, argument=1)
    history.give_up(index)
    assert history.operations[index].outcome == UNKNOWN


def test_indices_are_assigned_in_invocation_order() -> None:
    history = History()
    assert [history.invoke(9, READ, "x", at_ms=t) for t in (0, 10, 20)] == [0, 1, 2]


def test_completed_filters_out_the_unknown() -> None:
    history = History()
    first = history.invoke(9, WRITE, "x", at_ms=0, argument=1)
    history.invoke(9, WRITE, "x", at_ms=10, argument=2)
    history.complete(first, at_ms=5)
    assert [op.index for op in history.completed] == [first]


def test_operations_group_by_key_with_keys_sorted() -> None:
    history = History()
    history.invoke(9, WRITE, "z", at_ms=0, argument=1)
    history.invoke(9, WRITE, "a", at_ms=10, argument=2)
    history.invoke(9, READ, "z", at_ms=20)
    grouped = history.by_key()
    assert list(grouped) == ["a", "z"]
    assert [op.index for op in grouped["z"]] == [0, 2]


def test_a_completed_operation_precedes_a_later_one() -> None:
    first = Operation(0, 9, WRITE, "x", invoked_ms=0, returned_ms=10, outcome=OK)
    second = Operation(1, 9, READ, "x", invoked_ms=20)
    assert first.precedes(second) is True


def test_overlapping_operations_are_concurrent() -> None:
    first = Operation(0, 9, WRITE, "x", invoked_ms=0, returned_ms=30, outcome=OK)
    second = Operation(1, 9, READ, "x", invoked_ms=20)
    assert first.precedes(second) is False


def test_an_unknown_operation_never_forces_an_ordering() -> None:
    unknown = Operation(0, 9, WRITE, "x", invoked_ms=0, returned_ms=10, outcome=UNKNOWN)
    later = Operation(1, 9, READ, "x", invoked_ms=999)
    assert unknown.bounded is False
    assert unknown.precedes(later) is False


def test_a_history_renders_for_a_trace() -> None:
    history = History()
    index = history.invoke(9, READ, "x", at_ms=0)
    history.complete(index, at_ms=12, result=3)
    assert history.to_json() == [
        {
            "index": 0,
            "client": 9,
            "kind": READ,
            "key": "x",
            "argument": None,
            "expected": None,
            "invoked": 0,
            "returned": 12,
            "outcome": OK,
            "result": 3,
        }
    ]


def test_a_write_describes_itself() -> None:
    op = Operation(0, 1, WRITE, "x", argument=5, outcome=OK)
    assert op.describe() == "client 1 writes x=5 -> ok"


def test_a_read_describes_its_result() -> None:
    op = Operation(0, 1, READ, "x", outcome=OK, result=5)
    assert op.describe() == "client 1 reads x -> 5"


def test_a_swap_describes_its_outcome() -> None:
    swapped = Operation(0, 1, "cas", "x", argument=2, expected=1, outcome=OK, result=1)
    refused = Operation(1, 1, "cas", "x", argument=2, expected=1, outcome=OK, result=0)
    assert swapped.describe() == "client 1 cas x 1 -> 2 -> swapped"
    assert refused.describe() == "client 1 cas x 1 -> 2 -> refused"


def test_an_unknown_operation_says_so() -> None:
    op = Operation(0, 1, WRITE, "x", argument=5)
    assert op.describe() == "client 1 writes x=5 (unknown)"


def test_length_counts_operations() -> None:
    history = History()
    for t in range(4):
        history.invoke(9, READ, "x", at_ms=t)
    assert len(history) == 4
