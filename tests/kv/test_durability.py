"""What has to survive a reboot, and what is allowed not to."""

from cassette.kv.config import StoreConfig
from cassette.sim.faults import FaultConfig
from tests.kv.cluster import Cluster

FIVE = StoreConfig(replicas=5, read_quorum=3, write_quorum=3)


def test_an_acknowledged_write_survives_a_crash_of_its_coordinator() -> None:
    cluster = Cluster(store=FIVE)
    cluster.write("x", 1, coordinator=0)
    cluster.sim.schedule_crash(0, downtime_ms=200)
    cluster.sim.run()
    assert cluster.read("x", coordinator=1).value == 1


def test_an_acknowledged_write_survives_a_crash_of_a_minority() -> None:
    cluster = Cluster(store=FIVE)
    cluster.write("x", 1)
    for node_id in (2, 3):
        cluster.sim.schedule_crash(node_id, downtime_ms=200)
    cluster.sim.run()
    assert cluster.read("x").value == 1


def test_an_acknowledged_write_survives_a_full_cluster_bounce() -> None:
    cluster = Cluster(store=FIVE)
    cluster.write("x", 1)
    for node_id in FIVE.replica_ids:
        cluster.sim.schedule_crash(node_id, downtime_ms=200)
    cluster.sim.run()
    assert cluster.read("x").value == 1


def test_a_crash_does_not_resurrect_an_older_value() -> None:
    cluster = Cluster(store=FIVE)
    cluster.write("x", 1)
    cluster.write("x", 2)
    for node_id in FIVE.replica_ids:
        cluster.sim.schedule_crash(node_id, downtime_ms=200)
    cluster.sim.run()
    assert cluster.read("x").value == 2


def test_a_restarted_replica_catches_up_on_the_next_write() -> None:
    cluster = Cluster(store=FIVE)
    cluster.sim.schedule_crash(4, downtime_ms=400)
    cluster.sim.run(until_ms=0)
    cluster.write("x", 1)
    assert cluster.replicas[4].stored("x").value is None
    cluster.sim.run()
    cluster.write("x", 2)
    assert cluster.replicas[4].stored("x").value == 2


def test_a_replica_that_missed_a_write_does_not_serve_a_stale_quorum() -> None:
    cluster = Cluster(store=FIVE)
    cluster.write("x", 1)
    cluster.sim.schedule_crash(0, downtime_ms=100)
    cluster.sim.schedule_crash(1, downtime_ms=100)
    cluster.sim.run()
    assert cluster.read("x", coordinator=2).value == 1


def test_writes_land_across_repeated_crashes() -> None:
    cluster = Cluster(store=FIVE, faults=FaultConfig(latency_ms=(1, 10)))
    for round_number in range(1, 6):
        cluster.sim.schedule_crash(round_number % 4 + 1, downtime_ms=50)
        assert cluster.write("x", round_number, coordinator=0).ok is True
    assert cluster.read("x").value == 5


def test_a_coordinator_crash_leaves_the_client_with_no_answer() -> None:
    """The round lived in volatile state. Nobody is left to send the reply.

    This is why a client keeps its own patience timer, and why an operation
    with no answer has to be recorded as unknown rather than dropped.
    """
    cluster = Cluster(store=FIVE)
    req = cluster.request("write", "x", 1, coordinator=0)
    cluster.sim.run(max_events=2)
    cluster.sim.schedule_crash(0, downtime_ms=50)
    cluster.sim.run()
    assert all(reply.req != req for reply in cluster.mailbox.replies)
