from __future__ import annotations

from pathlib import Path

from cassette import corpus
from cassette.fuzz import Plan, fuzz, probe
from cassette.kv.config import StoreConfig
from cassette.scenario import QUIET, STANDARD, WorkloadSpec
from cassette.sim.faults import PERFECT_NETWORK
from tests.broken import BROKEN

# Both known defects are fixed, so a fuzzer pointed at the current store finds
# nothing — which is the point, and useless for testing the fuzzer. These plans
# use the --buggy store, the same switch docs/FINDINGS.md documents.
STANDARD_PLAN = Plan(preset="standard-buggy", store=BROKEN, faults=STANDARD)
QUIET_PLAN = Plan(preset="quiet-buggy", store=BROKEN, faults=QUIET)
PERFECT_PLAN = Plan(preset="quiet-buggy", store=BROKEN, faults=PERFECT_NETWORK)
FIXED_PLAN = Plan(preset="standard", faults=STANDARD)


def test_a_network_with_no_jitter_at_all_produces_no_violations() -> None:
    """Fixed latency makes the bus FIFO, and nothing overlaps enough to break."""
    assert fuzz(range(300), PERFECT_PLAN, stop_at_first=False).clean is True


def test_a_faulty_network_produces_violations() -> None:
    assert fuzz(range(400), STANDARD_PLAN, stop_at_first=False).findings


def test_the_fixed_store_survives_the_same_seeds() -> None:
    """The other half of the claim. Same faults, same seeds, nothing found."""
    assert fuzz(range(2_000), FIXED_PLAN, stop_at_first=False).clean is True


def test_jitter_alone_is_enough_to_produce_violations() -> None:
    """No loss, no partitions, no crashes. Variable latency is the whole fault."""
    assert fuzz(range(500), QUIET_PLAN, stop_at_first=False).findings


def test_the_first_violation_stops_the_search_by_default() -> None:
    report = fuzz(range(400), STANDARD_PLAN)
    assert len(report.findings) == 1
    assert report.explored < 400


def test_the_same_seeds_find_the_same_violations() -> None:
    left = fuzz(range(400), STANDARD_PLAN, stop_at_first=False)
    right = fuzz(range(400), STANDARD_PLAN, stop_at_first=False)
    assert [f.seed for f in left.findings] == [f.seed for f in right.findings]


def test_workers_do_not_change_the_answer() -> None:
    """The pool decides who computes what, never what the answer is."""
    serial = fuzz(range(400), STANDARD_PLAN, workers=1, stop_at_first=False)
    parallel = fuzz(range(400), STANDARD_PLAN, workers=4, stop_at_first=False)
    assert [f.seed for f in serial.findings] == [f.seed for f in parallel.findings]
    assert [f.explanation for f in serial.findings] == [f.explanation for f in parallel.findings]


def test_a_finding_names_the_seed_and_the_operation() -> None:
    finding = fuzz(range(400), STANDARD_PLAN).findings[0]
    assert finding.seed >= 0
    assert finding.key in ("x", "y")
    assert finding.operation is not None
    assert str(finding).startswith(f"seed {finding.seed}")


def test_a_single_seed_can_be_probed_on_its_own() -> None:
    seed = fuzz(range(400), STANDARD_PLAN).findings[0].seed
    _, finding, undecided = probe((seed, STANDARD_PLAN))
    assert finding is not None
    assert undecided is False


def test_a_clean_seed_probes_clean() -> None:
    assert probe((0, PERFECT_PLAN)) == (0, None, False)


def test_progress_is_reported_for_every_seed() -> None:
    seen: list[int] = []
    fuzz(range(50), PERFECT_PLAN, stop_at_first=False, on_result=lambda s, _: seen.append(s))
    assert seen == list(range(50))


def test_throughput_is_reported() -> None:
    assert fuzz(range(50), PERFECT_PLAN, stop_at_first=False).throughput > 0


def test_a_harsher_preset_finds_more() -> None:
    mild = fuzz(range(600), QUIET_PLAN, stop_at_first=False).findings
    rough = fuzz(range(600), STANDARD_PLAN, stop_at_first=False).findings
    assert len(rough) > len(mild)


# -- the corpus -----------------------------------------------------------


def test_an_entry_round_trips_through_its_line() -> None:
    entry = corpus.Entry(seed=161, preset="harsh", nodes=3, clients=2, note="stale read on x")
    assert corpus.Entry.from_line(entry.to_line()) == entry


def test_a_note_is_optional() -> None:
    entry = corpus.Entry(seed=1)
    assert "#" not in entry.to_line()
    assert corpus.Entry.from_line(entry.to_line()) == entry


def test_a_missing_corpus_is_empty_rather_than_an_error(tmp_path: Path) -> None:
    assert corpus.load(tmp_path / "nothing.txt") == []


def test_saving_and_loading_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "regressions.txt"
    entries = [corpus.Entry(seed=7), corpus.Entry(seed=3, preset="harsh")]
    corpus.save(entries, path)
    assert sorted(corpus.load(path), key=lambda e: e.seed) == sorted(entries, key=lambda e: e.seed)


def test_the_corpus_is_written_in_a_stable_order(tmp_path: Path) -> None:
    path = tmp_path / "regressions.txt"
    corpus.save([corpus.Entry(seed=9), corpus.Entry(seed=2)], path)
    first = path.read_text(encoding="utf-8")
    corpus.save([corpus.Entry(seed=2), corpus.Entry(seed=9)], path)
    assert path.read_text(encoding="utf-8") == first


def test_adding_a_known_seed_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "regressions.txt"
    corpus.save([corpus.Entry(seed=7)], path)
    assert corpus.add([corpus.Entry(seed=7)], path) == 0
    assert len(corpus.load(path)) == 1


def test_the_same_seed_under_a_different_preset_is_a_different_entry(tmp_path: Path) -> None:
    path = tmp_path / "regressions.txt"
    corpus.save([corpus.Entry(seed=7, preset="quiet")], path)
    assert corpus.add([corpus.Entry(seed=7, preset="harsh")], path) == 1


def test_comments_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "regressions.txt"
    path.write_text("# a note\n\nseed=5 preset=quiet\n", encoding="utf-8")
    assert [entry.seed for entry in corpus.load(path)] == [5]


def test_an_entry_rebuilds_its_scenario() -> None:
    entry = corpus.Entry(seed=161, nodes=5, clients=3, operations=8)
    scenario = entry.to_scenario()
    assert scenario.seed == 161
    assert scenario.store.replicas == 5
    assert scenario.operation_count == 24


def test_a_plan_describes_its_own_corpus_entry() -> None:
    plan = Plan(
        preset="harsh",
        store=StoreConfig(replicas=3, read_quorum=2, write_quorum=2),
        workload=WorkloadSpec(clients=2, operations=4),
    )
    entry = plan.entry_for(42, "boom")
    assert (entry.seed, entry.nodes, entry.clients, entry.note) == (42, 3, 2, "boom")
    assert entry.to_scenario().store.replicas == 3
