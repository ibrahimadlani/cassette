"""Minimal participants used to exercise the simulator without the KV store."""

from __future__ import annotations

from dataclasses import dataclass, field

from cassette.sim.env import Env
from cassette.sim.types import JsonDict, NodeId, Payload


@dataclass(frozen=True, slots=True)
class Ping:
    """A payload with no meaning beyond being carried around."""

    text: str = "ping"

    @property
    def kind(self) -> str:
        return "ping"

    def to_json(self) -> JsonDict:
        return {"text": self.text}


@dataclass
class RecordingNode:
    """A node that writes down everything it is handed."""

    node_id: NodeId
    messages: list[tuple[int, NodeId, str]] = field(default_factory=list)
    timers: list[tuple[int, str]] = field(default_factory=list)
    crashes: int = 0
    restarts: int = 0

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        assert isinstance(msg, Ping)
        self.messages.append((env.now(), sender, msg.text))

    def on_timer(self, env: Env, tag: str) -> None:
        self.timers.append((env.now(), tag))

    def on_crash(self) -> None:
        self.crashes += 1
        self.messages.clear()
        self.timers.clear()

    def on_restart(self, env: Env) -> None:
        self.restarts += 1


@dataclass
class EchoNode:
    """Replies once to whatever it receives, so messages keep flowing."""

    node_id: NodeId
    budget: int = 3
    seen: int = 0

    def on_message(self, env: Env, sender: NodeId, msg: Payload) -> None:
        assert isinstance(msg, Ping)
        self.seen += 1
        if self.budget > 0:
            self.budget -= 1
            env.send(sender, Ping(f"re:{msg.text}"))

    def on_timer(self, env: Env, tag: str) -> None:
        return

    def on_crash(self) -> None:
        return

    def on_restart(self, env: Env) -> None:
        return
