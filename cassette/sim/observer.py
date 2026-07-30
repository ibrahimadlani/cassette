"""The hook the simulator reports through.

Keeping the reporting surface down to a single `record` call means the engine
never has to know whether anybody is listening. The fuzzer runs with the null
observer and pays nothing; the recorder plugs in when a trace is wanted.
"""

from __future__ import annotations

from typing import Protocol

from cassette.sim.types import JsonValue


class Observer(Protocol):
    """Something that wants to know what the simulation is doing."""

    def record(self, event_type: str, **fields: JsonValue) -> None:
        """Note that `event_type` happened, with whatever detail the caller has."""


class NullObserver:
    """Discards everything. The default, and the fast path."""

    __slots__ = ()

    def record(self, event_type: str, **fields: JsonValue) -> None:
        """Do nothing at all."""
        return
