"""The engine: owns the clock, the queue, the bus and the nodes.

A `Simulation` is the only object that sees all of the moving parts. Nodes see
a `NodeEnv` and nothing else.
"""

from __future__ import annotations

from cassette.sim.clock import VirtualClock
from cassette.sim.env import Env, Node
from cassette.sim.events import DeliverMessage, Event, FireTimer
from cassette.sim.faults import FaultConfig
from cassette.sim.network import Network
from cassette.sim.observer import NullObserver, Observer
from cassette.sim.rng import Rng
from cassette.sim.scheduler import Scheduler
from cassette.sim.types import NodeId, Payload


class NodeEnv:
    """One node's view of the simulation.

    Implements `Env` structurally. Every method is a forward to the owning
    simulation with the node id already bound, so a node cannot accidentally
    act on behalf of another.
    """

    __slots__ = ("_node_id", "_sim")

    def __init__(self, node_id: NodeId, simulation: Simulation) -> None:
        self._node_id = node_id
        self._sim = simulation

    def now(self) -> int:
        """This node's view of logical time."""
        return self._sim.now_for(self._node_id)

    def send(self, to: NodeId, msg: Payload) -> None:
        """Hand a message to the bus."""
        self._sim.send(self._node_id, to, msg)

    def set_timer(self, delay_ms: int, tag: str) -> None:
        """Ask to be woken with `tag`, replacing any pending timer of that tag."""
        self._sim.set_timer(self._node_id, delay_ms, tag)

    def cancel_timer(self, tag: str) -> None:
        """Drop a pending timer."""
        self._sim.cancel_timer(self._node_id, tag)

    def random(self) -> float:
        """Draw from the simulation's seeded source."""
        return self._sim.rng.random()


class Simulation:
    """A single deterministic run."""

    def __init__(
        self,
        seed: int,
        config: FaultConfig | None = None,
        observer: Observer | None = None,
    ) -> None:
        self.config = config or FaultConfig()
        self.observer = observer or NullObserver()
        self.clock = VirtualClock()
        self.rng = Rng(seed)
        self.scheduler = Scheduler(self.clock)
        self.network = Network(self.scheduler, self.rng, self.config, self.observer)
        self._nodes: dict[NodeId, Node] = {}
        self._envs: dict[NodeId, NodeEnv] = {}
        self._timers: dict[tuple[NodeId, str], int] = {}

    # -- wiring ---------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Register a participant. Ids must be unique."""
        if node.node_id in self._nodes:
            raise ValueError(f"node {node.node_id} is already registered")
        self._nodes[node.node_id] = node
        self._envs[node.node_id] = NodeEnv(node.node_id, self)

    def env_for(self, node_id: NodeId) -> Env:
        """The `Env` handed to a registered node."""
        return self._envs[node_id]

    @property
    def node_ids(self) -> list[NodeId]:
        """Registered ids, sorted. Never iterate the underlying mapping directly."""
        return sorted(self._nodes)

    # -- services offered to nodes --------------------------------------

    def now_for(self, node_id: NodeId) -> int:
        """The time `node_id` believes it is."""
        return self.clock.now

    def send(self, sender: NodeId, recipient: NodeId, msg: Payload) -> None:
        """Route a message through the bus."""
        self.network.send(sender, recipient, msg)

    def set_timer(self, node_id: NodeId, delay_ms: int, tag: str) -> None:
        """Schedule a wakeup, superseding any pending timer with the same tag.

        Replacing rather than stacking matters: "restart my election timeout" is
        the single most common timer operation in a replicated system, and a
        queue that accumulated one entry per reset would drift away from what
        the protocol actually asked for.
        """
        self.cancel_timer(node_id, tag)
        self._timers[node_id, tag] = self.scheduler.schedule(delay_ms, node_id, FireTimer(tag))

    def cancel_timer(self, node_id: NodeId, tag: str) -> None:
        """Drop a pending timer. Unknown tags are ignored."""
        pending = self._timers.pop((node_id, tag), None)
        if pending is not None:
            self.scheduler.cancel(pending)

    # -- the loop -------------------------------------------------------

    def step(self) -> bool:
        """Deliver one event.

        Returns:
            False once the queue is drained.
        """
        event = self.scheduler.pop()
        if event is None:
            return False
        self._dispatch(event)
        return True

    def run(self, *, until_ms: int | None = None, max_events: int | None = None) -> int:
        """Drain the queue, optionally stopping early.

        Returns:
            The number of events delivered.
        """
        delivered = 0
        while max_events is None or delivered < max_events:
            if until_ms is not None:
                next_time = self.scheduler.peek_time()
                if next_time is None or next_time > until_ms:
                    break
            if not self.step():
                break
            delivered += 1
        return delivered

    def _dispatch(self, event: Event) -> None:
        node = self._nodes.get(event.node)
        if node is None:
            return
        env = self._envs[event.node]
        action = event.action
        if isinstance(action, DeliverMessage):
            node.on_message(env, action.sender, action.msg)
        else:
            if self._timers.get((event.node, action.tag)) != event.seq:
                return
            del self._timers[event.node, action.tag]
            node.on_timer(env, action.tag)
