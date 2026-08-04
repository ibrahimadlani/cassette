from cassette.kv.version import ABSENT, ZERO, Stored, Version


def test_a_higher_counter_wins() -> None:
    assert Version(2, 0) > Version(1, 9)


def test_the_node_breaks_a_counter_tie() -> None:
    assert Version(1, 3) > Version(1, 1)


def test_the_order_is_total() -> None:
    versions = [Version(2, 1), Version(1, 3), Version(2, 0), Version(1, 1)]
    assert sorted(versions) == [Version(1, 1), Version(1, 3), Version(2, 0), Version(2, 1)]


def test_the_zero_version_loses_to_everything() -> None:
    assert Version(1, 0) > ZERO
    assert Version(0, -1) == ZERO


def test_next_from_supersedes_the_current_version() -> None:
    current = Version(4, 2)
    assert current.next_from(1) > current


def test_next_from_stamps_the_coordinator() -> None:
    assert Version(4, 2).next_from(1) == Version(5, 1)


def test_two_coordinators_at_the_same_counter_stay_distinguishable() -> None:
    assert ZERO.next_from(1) != ZERO.next_from(2)


def test_json_round_trip() -> None:
    version = Version(7, 3)
    assert Version.from_json(version.to_json()) == version


def test_a_version_reads_as_counter_dot_node() -> None:
    assert str(Version(7, 3)) == "7.3"


def test_an_absent_key_has_no_value() -> None:
    assert Stored(value=None, version=ZERO) == ABSENT


def test_stored_renders_for_a_trace() -> None:
    assert Stored(5, Version(2, 1)).to_json() == {"value": 5, "version": [2, 1]}
