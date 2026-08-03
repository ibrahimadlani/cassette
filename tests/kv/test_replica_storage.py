import pytest

from cassette.kv.config import StoreConfig
from cassette.kv.messages import ReadReply, ReadRequest, WriteAck, WriteRequest
from cassette.kv.replica import Replica
from cassette.kv.version import ZERO, Stored, Version
from cassette.sim.env import Env
from cassette.sim.faults import FaultConfig
from cassette.sim.simulation import Simulation
from cassette.sim.types import NodeId, Payload
from tests.fakes import Ping, RecordingNode

CLIENT = 9


def build() -> tuple[Simulation, Replica, list[ReadReply | WriteAck]]:
    sim = Simulation(seed=1, config=FaultConfig(latency_ms=(1, 1)))
    replica = Replica(node_id=0)
    inbox: list[ReadReply | WriteAck] = []

    class Mailbox(RecordingNode):
        def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
            assert isinstance(msg, ReadReply | WriteAck)
            inbox.append(msg)

    sim.add_node(replica)
    sim.add_node(Mailbox(node_id=CLIENT))
    return sim, replica, inbox


def test_an_unknown_key_reads_as_absent() -> None:
    sim, _replica, inbox = build()
    sim.env_for(CLIENT).send(0, ReadRequest(req=1, key="x"))
    sim.run()
    assert inbox == [ReadReply(req=1, key="x", value=None, version=ZERO)]


def test_a_write_is_stored_and_acknowledged() -> None:
    sim, replica, inbox = build()
    sim.env_for(CLIENT).send(0, WriteRequest(req=1, key="x", value=5, version=Version(1, 2)))
    sim.run()
    assert replica.stored("x") == Stored(5, Version(1, 2))
    assert inbox == [WriteAck(req=1, key="x", version=Version(1, 2))]


def test_a_stored_value_reads_back() -> None:
    sim, _replica, inbox = build()
    env = sim.env_for(CLIENT)
    env.send(0, WriteRequest(req=1, key="x", value=5, version=Version(1, 2)))
    sim.run()
    env.send(0, ReadRequest(req=2, key="x"))
    sim.run()
    assert inbox[-1] == ReadReply(req=2, key="x", value=5, version=Version(1, 2))


def test_a_newer_version_wins() -> None:
    sim, replica, _ = build()
    env = sim.env_for(CLIENT)
    env.send(0, WriteRequest(req=1, key="x", value=5, version=Version(1, 0)))
    env.send(0, WriteRequest(req=2, key="x", value=6, version=Version(2, 0)))
    sim.run()
    assert replica.stored("x") == Stored(6, Version(2, 0))


def test_an_older_version_is_ignored() -> None:
    sim, replica, _ = build()
    env = sim.env_for(CLIENT)
    env.send(0, WriteRequest(req=1, key="x", value=6, version=Version(2, 0)))
    sim.run()
    env.send(0, WriteRequest(req=2, key="x", value=5, version=Version(1, 0)))
    sim.run()
    assert replica.stored("x") == Stored(6, Version(2, 0))


def test_an_older_version_is_still_acknowledged() -> None:
    sim, _, inbox = build()
    env = sim.env_for(CLIENT)
    env.send(0, WriteRequest(req=1, key="x", value=6, version=Version(2, 0)))
    sim.run()
    env.send(0, WriteRequest(req=2, key="x", value=5, version=Version(1, 0)))
    sim.run()
    assert inbox[-1] == WriteAck(req=2, key="x", version=Version(1, 0))


def test_a_replayed_write_is_idempotent() -> None:
    sim, replica, _ = build()
    env = sim.env_for(CLIENT)
    for _ in range(3):
        env.send(0, WriteRequest(req=1, key="x", value=5, version=Version(1, 0)))
    sim.run()
    assert replica.stored("x") == Stored(5, Version(1, 0))


def test_keys_are_independent() -> None:
    sim, replica, _ = build()
    env = sim.env_for(CLIENT)
    env.send(0, WriteRequest(req=1, key="x", value=1, version=Version(1, 0)))
    env.send(0, WriteRequest(req=2, key="y", value=2, version=Version(1, 0)))
    sim.run()
    assert replica.keys == ["x", "y"]


def test_the_store_survives_a_crash() -> None:
    sim, replica, _ = build()
    sim.env_for(CLIENT).send(0, WriteRequest(req=1, key="x", value=5, version=Version(1, 0)))
    sim.run()
    sim.schedule_crash(0, downtime_ms=50)
    sim.run()
    assert replica.stored("x") == Stored(5, Version(1, 0))


def test_unknown_payloads_are_ignored() -> None:
    sim, _, inbox = build()
    sim.env_for(CLIENT).send(0, Ping())
    sim.run()
    assert inbox == []


def test_a_quorum_larger_than_the_cluster_is_rejected() -> None:
    with pytest.raises(ValueError, match="impossible with 3 replicas"):
        StoreConfig(replicas=3, read_quorum=4)


def test_quorum_overlap_is_reported() -> None:
    assert StoreConfig(replicas=5, read_quorum=3, write_quorum=3).quorums_overlap is True
    assert StoreConfig(replicas=5, read_quorum=2, write_quorum=3).quorums_overlap is False


def test_replica_ids_start_at_zero() -> None:
    assert StoreConfig(replicas=3).replica_ids == (0, 1, 2)


def test_store_config_round_trips_through_json() -> None:
    config = StoreConfig(replicas=3, read_quorum=2, write_quorum=2, request_timeout_ms=250)
    assert StoreConfig.from_json(config.to_json()) == config


def test_an_empty_cluster_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one replica"):
        StoreConfig(replicas=0)


def test_a_zero_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        StoreConfig(request_timeout_ms=0)
