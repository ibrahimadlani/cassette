"""T-7: what the simulator emits has to match what the schema promises.

The web replayer reads traces and never runs the simulator, so the schema is a
real contract between two halves of the project rather than documentation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from cassette.runner import execute
from cassette.scenario import Scenario, WorkloadSpec, generate
from cassette.sim.faults import PERFECT_NETWORK, FaultConfig
from cassette.trace import TRACE_VERSION, Trace

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "trace.schema.json"

STRESS = FaultConfig(
    latency_ms=(1, 40),
    drop_rate=0.05,
    dup_rate=0.03,
    partition_rate=0.06,
    crash_rate=0.03,
    pause_rate=0.03,
    clock_skew_ms=50,
)


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_the_schema_is_a_valid_schema(validator: Draft202012Validator) -> None:
    assert validator.schema["title"] == "Cassette trace"


@pytest.mark.parametrize("seed", [1, 42, 8421, 99_999])
def test_a_quiet_run_validates(validator: Draft202012Validator, seed: int) -> None:
    trace = execute(generate(seed, faults=PERFECT_NETWORK)).to_trace()
    validator.validate(trace.to_json())


@pytest.mark.parametrize("seed", [1, 42, 8421, 99_999])
def test_a_run_under_every_fault_validates(validator: Draft202012Validator, seed: int) -> None:
    trace = execute(generate(seed, faults=STRESS)).to_trace()
    validator.validate(trace.to_json())


def test_a_run_with_compare_and_swap_validates(validator: Draft202012Validator) -> None:
    workload = WorkloadSpec(read_ratio=0.3, cas_ratio=0.3)
    trace = execute(generate(8421, faults=STRESS, workload=workload)).to_trace()
    validator.validate(trace.to_json())


def test_a_trace_round_trips_through_json() -> None:
    trace = execute(generate(8421, faults=STRESS)).to_trace()
    rebuilt = Trace.from_json(json.loads(json.dumps(trace.to_json())))
    assert rebuilt.to_json() == trace.to_json()


def test_the_scenario_round_trips_on_its_own() -> None:
    scenario = generate(8421, faults=STRESS, workload=WorkloadSpec(cas_ratio=0.2))
    assert Scenario.from_json(scenario.to_json()) == scenario


def test_an_unknown_version_is_refused() -> None:
    payload = execute(generate(1)).to_trace().to_json()
    payload["version"] = 99
    with pytest.raises(ValueError, match="version 99 is not supported"):
        Trace.from_json(payload)


def test_the_current_version_is_one() -> None:
    assert TRACE_VERSION == 1


def test_a_verdict_can_be_attached_after_the_fact(validator: Draft202012Validator) -> None:
    trace = execute(generate(8421)).to_trace()
    assert trace.verdict is None
    judged = trace.with_verdict({"linearizable": True, "checked_operations": len(trace.history)})
    validator.validate(judged.to_json())
    assert judged.events == trace.events


def test_the_trace_carries_enough_to_replay_without_the_simulator() -> None:
    """Everything the replayer draws has to be in the file."""
    trace = execute(generate(8421, faults=STRESS)).to_trace()
    types = {str(event["type"]) for event in trace.events}
    assert {"msg_send", "msg_deliver"} <= types
    assert trace.scenario.store.replicas == 5
    assert trace.history
