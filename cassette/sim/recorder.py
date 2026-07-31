"""Turning a run into bytes.

The recorder is an `Observer` that timestamps whatever the engine reports and
keeps it in order. Its real job is the `digest`: a SHA-256 over the canonical
rendering of the whole run, which is what the determinism test compares. Two
runs of a seed either produce the same 64 hex characters or the project's
central claim is false.

Canonical means `sort_keys=True` and no whitespace. Key order in a Python dict
is insertion order, and insertion order is a property of the code that happened
to build the dict; sorting removes that from the answer entirely.
"""

from __future__ import annotations

import hashlib
import json

from cassette.sim.clock import VirtualClock
from cassette.sim.types import JsonDict, JsonValue


def canonical_json(value: JsonValue) -> str:
    """Render `value` so that equal data always produces equal text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_of(value: JsonValue) -> str:
    """The SHA-256 of the canonical rendering, as hex."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Recorder:
    """Collects every reported event, in order, with its logical timestamp."""

    __slots__ = ("_clock", "events")

    def __init__(self, clock: VirtualClock) -> None:
        self._clock = clock
        self.events: list[JsonDict] = []

    def record(self, event_type: str, **fields: JsonValue) -> None:
        """Append one event. Called by the engine, never by a node."""
        entry: JsonDict = {"t": self._clock.now, "type": event_type}
        entry.update(fields)
        self.events.append(entry)

    def digest(self) -> str:
        """A fingerprint of everything recorded so far."""
        return digest_of(list(self.events))

    def __len__(self) -> int:
        return len(self.events)
