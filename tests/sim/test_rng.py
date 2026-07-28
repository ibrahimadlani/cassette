import pytest

from cassette.sim.rng import Rng


def test_the_same_seed_draws_the_same_sequence() -> None:
    left = [Rng(8421).random() for _ in range(50)]
    right = [Rng(8421).random() for _ in range(50)]
    assert left == right


def test_different_seeds_diverge() -> None:
    assert Rng(1).random() != Rng(2).random()


def test_exposes_its_seed() -> None:
    assert Rng(8421).seed == 8421


def test_random_stays_in_the_unit_interval() -> None:
    rng = Rng(7)
    assert all(0.0 <= rng.random() < 1.0 for _ in range(1_000))


def test_chance_never_fires_at_zero() -> None:
    rng = Rng(7)
    assert not any(rng.chance(0.0) for _ in range(1_000))


def test_chance_always_fires_at_one() -> None:
    rng = Rng(7)
    assert all(rng.chance(1.0) for _ in range(1_000))


def test_chance_consumes_one_draw_whatever_the_probability() -> None:
    never, always = Rng(7), Rng(7)
    never.chance(0.0)
    always.chance(1.0)
    assert never.random() == always.random()


def test_randint_covers_both_bounds() -> None:
    rng = Rng(7)
    drawn = {rng.randint(0, 3) for _ in range(1_000)}
    assert drawn == {0, 1, 2, 3}


def test_randint_on_a_single_value_range() -> None:
    assert Rng(7).randint(4, 4) == 4


def test_randint_rejects_an_empty_range() -> None:
    with pytest.raises(ValueError, match=r"empty range \[5, 4\]"):
        Rng(7).randint(5, 4)


def test_choice_only_returns_members() -> None:
    rng = Rng(7)
    population = ["a", "b", "c"]
    assert all(rng.choice(population) in population for _ in range(200))


def test_choice_rejects_an_empty_population() -> None:
    with pytest.raises(ValueError, match="empty population"):
        Rng(7).choice([])
