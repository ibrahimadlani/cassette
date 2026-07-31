"""T-3: the test the whole project rests on.

For a thousand seeds, run the same workload twice and compare the SHA-256 of
the canonical trace. Any divergence — an unordered set that leaked into a
decision, a dict iterated in insertion order that changed, a stray hash — makes
this fail, and nothing downstream is worth anything until it passes.

It is deliberately the crudest possible check. A subtle assertion would tell
you *what* diverged; this one only tells you *that* something did, which is the
question that matters, and it cannot be fooled by an oversight in the
assertion itself.
"""

from __future__ import annotations

import pytest

from cassette.sim.faults import FaultConfig
from tests.workload import STRESS, run_workload

SEEDS = 1_000


@pytest.mark.slow
def test_a_thousand_seeds_replay_identically() -> None:
    for seed in range(SEEDS):
        first = run_workload(seed).digest()
        second = run_workload(seed).digest()
        assert first == second, f"seed {seed} diverged between two runs"


def test_different_seeds_produce_different_runs() -> None:
    digests = {run_workload(seed).digest() for seed in range(50)}
    assert len(digests) == 50


def test_a_run_is_reproducible_from_the_seed_alone() -> None:
    assert run_workload(8421).events == run_workload(8421).events


def test_faults_actually_fired_in_the_workload() -> None:
    """A determinism test over a run where nothing happens proves nothing."""
    types = {entry["type"] for entry in run_workload(8421).events}
    assert {"msg_send", "msg_deliver", "msg_drop"} <= types
    assert types & {"partition_start", "node_crash", "node_pause"}


def test_a_quiet_network_is_also_reproducible() -> None:
    quiet = FaultConfig(latency_ms=(1, 1))
    assert run_workload(8421, config=quiet).digest() == run_workload(8421, config=quiet).digest()


def test_changing_one_fault_changes_the_run() -> None:
    louder = STRESS.but(drop_rate=0.5)
    assert run_workload(8421).digest() != run_workload(8421, config=louder).digest()
