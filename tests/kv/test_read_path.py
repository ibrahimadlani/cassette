from cassette.kv.config import StoreConfig
from cassette.sim.faults import FaultConfig
from tests.kv.cluster import Cluster


def test_an_unwritten_key_reads_as_absent() -> None:
    cluster = Cluster()
    reply = cluster.read("x")
    assert reply.ok is True
    assert reply.value is None


def test_a_write_is_visible_to_a_later_read() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cluster.read("x").value == 1


def test_the_latest_write_wins() -> None:
    cluster = Cluster()
    for value in (1, 2, 3):
        cluster.write("x", value)
    assert cluster.read("x").value == 3


def test_a_read_can_be_coordinated_by_any_replica() -> None:
    cluster = Cluster()
    cluster.write("x", 7, coordinator=0)
    assert [cluster.read("x", coordinator=node).value for node in (1, 2, 3, 4)] == [7, 7, 7, 7]


def test_keys_do_not_interfere() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    cluster.write("y", 2)
    assert (cluster.read("x").value, cluster.read("y").value) == (1, 2)


def test_a_read_survives_a_crashed_minority() -> None:
    cluster = Cluster(store=StoreConfig(replicas=5, read_quorum=3, write_quorum=3))
    cluster.write("x", 1)
    cluster.sim.schedule_crash(3, downtime_ms=10_000)
    cluster.sim.schedule_crash(4, downtime_ms=10_000)
    cluster.sim.run(until_ms=0)
    assert cluster.read("x").value == 1


def test_a_read_fails_without_a_quorum() -> None:
    cluster = Cluster(store=StoreConfig(replicas=5, read_quorum=3, write_quorum=3))
    cluster.write("x", 1)
    for node_id in (2, 3, 4):
        cluster.sim.schedule_crash(node_id, downtime_ms=10_000)
    cluster.sim.run(until_ms=0)
    assert cluster.read("x").ok is False


def test_a_read_closes_its_round() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    cluster.read("x")
    assert all(replica.open_rounds == 0 for replica in cluster.replicas)


def test_a_read_does_not_change_the_stored_version() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    before = [replica.stored("x").version for replica in cluster.replicas]
    cluster.read("x")
    assert [replica.stored("x").version for replica in cluster.replicas] == before


def test_reads_tolerate_reordering_and_jitter() -> None:
    cluster = Cluster(faults=FaultConfig(latency_ms=(1, 80)))
    cluster.write("x", 42)
    assert cluster.read("x").value == 42
