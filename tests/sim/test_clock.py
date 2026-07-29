import pytest

from cassette.sim.clock import VirtualClock


def test_starts_at_zero_by_default() -> None:
    assert VirtualClock().now == 0


def test_starts_at_an_explicit_timestamp() -> None:
    assert VirtualClock(1_500).now == 1_500


def test_rejects_a_negative_start() -> None:
    with pytest.raises(ValueError, match="before zero"):
        VirtualClock(-1)


def test_advances_to_a_later_timestamp() -> None:
    clock = VirtualClock()
    clock.advance_to(40)
    assert clock.now == 40


def test_advancing_to_the_current_time_is_allowed() -> None:
    clock = VirtualClock(40)
    clock.advance_to(40)
    assert clock.now == 40


def test_refuses_to_move_backwards() -> None:
    clock = VirtualClock(40)
    with pytest.raises(ValueError, match="back to 39"):
        clock.advance_to(39)


def test_jumps_are_free() -> None:
    clock = VirtualClock()
    clock.advance_to(6 * 60 * 60 * 1_000)
    assert clock.now == 21_600_000
