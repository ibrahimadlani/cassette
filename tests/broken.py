"""The store with its two known defects switched back on.

Both bugs in `docs/FINDINGS.md` are fixed, which is a problem for the tests
that need something to find. Rather than deleting them — and losing the only
evidence that the fuzzer and the shrinker do anything — they now run against
the configuration that still fails.

This is the same switch `cassette --buggy` flips, so the demo in the README and
these tests are exercising one code path, not two.
"""

from __future__ import annotations

from dataclasses import replace

from cassette import corpus
from cassette.kv.config import StoreConfig
from cassette.scenario import Scenario

BROKEN = StoreConfig(stable_versions=False, read_repair=False)
"""Five replicas, majority quorums, and both defects present."""


def break_(scenario: Scenario) -> Scenario:
    """The same scenario against a store that still has the bugs."""
    return replace(
        scenario,
        store=replace(scenario.store, stable_versions=False, read_repair=False),
    )


def failing_scenarios(limit: int = 3) -> list[Scenario]:
    """Corpus entries, restored to the state in which they failed."""
    return [break_(entry.to_scenario()) for entry in corpus.load()[:limit]]
