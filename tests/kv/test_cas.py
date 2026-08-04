from cassette.kv.replica import NOT_SWAPPED, SWAPPED
from tests.kv.cluster import Cluster


def cas(cluster: Cluster, key: str, expected: int | None, new: int) -> int | None:
    return cluster.cas(key, expected, new).value


def test_a_matching_expectation_swaps() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cas(cluster, "x", expected=1, new=2) == SWAPPED
    assert cluster.read("x").value == 2


def test_a_mismatched_expectation_does_not_swap() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    assert cas(cluster, "x", expected=99, new=2) == NOT_SWAPPED
    assert cluster.read("x").value == 1


def test_an_absent_key_can_be_claimed() -> None:
    cluster = Cluster()
    assert cas(cluster, "x", expected=None, new=1) == SWAPPED
    assert cluster.read("x").value == 1


def test_an_absent_key_rejects_a_wrong_expectation() -> None:
    cluster = Cluster()
    assert cas(cluster, "x", expected=5, new=1) == NOT_SWAPPED
    assert cluster.read("x").value is None


def test_only_one_of_two_racing_claims_wins() -> None:
    cluster = Cluster()
    assert cas(cluster, "x", expected=None, new=1) == SWAPPED
    assert cas(cluster, "x", expected=None, new=2) == NOT_SWAPPED


def test_a_failed_swap_leaves_the_version_alone() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    before = cluster.replicas[0].stored("x").version
    cas(cluster, "x", expected=99, new=2)
    assert cluster.replicas[0].stored("x").version == before


def test_a_swap_closes_its_round() -> None:
    cluster = Cluster()
    cluster.write("x", 1)
    cas(cluster, "x", expected=1, new=2)
    assert all(replica.open_rounds == 0 for replica in cluster.replicas)
