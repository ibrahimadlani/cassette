"""The one source of randomness a simulation is allowed to have.

This is the single module in `cassette.sim` permitted to import `random`, and
the determinism guard in `tests/test_determinism_guard.py` enforces that.

Every helper below derives from `Random.random()`. That is deliberate:
`random()` is the one Mersenne Twister primitive CPython documents as stable,
while `randint`, `choice`, `sample` and `shuffle` have all changed their
internal draw patterns between releases. Deriving everything by hand costs a
few lines and buys trace hashes that survive a Python upgrade.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Rng:
    """A seeded random source with a version-stable draw sequence."""

    __slots__ = ("_random", "_seed")

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._random = random.Random(seed)

    @property
    def seed(self) -> int:
        """The seed this source was created from."""
        return self._seed

    def random(self) -> float:
        """Draw a float uniformly from [0, 1)."""
        return self._random.random()

    def chance(self, probability: float) -> bool:
        """Return True with the given probability.

        A probability of 0.0 never fires and 1.0 always does, without consuming
        a different number of draws — the draw happens either way so that
        turning a fault off does not shift every later decision.
        """
        return self._random.random() < probability

    def randint(self, low: int, high: int) -> int:
        """Draw an integer uniformly from the inclusive range [low, high]."""
        if high < low:
            raise ValueError(f"empty range [{low}, {high}]")
        return low + int(self._random.random() * (high - low + 1))

    def choice(self, population: Sequence[T]) -> T:
        """Pick one element uniformly."""
        if not population:
            raise ValueError("cannot choose from an empty population")
        return population[self.randint(0, len(population) - 1)]

    def shuffle(self, items: list[T]) -> None:
        """Shuffle `items` in place with a Fisher-Yates pass."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randint(0, i)
            items[i], items[j] = items[j], items[i]

    def sample(self, population: Sequence[T], size: int) -> list[T]:
        """Draw `size` distinct elements, in the order they were selected.

        A partial Fisher-Yates over a copy: O(len(population)) but with a draw
        count that depends only on `size`, which keeps the sequence predictable
        when a caller changes the population without changing the sample size.
        """
        if not 0 <= size <= len(population):
            raise ValueError(f"cannot sample {size} of {len(population)}")
        pool = list(population)
        for i in range(size):
            j = self.randint(i, len(pool) - 1)
            pool[i], pool[j] = pool[j], pool[i]
        return pool[:size]
