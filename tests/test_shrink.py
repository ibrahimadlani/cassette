from __future__ import annotations

import pytest

from cassette import corpus
from cassette.runner import execute
from cassette.scenario import STANDARD, generate
from cassette.shrink import shrink
from cassette.shrink.reduce import Size
from cassette.shrink.report import narrate, summarise

FAILING = corpus.load()[:3]


def test_shrinking_a_healthy_scenario_is_refused() -> None:
    with pytest.raises(ValueError, match="linearizable"):
        shrink(generate(0, faults=STANDARD.without_faults()))


@pytest.mark.parametrize("entry", FAILING, ids=lambda e: f"seed-{e.seed}")
def test_the_reduced_scenario_still_fails(entry: corpus.Entry) -> None:
    reduction = shrink(entry.to_scenario())
    run = execute(reduction.reduced, record=False)
    assert run.violated


@pytest.mark.parametrize("entry", FAILING, ids=lambda e: f"seed-{e.seed}")
def test_the_reduced_scenario_fails_on_the_same_key(entry: corpus.Entry) -> None:
    reduction = shrink(entry.to_scenario())
    original = execute(entry.to_scenario(), record=False).verdict
    assert original is not None
    assert reduction.verdict.key == original.key


@pytest.mark.parametrize("entry", FAILING, ids=lambda e: f"seed-{e.seed}")
def test_the_reduced_scenario_is_smaller(entry: corpus.Entry) -> None:
    reduction = shrink(entry.to_scenario())
    assert reduction.reduced_size.weight < reduction.original_size.weight
    assert reduction.reduced_size.operations < reduction.original_size.operations


@pytest.mark.parametrize("entry", FAILING, ids=lambda e: f"seed-{e.seed}")
def test_the_reduction_is_at_least_fivefold(entry: corpus.Entry) -> None:
    assert shrink(entry.to_scenario()).ratio >= 5.0


@pytest.mark.parametrize("entry", FAILING, ids=lambda e: f"seed-{e.seed}")
def test_shrinking_is_deterministic(entry: corpus.Entry) -> None:
    left, right = shrink(entry.to_scenario()), shrink(entry.to_scenario())
    assert left.reduced.to_json() == right.reduced.to_json()
    assert left.candidates == right.candidates


def test_the_reduced_scenario_is_replayable_on_its_own() -> None:
    reduction = shrink(FAILING[0].to_scenario())
    first = execute(reduction.reduced, record=False)
    second = execute(reduction.reduced, record=False)
    assert first.history.to_json() == second.history.to_json()


def test_the_reduced_scenario_has_an_explicit_schedule() -> None:
    """No adversary left. What you see in the scenario is everything that happens."""
    assert shrink(FAILING[0].to_scenario()).reduced.schedule is not None


def test_a_tight_budget_still_returns_something_valid() -> None:
    reduction = shrink(FAILING[0].to_scenario(), budget=5)
    assert execute(reduction.reduced, record=False).violated
    assert reduction.candidates <= 5


def test_deletion_and_search_are_reported_separately() -> None:
    """The search phase does not derive from the original, so it is never claimed to."""
    reduction = shrink(FAILING[0].to_scenario())
    assert reduction.deletion_ratio <= reduction.ratio
    assert reduction.rebuilt is (reduction.reduced_size.weight < reduction.deleted_size.weight)


def test_the_narration_names_every_operation() -> None:
    reduction = shrink(FAILING[0].to_scenario())
    lines = narrate(reduction)
    operations = execute(reduction.reduced, record=False).history.operations
    assert len(lines) >= len(operations)
    assert lines[0].startswith("1. client A")


def test_the_narration_marks_the_violation() -> None:
    lines = narrate(shrink(FAILING[0].to_scenario()))
    assert sum("no legal order" in line for line in lines) == 1


def test_the_summary_reports_all_three_sizes() -> None:
    lines = summarise(shrink(FAILING[0].to_scenario()))
    assert "Original scenario" in lines[0]
    assert "After deletion" in lines[1]
    assert "Reduced scenario" in lines[2]


def test_size_weights_operations_above_events() -> None:
    fewer_operations = Size(replicas=5, clients=3, operations=4, faults=0, events=200)
    fewer_events = Size(replicas=5, clients=3, operations=20, faults=0, events=100)
    assert fewer_operations.weight < fewer_events.weight


def test_a_size_describes_itself() -> None:
    described = str(Size(replicas=3, clients=2, operations=4, faults=1, events=48))
    assert described == "48 events, 3 replicas, 2 clients, 4 operations, 1 injected faults"
