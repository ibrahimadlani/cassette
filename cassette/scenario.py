"""Everything needed to reproduce a run, written down.

A `Scenario` is the unit the rest of the project passes around: the fuzzer
produces them from seeds, the runner executes them, the shrinker takes one
apart. It is explicit on purpose. The client operations are a list rather than
a rule for generating operations, because a list is something the shrinker can
delete an element from, and "the fourth operation client 6 would have picked"
is not.

The fault schedule is the one part that can still be implicit. `schedule=None`
means "let the injector decide from the seed", which is how a scenario starts
life. Once the injector has run, its decisions can be captured into an explicit
schedule, and from that point the run no longer needs the injector at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cassette.checker.history import CAS, READ, WRITE
from cassette.kv.client import PlannedOp
from cassette.kv.config import StoreConfig
from cassette.sim.faults import FaultConfig
from cassette.sim.rng import Rng
from cassette.sim.types import JsonDict, JsonValue, NodeId

DEFAULT_KEYS = ("x", "y")

QUIET = FaultConfig(latency_ms=(1, 20))
"""Jitter and reordering, nothing else. The baseline a store must survive."""

STANDARD = FaultConfig(
    latency_ms=(1, 40),
    drop_rate=0.02,
    dup_rate=0.01,
    partition_rate=0.04,
    partition_duration_ms=(200, 900),
    crash_rate=0.02,
    crash_duration_ms=(100, 600),
    pause_rate=0.02,
    pause_duration_ms=(50, 400),
    clock_skew_ms=50,
)
"""A bad afternoon in a real data centre."""

HARSH = FaultConfig(
    latency_ms=(1, 120),
    drop_rate=0.10,
    dup_rate=0.05,
    partition_rate=0.15,
    partition_duration_ms=(300, 1_500),
    crash_rate=0.08,
    crash_duration_ms=(100, 900),
    pause_rate=0.08,
    pause_duration_ms=(100, 800),
    clock_skew_ms=200,
)
"""Everything at once. Good for finding bugs, poor for reading the trace."""

PRESETS = {"quiet": QUIET, "standard": STANDARD, "harsh": HARSH}


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    """The shape of the client load, before it is turned into concrete operations."""

    clients: int = 3
    operations: int = 8
    keys: tuple[str, ...] = DEFAULT_KEYS
    value_range: tuple[int, int] = (1, 9)
    read_ratio: float = 0.5
    cas_ratio: float = 0.0
    think_ms: tuple[int, int] = (0, 60)

    def __post_init__(self) -> None:
        if self.clients < 1:
            raise ValueError(f"need at least one client, got {self.clients}")
        if self.operations < 1:
            raise ValueError(f"need at least one operation, got {self.operations}")
        if not self.keys:
            raise ValueError("need at least one key")
        if not 0.0 <= self.read_ratio + self.cas_ratio <= 1.0:
            raise ValueError("read_ratio + cas_ratio must be a probability")

    def to_json(self) -> JsonDict:
        """Render for the trace envelope."""
        return {
            "clients": self.clients,
            "operations": self.operations,
            "keys": list(self.keys),
            "value_range": list(self.value_range),
            "read_ratio": self.read_ratio,
            "cas_ratio": self.cas_ratio,
            "think_ms": list(self.think_ms),
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> WorkloadSpec:
        """Rebuild from a trace envelope."""
        return cls(
            clients=int(str(data["clients"])),
            operations=int(str(data["operations"])),
            keys=tuple(str(key) for key in _as_list(data["keys"])),
            value_range=_as_pair(data["value_range"]),
            read_ratio=float(str(data["read_ratio"])),
            cas_ratio=float(str(data["cas_ratio"])),
            think_ms=_as_pair(data["think_ms"]),
        )


def _as_list(raw: JsonValue) -> list[JsonValue]:
    assert isinstance(raw, list)
    return raw


def _as_pair(raw: JsonValue) -> tuple[int, int]:
    values = _as_list(raw)
    return int(str(values[0])), int(str(values[1]))


@dataclass(frozen=True, slots=True)
class Scenario:
    """A run, described completely enough to replay without an RNG."""

    seed: int
    store: StoreConfig = field(default_factory=StoreConfig)
    faults: FaultConfig = field(default_factory=FaultConfig)
    plans: tuple[tuple[PlannedOp, ...], ...] = ()
    horizon_ms: int = 60_000

    @property
    def client_ids(self) -> tuple[NodeId, ...]:
        """Clients take the node ids just above the replicas."""
        return tuple(self.store.replicas + index for index in range(len(self.plans)))

    @property
    def operation_count(self) -> int:
        """How many client operations this scenario plans in total."""
        return sum(len(plan) for plan in self.plans)

    def to_json(self) -> JsonDict:
        """Render for the trace envelope."""
        return {
            "seed": self.seed,
            "store": self.store.to_json(),
            "faults": self.faults.to_json(),
            "plans": [[op.to_json() for op in plan] for plan in self.plans],
            "horizon_ms": self.horizon_ms,
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> Scenario:
        """Rebuild from a trace envelope."""
        plans = _as_list(data["plans"])
        return cls(
            seed=int(str(data["seed"])),
            store=StoreConfig.from_json(_as_dict(data["store"])),
            faults=FaultConfig.from_json(_as_dict(data["faults"])),
            plans=tuple(
                tuple(PlannedOp.from_json(_as_dict(op)) for op in _as_list(plan)) for plan in plans
            ),
            horizon_ms=int(str(data["horizon_ms"])),
        )


def _as_dict(raw: JsonValue) -> JsonDict:
    assert isinstance(raw, dict)
    return dict(raw)


def generate(
    seed: int,
    store: StoreConfig | None = None,
    faults: FaultConfig | None = None,
    workload: WorkloadSpec | None = None,
    horizon_ms: int = 60_000,
) -> Scenario:
    """Turn a seed into a concrete scenario.

    The generator uses its own `Rng`, separate from the one the simulation will
    run with. Otherwise choosing the operations would consume draws that the
    network then never sees, and two scenarios differing only in operation
    count would inject completely different faults.
    """
    store = StoreConfig() if store is None else store
    faults = FaultConfig() if faults is None else faults
    workload = WorkloadSpec() if workload is None else workload

    rng = Rng(seed)
    plans: list[tuple[PlannedOp, ...]] = []
    for _ in range(workload.clients):
        plans.append(tuple(_plan_one(rng, workload, store) for _ in range(workload.operations)))

    return Scenario(
        seed=seed, store=store, faults=faults, plans=tuple(plans), horizon_ms=horizon_ms
    )


def _plan_one(rng: Rng, workload: WorkloadSpec, store: StoreConfig) -> PlannedOp:
    roll = rng.random()
    key = rng.choice(workload.keys)
    value = rng.randint(*workload.value_range)
    expected = rng.randint(*workload.value_range)
    coordinator = rng.choice(store.replica_ids)
    delay_ms = rng.randint(*workload.think_ms)

    if roll < workload.read_ratio:
        return PlannedOp(READ, key, coordinator=coordinator, delay_ms=delay_ms)
    if roll < workload.read_ratio + workload.cas_ratio:
        return PlannedOp(CAS, key, value, expected, coordinator, delay_ms)
    return PlannedOp(WRITE, key, value, coordinator=coordinator, delay_ms=delay_ms)
