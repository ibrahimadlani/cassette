"""What the simulator is allowed to do to the system under test.

A `FaultConfig` is the adversary's budget. It is a plain frozen dataclass with
a JSON round trip, because it has to survive three journeys: into a trace file,
into a regression corpus, and into the shrinker, which spends its whole life
producing slightly weaker versions of one.

Every rate is a probability applied on a fixed tick rather than a per-message
coin flip. That distinction matters for shrinking: a tick-based schedule has a
bounded number of decisions, so removing one of them is a well defined
operation, while a per-message flip would change meaning the moment the number
of messages changed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from cassette.sim.types import JsonDict

MillisecondRange = tuple[int, int]


def _check_rate(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a probability, got {value}")


def _check_range(name: str, value: MillisecondRange) -> None:
    low, high = value
    if low < 0:
        raise ValueError(f"{name} cannot be negative, got {value}")
    if high < low:
        raise ValueError(f"{name} is inverted, got {value}")


@dataclass(frozen=True, slots=True)
class FaultConfig:
    """The faults a simulation may inject, and how often."""

    latency_ms: MillisecondRange = (1, 20)
    """Delay applied to every message, drawn uniformly."""

    drop_rate: float = 0.0
    """Probability that a message is never delivered."""

    dup_rate: float = 0.0
    """Probability that a message is delivered twice, at independent delays."""

    partition_rate: float = 0.0
    """Probability, per tick, of cutting the cluster in two."""

    partition_duration_ms: MillisecondRange = (200, 2_000)

    crash_rate: float = 0.0
    """Probability, per tick, that one node loses its volatile state."""

    crash_duration_ms: MillisecondRange = (100, 1_000)

    pause_rate: float = 0.0
    """Probability, per tick, that one node stops processing without crashing."""

    pause_duration_ms: MillisecondRange = (50, 500)

    clock_skew_ms: int = 0
    """Bound on the per-node clock offset, drawn once when the run starts."""

    tick_ms: int = 100
    """How often the injector wakes up to roll its dice."""

    def __post_init__(self) -> None:
        _check_range("latency_ms", self.latency_ms)
        _check_range("partition_duration_ms", self.partition_duration_ms)
        _check_range("crash_duration_ms", self.crash_duration_ms)
        _check_range("pause_duration_ms", self.pause_duration_ms)
        _check_rate("drop_rate", self.drop_rate)
        _check_rate("dup_rate", self.dup_rate)
        _check_rate("partition_rate", self.partition_rate)
        _check_rate("crash_rate", self.crash_rate)
        _check_rate("pause_rate", self.pause_rate)
        if self.clock_skew_ms < 0:
            raise ValueError(f"clock_skew_ms cannot be negative, got {self.clock_skew_ms}")
        if self.tick_ms <= 0:
            raise ValueError(f"tick_ms must be positive, got {self.tick_ms}")

    @property
    def injects_anything(self) -> bool:
        """Whether the injector has any reason to wake up at all."""
        return bool(self.partition_rate or self.crash_rate or self.pause_rate)

    def without_faults(self) -> FaultConfig:
        """The same latency profile with every fault switched off.

        The floor the shrinker works towards, and the configuration used to
        assert that a healthy network produces linearizable histories.
        """
        return FaultConfig(latency_ms=self.latency_ms, tick_ms=self.tick_ms)

    def but(self, **changes: object) -> FaultConfig:
        """A copy with some fields replaced."""
        return replace(self, **changes)  # type: ignore[arg-type]

    def to_json(self) -> JsonDict:
        """Render for the trace envelope, with ranges as two-element lists."""
        raw = asdict(self)
        return {
            key: list(value) if isinstance(value, tuple) else value for key, value in raw.items()
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> FaultConfig:
        """Rebuild from a trace envelope."""
        fields: dict[str, object] = {}
        for key, value in data.items():
            fields[key] = (value[0], value[1]) if isinstance(value, list) else value
        return cls(**fields)  # type: ignore[arg-type]


PERFECT_NETWORK = FaultConfig(latency_ms=(1, 1))
"""No jitter, no loss, no faults. Used to assert the KV is correct at all."""

PARTITION = "partition"
CRASH = "crash"
PAUSE = "pause"


@dataclass(frozen=True, slots=True)
class InjectedFault:
    """One decision the adversary took, written down.

    A list of these is a fault schedule: everything the injector would have
    done, at absolute times, with no dice left to roll. It is what makes a run
    replayable without the injector, and therefore what makes it shrinkable —
    the reducer deletes entries from a list rather than trying to talk a random
    number generator out of a decision.
    """

    at_ms: int
    kind: str
    duration_ms: int
    targets: tuple[int, ...]

    def describe(self) -> str:
        """One line, the way it would be read out loud."""
        if self.kind == PARTITION:
            side = ", ".join(f"n{node}" for node in self.targets)
            return f"partition {{{side}}} away for {self.duration_ms}ms"
        return f"{self.kind} n{self.targets[0]} for {self.duration_ms}ms"

    def to_json(self) -> JsonDict:
        """Render for the trace and for a reduced scenario."""
        return {
            "at_ms": self.at_ms,
            "kind": self.kind,
            "duration_ms": self.duration_ms,
            "targets": list(self.targets),
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> InjectedFault:
        """Rebuild from the stored form."""
        targets = data["targets"]
        assert isinstance(targets, list)
        return cls(
            at_ms=int(str(data["at_ms"])),
            kind=str(data["kind"]),
            duration_ms=int(str(data["duration_ms"])),
            targets=tuple(int(str(node)) for node in targets),
        )
