"""The adversary.

Wakes on a fixed tick, rolls one die per fault kind, and schedules whatever it
decided. Everything it does goes through the same public `Simulation` methods a
test would use, so a hand-written scenario and a generated one are
indistinguishable to the engine — which is exactly what the shrinker relies on
when it replays a reduced schedule without an injector at all.
"""

from __future__ import annotations

from collections.abc import Sequence

from cassette.sim.events import CONTROL, FaultTick
from cassette.sim.simulation import Simulation
from cassette.sim.types import NodeId


class FaultInjector:
    """Decides what breaks, and when."""

    __slots__ = ("_replicas", "_sim")

    def __init__(self, simulation: Simulation, replicas: Sequence[NodeId]) -> None:
        if len(replicas) < 2:
            raise ValueError("need at least two replicas to injure")
        self._sim = simulation
        self._replicas = sorted(replicas)

    def start(self) -> None:
        """Arm the first tick. Does nothing if the config injects nothing."""
        if not self._sim.config.injects_anything:
            return
        self._sim.on_fault_tick = self.tick
        self._sim.scheduler.schedule(self._sim.config.tick_ms, CONTROL, FaultTick())

    def tick(self) -> None:
        """Roll for every fault kind, then arm the next tick."""
        config = self._sim.config
        rng = self._sim.rng

        if rng.chance(config.partition_rate) and self._sim.network.partition is None:
            self._sim.schedule_partition(self._split(), rng.randint(*config.partition_duration_ms))
        if rng.chance(config.crash_rate):
            victim = rng.choice(self._replicas)
            self._sim.schedule_crash(victim, rng.randint(*config.crash_duration_ms))
        if rng.chance(config.pause_rate):
            victim = rng.choice(self._replicas)
            self._sim.schedule_pause(victim, rng.randint(*config.pause_duration_ms))

        self._sim.scheduler.schedule(config.tick_ms, CONTROL, FaultTick())

    def _split(self) -> tuple[frozenset[NodeId], ...]:
        """Cut the replicas into two non-empty groups.

        The interesting splits are the lopsided ones — a minority that keeps
        accepting work it has no right to — so the size is drawn uniformly over
        every proper subset rather than aiming for halves.
        """
        rng = self._sim.rng
        size = rng.randint(1, len(self._replicas) - 1)
        chosen = frozenset(rng.sample(self._replicas, size))
        return chosen, frozenset(self._replicas) - chosen
