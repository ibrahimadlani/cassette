"""A client: runs a fixed plan of operations and writes down what it saw.

The plan is explicit rather than generated on the fly. That is a decision made
for the shrinker's benefit: a scenario the shrinker can reduce has to be a list
of things it can delete, and "the fourth operation client 6 would have chosen"
is not something you can delete without changing everything after it.

One operation is in flight at a time per client. Concurrency comes from running
several clients, which is also the setting linearizability is defined in — each
client is a sequential process, and the interesting question is how their
timelines interleave.
"""

from __future__ import annotations

from dataclasses import dataclass

from cassette.checker.history import CAS, History
from cassette.kv.messages import ClientReply, ClientRequest, Key, Value
from cassette.sim.env import Env
from cassette.sim.types import JsonDict, NodeId, Payload

NEXT_TIMER = "next"
PATIENCE_TIMER = "patience"


@dataclass(frozen=True, slots=True)
class PlannedOp:
    """One operation a client will issue, and how long it waits first."""

    kind: str
    key: Key
    argument: Value = None
    expected: Value = None
    coordinator: NodeId = 0
    delay_ms: int = 0

    def to_json(self) -> JsonDict:
        """Render for the trace and for the shrunk scenario."""
        return {
            "kind": self.kind,
            "key": self.key,
            "argument": self.argument,
            "expected": self.expected,
            "coordinator": self.coordinator,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> PlannedOp:
        """Rebuild from the trace form."""
        return cls(
            kind=str(data["kind"]),
            key=str(data["key"]),
            argument=_as_value(data["argument"]),
            expected=_as_value(data["expected"]),
            coordinator=int(str(data["coordinator"])),
            delay_ms=int(str(data["delay_ms"])),
        )


def _as_value(raw: object) -> Value:
    return None if raw is None else int(str(raw))


class Client:
    """Issues a plan, one operation at a time, recording each into the history."""

    def __init__(
        self,
        node_id: NodeId,
        plan: tuple[PlannedOp, ...],
        history: History,
        patience_ms: int = 5_000,
    ) -> None:
        self.node_id = node_id
        self.plan = plan
        self.history = history
        self.patience_ms = patience_ms
        self._index = 0
        self._req = node_id * 1_000_000
        self._outstanding: tuple[int, int] | None = None

    @property
    def finished(self) -> bool:
        """Whether the plan has been exhausted."""
        return self._index >= len(self.plan) and self._outstanding is None

    def start(self, env: Env) -> None:
        """Arm the first operation."""
        self._arm(env)

    # -- the loop -------------------------------------------------------

    def _arm(self, env: Env) -> None:
        if self._index >= len(self.plan):
            return
        env.set_timer(self.plan[self._index].delay_ms, NEXT_TIMER)

    def _issue(self, env: Env) -> None:
        planned = self.plan[self._index]
        self._req += 1
        entry = self.history.invoke(
            client=self.node_id,
            kind=planned.kind,
            key=planned.key,
            at_ms=env.now(),
            argument=planned.argument,
            expected=planned.expected,
        )
        self._outstanding = (self._req, entry)
        env.send(
            planned.coordinator,
            ClientRequest(self._req, planned.kind, planned.key, planned.argument, planned.expected),
        )
        env.set_timer(self.patience_ms, PATIENCE_TIMER)

    def _settle(self, env: Env, reply: ClientReply | None) -> None:
        if self._outstanding is None:
            return
        _, entry = self._outstanding
        planned = self.plan[self._index]
        if reply is not None and reply.ok:
            self.history.complete(entry, at_ms=env.now(), result=self._result(planned, reply))
        else:
            # Told it failed, or never told anything. Same thing to the checker:
            # nobody knows whether this landed.
            self.history.give_up(entry)
        self._outstanding = None
        self._index += 1
        env.cancel_timer(PATIENCE_TIMER)
        self._arm(env)

    @staticmethod
    def _result(planned: PlannedOp, reply: ClientReply) -> Value:
        return reply.value if planned.kind in (CAS, "read") else None

    # -- Node protocol --------------------------------------------------

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        """Take a coordinator's answer, if it is the one we are waiting for."""
        if not isinstance(msg, ClientReply) or self._outstanding is None:
            return
        if msg.req != self._outstanding[0]:
            return
        self._settle(env, msg)

    def on_timer(self, env: Env, tag: str) -> None:
        """Issue the next operation, or give up on the current one."""
        if tag == NEXT_TIMER:
            self._issue(env)
        elif tag == PATIENCE_TIMER:
            self._settle(env, None)

    def on_crash(self) -> None:
        """Clients do not crash in this harness."""
        return

    def on_restart(self, env: Env) -> None:
        """Clients do not crash in this harness."""
        return
