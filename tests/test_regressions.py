"""T-6: every seed that has ever failed is replayed on every run.

All fourteen of them come back clean now. That is the assertion this file
exists for, and it is the one that makes a fix mean something: a bug that has
been found once cannot come back without the suite going red.

Reproducibility is still pinned alongside it. A regression suite built on
seeds is only as good as the guarantee that a seed means the same thing
tomorrow.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cassette import corpus
from cassette.checker.linear import Verdict
from cassette.runner import execute

CORPUS_PATH = Path(__file__).resolve().parent.parent / "regressions.txt"
ENTRIES = corpus.load(CORPUS_PATH)


def judge(entry: corpus.Entry) -> Verdict:
    verdict = execute(entry.to_scenario(), record=False).verdict
    assert verdict is not None
    return verdict


def test_the_corpus_is_not_empty() -> None:
    """A regression suite with nothing in it passes for the wrong reason."""
    assert ENTRIES


def test_every_entry_parses() -> None:
    assert all(entry.seed >= 0 for entry in ENTRIES)


def test_the_corpus_has_no_duplicates() -> None:
    keys = [(entry.preset, entry.seed) for entry in ENTRIES]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: f"seed-{entry.seed}")
def test_a_corpus_seed_replays_identically(entry: corpus.Entry) -> None:
    first, second = judge(entry), judge(entry)
    assert first == second


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: f"seed-{entry.seed}")
def test_a_corpus_seed_is_linearizable_now(entry: corpus.Entry) -> None:
    verdict = judge(entry)
    assert verdict.linearizable, f"seed {entry.seed} regressed: {verdict.explanation}"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: f"seed-{entry.seed}")
def test_a_corpus_seed_fails_again_with_the_defects_switched_back_on(
    entry: corpus.Entry,
) -> None:
    """The corpus proves the fix, so it has to prove the bug was there too.

    Without this, a corpus of seeds that pass could just as easily be a corpus
    of seeds that never failed.
    """
    scenario = entry.to_scenario()
    broken = replace(
        scenario, store=replace(scenario.store, stable_versions=False, read_repair=False)
    )
    verdict = execute(broken, record=False).verdict
    assert verdict is not None
    assert verdict.violated, f"seed {entry.seed} does not reproduce its original failure"
