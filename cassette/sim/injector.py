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
from cassette.sim.faults import CRASH, PARTITION, PAUSE, InjectedFault
from cassette.sim.rng import Rng
from cassette.sim.simulation import Simulation
from cassette.sim.types import NodeId

INJECTOR_STREAM = 0x9E3779B9
"""Salt separating the adversary's draws from the network's.

Without it, adding or removing a fault would shift every latency and loss
decision taken afterwards, and the shrinker's central question — "does the bug
survive without this fault?" — would be unanswerable, because removing the
fault would also silently rewrite the network.
"""


class FaultInjector:
    """Decides what breaks, and when."""

    __slots__ = ("_replicas", "_rng", "_sim", "decisions")

    def __init__(self, simulation: Simulation, replicas: Sequence[NodeId]) -> None:
        if len(replicas) < 2:
            raise ValueError("need at least two replicas to injure")
        self._sim = simulation
        self._replicas = sorted(replicas)
        self._rng = Rng(simulation.rng.seed ^ INJECTOR_STREAM)
        self.decisions: list[InjectedFault] = []

    def start(self) -> None:
        """Arm the first tick. Does nothing if the config injects nothing."""
        if not self._sim.config.injects_anything:
            return
        self._sim.on_fault_tick = self.tick
        self._sim.scheduler.schedule(self._sim.config.tick_ms, CONTROL, FaultTick())

    def tick(self) -> None:
        """Roll for every fault kind, then arm the next tick."""
        config = self._sim.config
        rng = self._rng

        now = self._sim.clock.now
        if rng.chance(config.partition_rate) and self._sim.network.partition is None:
            groups = self._split()
            duration = rng.randint(*config.partition_duration_ms)
            self._sim.schedule_partition(groups, duration)
            self._record(now, PARTITION, duration, tuple(sorted(groups[0])))
        if rng.chance(config.crash_rate):
            victim = rng.choice(self._replicas)
            duration = rng.randint(*config.crash_duration_ms)
            self._sim.schedule_crash(victim, duration)
            self._record(now, CRASH, duration, (victim,))
        if rng.chance(config.pause_rate):
            victim = rng.choice(self._replicas)
            duration = rng.randint(*config.pause_duration_ms)
            self._sim.schedule_pause(victim, duration)
            self._record(now, PAUSE, duration, (victim,))

        self._sim.scheduler.schedule(config.tick_ms, CONTROL, FaultTick())

    def _record(self, at_ms: int, kind: str, duration_ms: int, targets: tuple[NodeId, ...]) -> None:
        self.decisions.append(InjectedFault(at_ms, kind, duration_ms, targets))

    @property
    def schedule(self) -> tuple[InjectedFault, ...]:
        """Everything the adversary decided, ready to be replayed without it."""
        return tuple(self.decisions)

    def _split(self) -> tuple[frozenset[NodeId], ...]:
        """Cut the replicas into two non-empty groups.

        The interesting splits are the lopsided ones — a minority that keeps
        accepting work it has no right to — so the size is drawn uniformly over
        every proper subset rather than aiming for halves.
        """
        rng = self._rng
        size = rng.randint(1, len(self._replicas) - 1)
        chosen = frozenset(rng.sample(self._replicas, size))
        return chosen, frozenset(self._replicas) - chosen


class ScriptedInjector:
    """Replays a captured schedule. Rolls no dice at all.

    It wakes on the same tick as the adversary it replaces, and applies
    whatever was recorded for that tick. Queueing every fault up front would be
    simpler and would be wrong: events are ordered by `(time_ms, seq)`, and
    inserting a fault thousands of sequence numbers earlier moves it past
    messages it originally arrived after. That showed up as a replayed run
    diverging from its original by thirty milliseconds — small, and fatal to
    the whole idea.
    """

    __slots__ = ("_by_tick", "_replicas", "_schedule", "_sim")

    def __init__(
        self,
        simulation: Simulation,
        replicas: Sequence[NodeId],
        schedule: Sequence[InjectedFault],
    ) -> None:
        self._sim = simulation
        self._replicas = sorted(replicas)
        self._schedule = tuple(schedule)
        self._by_tick: dict[int, list[InjectedFault]] = {}
        for fault in self._schedule:
            self._by_tick.setdefault(fault.at_ms, []).append(fault)

    def start(self) -> None:
        """Arm the tick loop, if this scenario has anything to inject."""
        if not (self._sim.config.injects_anything or self._schedule):
            return
        self._sim.on_fault_tick = self.tick
        self._sim.scheduler.schedule(self._sim.config.tick_ms, CONTROL, FaultTick())

    def tick(self) -> None:
        """Apply whatever was recorded for this instant, then arm the next tick."""
        for fault in self._by_tick.get(self._sim.clock.now, ()):
            self._apply(fault)
        self._sim.scheduler.schedule(self._sim.config.tick_ms, CONTROL, FaultTick())

    def _apply(self, fault: InjectedFault) -> None:
        live = frozenset(self._replicas)
        targets = tuple(node for node in fault.targets if node in live)
        if not targets:
            return
        if fault.kind == PARTITION:
            side = frozenset(targets)
            other = live - side
            if other:
                self._sim.schedule_partition((side, other), fault.duration_ms)
        elif fault.kind == CRASH:
            self._sim.schedule_crash(targets[0], fault.duration_ms)
        elif fault.kind == PAUSE:
            self._sim.schedule_pause(targets[0], fault.duration_ms)
