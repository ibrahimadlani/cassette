from typing import Any

import pytest

from cassette.sim.faults import PERFECT_NETWORK, FaultConfig


def build(**overrides: Any) -> FaultConfig:
    return FaultConfig(**overrides)


def test_defaults_inject_nothing() -> None:
    assert FaultConfig().injects_anything is False


def test_a_configured_rate_wakes_the_injector() -> None:
    assert FaultConfig(partition_rate=0.01).injects_anything is True


def test_without_faults_keeps_the_latency_profile() -> None:
    config = FaultConfig(latency_ms=(3, 30), drop_rate=0.2, crash_rate=0.1, tick_ms=50)
    stripped = config.without_faults()
    assert stripped.latency_ms == (3, 30)
    assert stripped.tick_ms == 50
    assert stripped.drop_rate == 0.0
    assert stripped.injects_anything is False


def test_but_replaces_a_single_field() -> None:
    config = FaultConfig(drop_rate=0.2)
    assert config.but(drop_rate=0.0).drop_rate == 0.0
    assert config.drop_rate == 0.2


def test_the_perfect_network_has_no_jitter() -> None:
    assert PERFECT_NETWORK.latency_ms == (1, 1)
    assert PERFECT_NETWORK.injects_anything is False


def test_json_round_trip_is_lossless() -> None:
    config = FaultConfig(
        latency_ms=(2, 45),
        drop_rate=0.1,
        dup_rate=0.05,
        partition_rate=0.02,
        partition_duration_ms=(300, 900),
        crash_rate=0.01,
        pause_rate=0.03,
        clock_skew_ms=250,
        tick_ms=25,
    )
    assert FaultConfig.from_json(config.to_json()) == config


def test_ranges_serialise_as_lists() -> None:
    assert FaultConfig().to_json()["latency_ms"] == [1, 20]


@pytest.mark.parametrize(
    "field",
    ["drop_rate", "dup_rate", "partition_rate", "crash_rate", "pause_rate"],
)
def test_rates_must_be_probabilities(field: str) -> None:
    with pytest.raises(ValueError, match="must be a probability"):
        build(**{field: 1.5})


@pytest.mark.parametrize(
    "field",
    ["latency_ms", "partition_duration_ms", "crash_duration_ms", "pause_duration_ms"],
)
def test_ranges_must_not_be_inverted(field: str) -> None:
    with pytest.raises(ValueError, match="is inverted"):
        build(**{field: (20, 5)})


def test_a_negative_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        FaultConfig(latency_ms=(-5, 5))


def test_a_negative_skew_is_rejected() -> None:
    with pytest.raises(ValueError, match="clock_skew_ms cannot be negative"):
        FaultConfig(clock_skew_ms=-1)


def test_the_tick_must_be_positive() -> None:
    with pytest.raises(ValueError, match="tick_ms must be positive"):
        FaultConfig(tick_ms=0)
