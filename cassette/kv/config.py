"""How many replicas have to agree, and how long the coordinator waits."""

from __future__ import annotations

from dataclasses import dataclass

from cassette.sim.types import JsonDict


@dataclass(frozen=True, slots=True)
class StoreConfig:
    """The shape of the cluster and its quorum rule."""

    replicas: int = 5
    read_quorum: int = 3
    write_quorum: int = 3
    request_timeout_ms: int = 400

    stable_versions: bool = True
    """Whether a coordinator refuses to mint a version stamp twice.

    Off, two rounds it is coordinating at the same time can derive the same
    stamp for different values. See docs/FINDINGS.md.
    """

    def __post_init__(self) -> None:
        if self.replicas < 1:
            raise ValueError(f"a cluster needs at least one replica, got {self.replicas}")
        for name in ("read_quorum", "write_quorum"):
            size = getattr(self, name)
            if not 1 <= size <= self.replicas:
                raise ValueError(f"{name}={size} is impossible with {self.replicas} replicas")
        if self.request_timeout_ms <= 0:
            raise ValueError(f"request_timeout_ms must be positive, got {self.request_timeout_ms}")

    @property
    def quorums_overlap(self) -> bool:
        """Whether R + W > N, so every read quorum meets every write quorum.

        Necessary for a read to have any chance of seeing the latest write. Not
        sufficient — see docs/FINDINGS.md, which is the point of the exercise.
        """
        return self.read_quorum + self.write_quorum > self.replicas

    @property
    def replica_ids(self) -> tuple[int, ...]:
        """Replicas take the low node ids; clients take the ones above them."""
        return tuple(range(self.replicas))

    @property
    def faithful(self) -> bool:
        """Whether the known defects are switched off."""
        return self.stable_versions

    def to_json(self) -> JsonDict:
        """Render for the trace envelope."""
        return {
            "replicas": self.replicas,
            "read_quorum": self.read_quorum,
            "write_quorum": self.write_quorum,
            "request_timeout_ms": self.request_timeout_ms,
            "stable_versions": self.stable_versions,
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> StoreConfig:
        """Rebuild from a trace envelope."""
        return cls(**data)  # type: ignore[arg-type]
