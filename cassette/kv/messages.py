"""The wire format of the store.

Two conversations happen over these messages. A client talks to whichever
replica it picked as coordinator, and that coordinator talks to the whole
cluster to assemble a quorum. Any replica can play either role, which is what
"leaderless" means here.

Every message carries the request id it belongs to. Late replies from a round
the coordinator has already finished — or abandoned — are common once latency
and duplication are switched on, and the id is what makes them safe to ignore
rather than a source of corruption.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

from cassette.kv.version import Version
from cassette.sim.types import JsonDict, JsonValue

Key = str
Value = int | None


def _jsonify(value: object) -> JsonValue:
    if isinstance(value, Version):
        return value.to_json()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"{type(value).__name__} has no trace form")


@dataclass(frozen=True, slots=True)
class Message:
    """Base for every payload the store puts on the wire.

    Subclasses declare their fields and a `KIND`; the trace form is derived,
    so a new message cannot be added with a body that silently disagrees with
    its own definition.
    """

    KIND: ClassVar[str] = "message"

    @property
    def kind(self) -> str:
        """The stable tag used in traces and in the replayer."""
        return self.KIND

    def to_json(self) -> JsonDict:
        """Every field, with versions rendered in their list form."""
        return {field.name: _jsonify(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class ClientRequest(Message):
    """An operation a client wants performed."""

    KIND: ClassVar[str] = "client_request"

    req: int
    op: str
    key: Key
    value: Value = None
    expected: Value = None


@dataclass(frozen=True, slots=True)
class ClientReply(Message):
    """What the coordinator tells the client, once it knows."""

    KIND: ClassVar[str] = "client_reply"

    req: int
    ok: bool
    value: Value = None


@dataclass(frozen=True, slots=True)
class ReadRequest(Message):
    """Phase one: ask a replica what it holds."""

    KIND: ClassVar[str] = "read_request"

    req: int
    key: Key


@dataclass(frozen=True, slots=True)
class ReadReply(Message):
    """A replica's answer, with the stamp so the coordinator can compare."""

    KIND: ClassVar[str] = "read_reply"

    req: int
    key: Key
    value: Value
    version: Version


@dataclass(frozen=True, slots=True)
class WriteRequest(Message):
    """Phase two: install a value, if it is newer than what the replica holds."""

    KIND: ClassVar[str] = "write_request"

    req: int
    key: Key
    value: Value
    version: Version


@dataclass(frozen=True, slots=True)
class WriteAck(Message):
    """A replica confirming it has seen the write. It may have kept a newer one."""

    KIND: ClassVar[str] = "write_ack"

    req: int
    key: Key
    version: Version
