"""T-6: every seed that has ever failed is replayed on every run.

Today these seeds still fail — the bug they found has not been fixed yet, and
pretending otherwise would be worse than useless. What the suite pins right now
is that they are *reproducible*: each one produces the same verdict, naming the
same operation, every single time.

That is the property the whole project rests on, and it is the property that
makes the next step possible. Once the fix lands, this file gains the
assertion it is really for: every seed in the corpus comes back clean.
"""

from __future__ import annotations

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
def test_a_corpus_seed_still_reproduces_its_recorded_failure(entry: corpus.Entry) -> None:
    verdict = judge(entry)
    assert verdict.violated, f"seed {entry.seed} no longer fails — update the corpus"
    assert entry.note.startswith(str(verdict.explanation)[:20])
