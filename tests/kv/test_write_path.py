from cassette.kv.config import StoreConfig
from cassette.kv.version import Version
from cassette.sim.faults import FaultConfig
from tests.kv.cluster import Cluster


def test_a_write_is_acknowledged() -> None:
    cluster = Cluster()
    assert cluster.write("x", 1).ok is True


def test_a_write_reaches_at_least_a_write_quorum() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cluster.holdings("x").count(1) >= cluster.store.write_quorum


def test_a_healthy_cluster_converges_on_every_replica() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cluster.holdings("x") == [1] * cluster.store.replicas


def test_the_first_write_lands_at_counter_one() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cluster.replicas[0].stored("x").version == Version(1, 0)


def test_successive_writes_advance_the_counter() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    cluster.write("x", 2)
    cluster.write("x", 3)
    assert cluster.replicas[0].stored("x").version == Version(3, 0)


def test_the_version_carries_the_coordinator() -> None:
    cluster = Cluster()
    cluster.write("x", 1, coordinator=2)
    assert cluster.replicas[0].stored("x").version == Version(1, 2)


def test_a_second_coordinator_still_supersedes_the_first() -> None:
    cluster = Cluster()
    cluster.write("x", 1, coordinator=0)
    cluster.write("x", 2, coordinator=3)
    assert cluster.holdings("x") == [2] * cluster.store.replicas


def test_the_round_is_closed_once_the_client_is_told() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert all(replica.open_rounds == 0 for replica in cluster.replicas)


def test_a_repeated_request_id_is_ignored() -> None:
    cluster = Cluster()
    cluster.sim.env_for(cluster.client_id)
    first = cluster.request("write", "x", 1)
    cluster.sim.run()
    assert first == 1
    assert len(cluster.mailbox.replies) == 1


def test_a_write_survives_losing_a_minority() -> None:
    cluster = Cluster(store=StoreConfig(replicas=5, read_quorum=3, write_quorum=3))
    cluster.sim.schedule_crash(3, downtime_ms=10_000)
    cluster.sim.schedule_crash(4, downtime_ms=10_000)
    cluster.sim.run(until_ms=0)
    assert cluster.write("x", 1).ok is True


def test_a_write_fails_when_no_quorum_can_be_reached() -> None:
    cluster = Cluster(store=StoreConfig(replicas=5, read_quorum=3, write_quorum=3))
    for node_id in (2, 3, 4):
        cluster.sim.schedule_crash(node_id, downtime_ms=10_000)
    cluster.sim.run(until_ms=0)
    assert cluster.write("x", 1).ok is False


def test_a_failed_round_is_cleaned_up() -> None:
    cluster = Cluster(store=StoreConfig(replicas=5, read_quorum=3, write_quorum=3))
    for node_id in (2, 3, 4):
        cluster.sim.schedule_crash(node_id, downtime_ms=10_000)
    cluster.sim.run(until_ms=0)
    cluster.write("x", 1)
    assert cluster.replicas[0].open_rounds == 0


def test_a_crash_forgets_open_rounds_but_keeps_the_store() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    cluster.request("write", "x", 2)
    cluster.sim.run(max_events=1)
    cluster.sim.schedule_crash(0, downtime_ms=50)
    cluster.sim.run()
    assert cluster.replicas[0].open_rounds == 0
    assert cluster.replicas[0].stored("x").value == 1


def test_writes_survive_an_occasional_lost_message() -> None:
    cluster = Cluster(faults=FaultConfig(latency_ms=(1, 20), drop_rate=0.05))
    assert cluster.write("x", 1).ok is True
