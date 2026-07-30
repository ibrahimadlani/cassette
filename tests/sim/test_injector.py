import pytest

from cassette.sim.faults import FaultConfig
from cassette.sim.injector import FaultInjector
from cassette.sim.observer import Observer
from cassette.sim.simulation import Simulation
from cassette.sim.types import JsonValue
from tests.fakes import RecordingNode

CLUSTER = 5
HORIZON_MS = 30_000


class Log:
    """An observer that keeps the event types it was told about."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, JsonValue]]] = []

    def record(self, event_type: str, **fields: JsonValue) -> None:
        self.entries.append((event_type, dict(fields)))

    def types(self) -> list[str]:
        return [event_type for event_type, _ in self.entries]


def run(config: FaultConfig, seed: int = 8421) -> Log:
    log = Log()
    observer: Observer = log
    sim = Simulation(seed=seed, config=config, observer=observer)
    for node_id in range(CLUSTER):
        sim.add_node(RecordingNode(node_id=node_id))
    FaultInjector(sim, sim.node_ids).start()
    sim.run(until_ms=HORIZON_MS)
    return log


def test_a_quiet_config_never_arms_the_injector() -> None:
    assert run(FaultConfig()).entries == []


def test_partitions_open_and_close() -> None:
    types = run(FaultConfig(partition_rate=0.05)).types()
    assert types.count("partition_start") > 0
    assert types.count("partition_end") == types.count("partition_start")


def test_a_second_partition_never_opens_over_the_first() -> None:
    log = run(FaultConfig(partition_rate=0.5, partition_duration_ms=(2_000, 4_000)))
    depth = 0
    for event_type, _ in log.entries:
        if event_type == "partition_start":
            depth += 1
        elif event_type == "partition_end":
            depth -= 1
        assert 0 <= depth <= 1


def test_a_split_always_has_two_non_empty_groups() -> None:
    log = run(FaultConfig(partition_rate=0.05))
    splits = [
        fields["groups"] for event_type, fields in log.entries if event_type.endswith("start")
    ]
    assert splits
    for groups in splits:
        assert isinstance(groups, list)
        assert len(groups) == 2
        assert all(group for group in groups)
        assert sum(len(group) for group in groups) == CLUSTER


def test_crashes_are_followed_by_restarts() -> None:
    types = run(FaultConfig(crash_rate=0.05)).types()
    assert types.count("node_crash") > 0
    assert types.count("node_restart") == types.count("node_crash")


def test_pauses_are_followed_by_resumes() -> None:
    types = run(FaultConfig(pause_rate=0.05)).types()
    assert types.count("node_pause") > 0
    assert types.count("node_resume") == types.count("node_pause")


def test_the_same_seed_injects_the_same_faults() -> None:
    config = FaultConfig(partition_rate=0.05, crash_rate=0.05, pause_rate=0.05)
    assert run(config).entries == run(config).entries


def test_different_seeds_injects_different_faults() -> None:
    config = FaultConfig(partition_rate=0.05, crash_rate=0.05, pause_rate=0.05)
    assert run(config, seed=1).entries != run(config, seed=2).entries


def test_a_higher_rate_breaks_more() -> None:
    rare = run(FaultConfig(crash_rate=0.01)).types().count("node_crash")
    often = run(FaultConfig(crash_rate=0.20)).types().count("node_crash")
    assert often > rare


def test_a_cluster_of_one_cannot_be_split() -> None:
    sim = Simulation(seed=1, config=FaultConfig(partition_rate=0.5))
    sim.add_node(RecordingNode(node_id=0))
    with pytest.raises(ValueError, match="at least two replicas"):
        FaultInjector(sim, sim.node_ids)
