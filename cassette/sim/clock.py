"""Virtual time.

Time is an integer count of logical milliseconds. It never advances on its own:
the scheduler moves it forward to the timestamp of the event it is about to
deliver, and nothing else may touch it. A simulation that covers six hours of
cluster life therefore costs exactly as much wall time as the work it performs.
"""

from __future__ import annotations


class VirtualClock:
    """A monotonically increasing counter of logical milliseconds."""

    __slots__ = ("_now",)

    def __init__(self, start_ms: int = 0) -> None:
        if start_ms < 0:
            raise ValueError("virtual time cannot start before zero")
        self._now = start_ms

    @property
    def now(self) -> int:
        """The current logical time, in milliseconds."""
        return self._now

    def advance_to(self, timestamp_ms: int) -> None:
        """Move the clock forward to `timestamp_ms`.

        Moving to the current time is allowed: several events routinely share a
        timestamp. Moving backwards is a bug in the caller, not a recoverable
        condition, so it raises.

        Raises:
            ValueError: if `timestamp_ms` is before the current time.
        """
        if timestamp_ms < self._now:
            raise ValueError(f"cannot move virtual time from {self._now} back to {timestamp_ms}")
        self._now = timestamp_ms

    def __repr__(self) -> str:
        return f"VirtualClock(now={self._now})"
