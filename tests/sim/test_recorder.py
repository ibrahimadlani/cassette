from cassette.sim.clock import VirtualClock
from cassette.sim.recorder import Recorder, canonical_json, digest_of


def test_events_are_stamped_with_logical_time() -> None:
    clock = VirtualClock()
    recorder = Recorder(clock)
    recorder.record("msg_send", id=0)
    clock.advance_to(42)
    recorder.record("msg_deliver", id=0)
    assert [entry["t"] for entry in recorder.events] == [0, 42]


def test_the_event_type_is_kept_alongside_the_fields() -> None:
    recorder = Recorder(VirtualClock())
    recorder.record("msg_drop", id=7, reason="loss")
    assert recorder.events == [{"t": 0, "type": "msg_drop", "id": 7, "reason": "loss"}]


def test_order_is_preserved() -> None:
    recorder = Recorder(VirtualClock())
    for i in range(5):
        recorder.record("tick", n=i)
        assert len(recorder) == i + 1
    assert [entry["n"] for entry in recorder.events] == [0, 1, 2, 3, 4]


def test_canonical_json_sorts_keys() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_has_no_whitespace() -> None:
    assert canonical_json([1, 2, {"a": 3}]) == '[1,2,{"a":3}]'


def test_insertion_order_does_not_change_the_digest() -> None:
    assert digest_of({"a": 1, "b": 2}) == digest_of({"b": 2, "a": 1})


def test_different_data_gives_a_different_digest() -> None:
    assert digest_of({"a": 1}) != digest_of({"a": 2})


def test_a_digest_is_sixty_four_hex_characters() -> None:
    fingerprint = digest_of({"a": 1})
    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")


def test_two_identical_recordings_agree() -> None:
    left, right = Recorder(VirtualClock()), Recorder(VirtualClock())
    for recorder in (left, right):
        recorder.record("msg_send", id=1, to=2)
        recorder.record("msg_deliver", id=1, to=2)
    assert left.digest() == right.digest()


def test_one_extra_event_changes_the_digest() -> None:
    left, right = Recorder(VirtualClock()), Recorder(VirtualClock())
    left.record("msg_send", id=1)
    right.record("msg_send", id=1)
    right.record("msg_drop", id=1)
    assert left.digest() != right.digest()
