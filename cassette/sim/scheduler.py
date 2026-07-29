"""The single event queue that drives a simulation.

Events are ordered by `(time_ms, seq)`, where `seq` is a counter incremented on
every insertion. That pair is a total order: `seq` is unique by construction,
so two events can never compare equal and the queue can never fall back on an
undefined tie-break. Adding the node id to the key — a natural reflex — would
be dead weight, because the comparison never reaches a third component.

The ordering key is the whole determinism argument for this module. Anything
that pushes work into the queue is describing an interleaving; nothing else in
the process is allowed to.
"""

from __future__ import annotations

import heapq

from cassette.sim.clock import VirtualClock
from cassette.sim.events import Action, Event
from cassette.sim.types import NodeId


class Scheduler:
    """A priority queue of pending events, with lazy cancellation."""

    __slots__ = ("_cancelled", "_clock", "_heap", "_seq")

    def __init__(self, clock: VirtualClock) -> None:
        self._clock = clock
        self._heap: list[tuple[int, int, Event]] = []
        self._cancelled: set[int] = set()
        self._seq = 0

    def schedule(self, delay_ms: int, node: NodeId, action: Action) -> int:
        """Queue `action` for `node`, `delay_ms` from now.

        Returns:
            The sequence number, which is also the cancellation handle.
        """
        if delay_ms < 0:
            raise ValueError(f"cannot schedule {delay_ms}ms in the past")
        return self.schedule_at(self._clock.now + delay_ms, node, action)

    def schedule_at(self, time_ms: int, node: NodeId, action: Action) -> int:
        """Queue `action` for `node` at an absolute logical timestamp."""
        if time_ms < self._clock.now:
            raise ValueError(f"cannot schedule at {time_ms}, already at {self._clock.now}")
        seq = self._seq
        self._seq += 1
        heapq.heappush(self._heap, (time_ms, seq, Event(time_ms, seq, node, action)))
        return seq

    def cancel(self, seq: int) -> None:
        """Mark an event as cancelled. Unknown handles are ignored."""
        self._cancelled.add(seq)

    def pop(self) -> Event | None:
        """Take the next event, advancing the clock to its timestamp.

        Cancelled entries are skipped here rather than removed on cancellation,
        which keeps cancellation O(1) and, more importantly, keeps it from
        perturbing the heap layout of everything still pending.

        Returns:
            The next event, or None once the queue is drained.
        """
        while self._heap:
            time_ms, seq, event = heapq.heappop(self._heap)
            if seq in self._cancelled:
                self._cancelled.discard(seq)
                continue
            self._clock.advance_to(time_ms)
            return event
        return None

    @property
    def pending(self) -> int:
        """How many entries are queued, cancelled ones included."""
        return len(self._heap)

    def __len__(self) -> int:
        return len(self._heap)
