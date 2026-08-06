"""Wiring a scenario into a simulation, and taking the results out again.

This is the only place that knows the store, the clients, the injector and the
recorder all exist at the same time. Everything above it deals in scenarios and
traces; everything below it deals in events.
"""

from __future__ import annotations

from dataclasses import dataclass

from cassette.checker.history import History
from cassette.checker.linear import DEFAULT_BUDGET, Verdict, check
from cassette.kv.client import Client
from cassette.kv.replica import Replica
from cassette.scenario import Scenario
from cassette.sim.clock import VirtualClock
from cassette.sim.injector import FaultInjector
from cassette.sim.observer import NullObserver, Observer
from cassette.sim.recorder import Recorder
from cassette.sim.simulation import Simulation
from cassette.sim.types import JsonDict
from cassette.trace import Trace, trace_of


@dataclass(frozen=True, slots=True)
class Run:
    """What came out of executing a scenario."""

    scenario: Scenario
    history: History
    events: list[JsonDict]
    delivered: int
    elapsed_ms: int
    verdict: Verdict | None = None

    @property
    def violated(self) -> bool:
        """Whether the checker found a genuine counterexample."""
        return self.verdict is not None and self.verdict.violated

    def to_trace(self) -> Trace:
        """Package the run for storage or for the replayer."""
        trace = trace_of(self.scenario, self.events, self.history)
        return trace if self.verdict is None else trace.with_verdict(self.verdict.to_json())


def execute(
    scenario: Scenario,
    *,
    record: bool = True,
    judge: bool = True,
    budget: int = DEFAULT_BUDGET,
) -> Run:
    """Run `scenario` to its horizon and, by default, check what came out.

    Recording is optional because the fuzzer does not want it: exploring
    thousands of seeds, the only thing that matters is the verdict, and the
    event log is an order of magnitude more data than that needs.
    """
    clock = VirtualClock()
    recorder = Recorder(clock) if record else None
    observer: Observer = recorder if recorder is not None else NullObserver()

    sim = Simulation(seed=scenario.seed, config=scenario.faults, observer=observer, clock=clock)
    for node_id in scenario.store.replica_ids:
        sim.add_node(Replica(node_id, scenario.store))

    history = History()
    clients = [
        Client(node_id, plan, history)
        for node_id, plan in zip(scenario.client_ids, scenario.plans, strict=True)
    ]
    for client in clients:
        sim.add_node(client, skewed=False)

    FaultInjector(sim, list(scenario.store.replica_ids)).start()
    for client in clients:
        client.start(sim.env_for(client.node_id))

    delivered = sim.run(
        until_ms=scenario.horizon_ms,
        stop_when=lambda: all(client.finished for client in clients),
    )

    return Run(
        scenario=scenario,
        history=history,
        events=list(recorder.events) if recorder is not None else [],
        delivered=delivered,
        elapsed_ms=sim.clock.now,
        verdict=check(history, budget) if judge else None,
    )
