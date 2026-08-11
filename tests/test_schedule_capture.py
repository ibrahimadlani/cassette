"""A captured fault schedule has to replay the run exactly.

This is the hinge the shrinker hangs on. If pinning the adversary's decisions
changed the run in any way, then removing one of those decisions would tell you
nothing about the original failure.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cassette.runner import execute
from cassette.scenario import HARSH, STANDARD, Scenario, generate
from cassette.sim.faults import CRASH, PARTITION, PAUSE, InjectedFault
from tests.broken import failing_scenarios

SEEDS = [1, 42, 161, 8421]


@pytest.mark.parametrize("seed", SEEDS)
def test_pinning_the_schedule_reproduces_the_history(seed: int) -> None:
    run = execute(generate(seed, faults=HARSH), record=False)
    replay = execute(run.pinned(), record=False)
    assert replay.history.to_json() == run.history.to_json()


@pytest.mark.parametrize("seed", SEEDS)
def test_pinning_the_schedule_reproduces_the_verdict(seed: int) -> None:
    run = execute(generate(seed, faults=HARSH), record=False)
    assert execute(run.pinned(), record=False).verdict == run.verdict


@pytest.mark.parametrize("seed", SEEDS)
def test_pinning_the_schedule_reproduces_the_events(seed: int) -> None:
    run = execute(generate(seed, faults=STANDARD))
    assert execute(run.pinned()).events == run.events


def test_a_pinned_scenario_is_pinned_to_the_same_thing_twice() -> None:
    run = execute(generate(8421, faults=HARSH), record=False)
    assert execute(run.pinned(), record=False).schedule == run.schedule


def test_a_captured_schedule_covers_every_fault_kind() -> None:
    kinds: set[str] = set()
    for seed in range(60):
        kinds |= {fault.kind for fault in execute(generate(seed, faults=HARSH)).schedule}
    assert kinds == {PARTITION, CRASH, PAUSE}


def test_a_quiet_run_captures_nothing() -> None:
    assert execute(generate(1, faults=STANDARD.without_faults()), record=False).schedule == ()


def test_an_empty_schedule_is_not_the_same_as_no_schedule() -> None:
    """None means "let the adversary decide"; () means "it decided nothing"."""
    scenario = generate(8421, faults=HARSH)
    assert scenario.schedule is None
    assert scenario.fault_count == -1

    scripted = replace(scenario, schedule=())
    assert scripted.fault_count == 0
    assert execute(scripted, record=False).schedule == ()


def test_a_fault_round_trips_through_json() -> None:
    fault = InjectedFault(at_ms=400, kind=PARTITION, duration_ms=250, targets=(1, 3))
    assert InjectedFault.from_json(fault.to_json()) == fault


def test_a_fault_describes_itself() -> None:
    assert InjectedFault(0, PARTITION, 250, (1, 3)).describe() == (
        "partition {n1, n3} away for 250ms"
    )
    assert InjectedFault(0, CRASH, 100, (2,)).describe() == "crash n2 for 100ms"


def test_a_scenario_with_a_schedule_round_trips() -> None:
    pinned = execute(generate(8421, faults=HARSH), record=False).pinned()
    assert pinned.__class__.from_json(pinned.to_json()) == pinned


@pytest.mark.parametrize("scenario", failing_scenarios(4), ids=lambda s: f"seed-{s.seed}")
def test_a_failing_scenario_still_fails_once_pinned(scenario: Scenario) -> None:
    run = execute(scenario, record=False)
    assert run.violated
    assert execute(run.pinned(), record=False).verdict == run.verdict
