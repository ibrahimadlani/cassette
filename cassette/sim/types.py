"""Types shared between the simulator and the systems it runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias

NodeId: TypeAlias = int
"""Identifier of a participant. Replicas take the low ids, clients the high ones."""

JsonValue: TypeAlias = (
    "str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None"
)
"""Anything `json.dumps` will accept.

Deliberately spelled with the covariant `Sequence` and `Mapping` rather than
`list` and `dict`: a `list[int]` is not a `list[JsonValue]` under invariance,
and every second call site would need a cast.
"""

JsonDict: TypeAlias = "dict[str, JsonValue]"


class Payload(Protocol):
    """A message body.

    The simulator moves payloads around, delays them, drops them and writes
    them to the trace. It never looks inside one beyond these two members, so
    the system under test is free to model its protocol however it likes.
    """

    @property
    def kind(self) -> str:
        """A short stable tag used in traces and in the replayer."""

    def to_json(self) -> JsonDict:
        """Render the body for the trace. Must be deterministic."""
