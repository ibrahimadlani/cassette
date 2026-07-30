"""The engine: owns the clock, the queue, the bus and the nodes.

A `Simulation` is the only object that sees all of the moving parts. Nodes see
a `NodeEnv` and nothing else.
"""

from __future__ import annotations

from cassette.sim.clock import VirtualClock
from cassette.sim.env import Env, Node
from cassette.sim.events import (
    CONTROL,
    CrashNode,
    DeliverMessage,
    Event,
    FireTimer,
    HealPartition,
    PauseNode,
    RestartNode,
    ResumeNode,
    StartPartition,
)
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
        self._down: set[NodeId] = set()
        self._paused_until: dict[NodeId, int] = {}
        self._skew: dict[NodeId, int] = {}

    # -- wiring ---------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Register a participant. Ids must be unique and non-negative."""
        if node.node_id == CONTROL:
            raise ValueError(f"{CONTROL} is reserved for fault events")
        if node.node_id in self._nodes:
            raise ValueError(f"node {node.node_id} is already registered")
        self._nodes[node.node_id] = node
        self._envs[node.node_id] = NodeEnv(node.node_id, self)
        skew = self.config.clock_skew_ms
        self._skew[node.node_id] = self.rng.randint(-skew, skew)

    def env_for(self, node_id: NodeId) -> Env:
        """The `Env` handed to a registered node."""
        return self._envs[node_id]

    @property
    def node_ids(self) -> list[NodeId]:
        """Registered ids, sorted. Never iterate the underlying mapping directly."""
        return sorted(self._nodes)

    # -- services offered to nodes --------------------------------------

    def now_for(self, node_id: NodeId) -> int:
        """The time `node_id` believes it is.

        Skew shifts what a node reads, never when it is scheduled. The queue
        stays the single authority on ordering, which is what keeps skew from
        turning into a second, hidden clock.
        """
        return max(0, self.clock.now + self._skew.get(node_id, 0))

    def skew_of(self, node_id: NodeId) -> int:
        """The offset drawn for this node when it was registered."""
        return self._skew.get(node_id, 0)

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

    # -- faults ---------------------------------------------------------

    def schedule_partition(self, groups: tuple[frozenset[NodeId], ...], duration_ms: int) -> None:
        """Open a partition now and close it after `duration_ms`."""
        self.scheduler.schedule(0, CONTROL, StartPartition(groups))
        self.scheduler.schedule(duration_ms, CONTROL, HealPartition())

    def schedule_crash(self, node_id: NodeId, downtime_ms: int) -> None:
        """Kill a node now and bring it back after `downtime_ms`."""
        self.scheduler.schedule(0, node_id, CrashNode())
        self.scheduler.schedule(downtime_ms, node_id, RestartNode())

    def schedule_pause(self, node_id: NodeId, duration_ms: int) -> None:
        """Freeze a node for `duration_ms`, then let it catch up.

        A pause is not a crash: nothing is lost, and nothing addressed to the
        node is discarded. Work simply queues up and lands in a burst on the
        far side, which is precisely the shape of a stop-the-world collection
        and precisely what breaks lease- and timeout-based reasoning.
        """
        self.scheduler.schedule(0, node_id, PauseNode(self.clock.now + duration_ms))
        self.scheduler.schedule(duration_ms, node_id, ResumeNode())

    def is_down(self, node_id: NodeId) -> bool:
        """Whether the node is currently crashed."""
        return node_id in self._down

    def is_paused(self, node_id: NodeId) -> bool:
        """Whether the node is currently frozen."""
        return node_id in self._paused_until

    def _pause(self, node_id: NodeId, until_ms: int) -> None:
        if node_id not in self._nodes or node_id in self._down:
            return
        self._paused_until[node_id] = max(self._paused_until.get(node_id, 0), until_ms)
        self.observer.record("node_pause", node=node_id, until=until_ms)

    def _resume(self, node_id: NodeId) -> None:
        deadline = self._paused_until.get(node_id)
        if deadline is None or deadline > self.clock.now:
            return
        del self._paused_until[node_id]
        self.observer.record("node_resume", node=node_id)

    def _crash(self, node_id: NodeId) -> None:
        node = self._nodes.get(node_id)
        if node is None or node_id in self._down:
            return
        self._down.add(node_id)
        self._paused_until.pop(node_id, None)
        for pending in sorted(key for key in self._timers if key[0] == node_id):
            self.scheduler.cancel(self._timers.pop(pending))
        node.on_crash()
        self.observer.record("node_crash", node=node_id)

    def _restart(self, node_id: NodeId) -> None:
        node = self._nodes.get(node_id)
        if node is None or node_id not in self._down:
            return
        self._down.discard(node_id)
        node.on_restart(self._envs[node_id])
        self.observer.record("node_restart", node=node_id)

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
        match event.action:
            case DeliverMessage() as action:
                self._deliver(event.node, action)
            case FireTimer() as action:
                self._fire_timer(event, action)
            case StartPartition() as action:
                self.network.partition_into(action.groups)
            case HealPartition():
                self.network.heal()
            case CrashNode():
                self._crash(event.node)
            case RestartNode():
                self._restart(event.node)
            case PauseNode() as action:
                self._pause(event.node, action.until_ms)
            case ResumeNode():
                self._resume(event.node)

    def _deliver(self, recipient: NodeId, action: DeliverMessage) -> None:
        node = self._nodes.get(recipient)
        if node is None:
            return
        if not self.network.can_reach(action.sender, recipient):
            self.network.report_drop(action.sender, recipient, action.msg_id, "partition")
            return
        if recipient in self._down:
            self.network.report_drop(action.sender, recipient, action.msg_id, "crashed")
            return
        resume_at = self._paused_until.get(recipient)
        if resume_at is not None:
            self.scheduler.schedule_at(resume_at, recipient, action)
            return
        self.observer.record(
            "msg_deliver",
            id=action.msg_id,
            sender=action.sender,
            to=recipient,
            kind=action.msg.kind,
        )
        node.on_message(self._envs[recipient], action.sender, action.msg)

    def _fire_timer(self, event: Event, action: FireTimer) -> None:
        node = self._nodes.get(event.node)
        if node is None:
            return
        if self._timers.get((event.node, action.tag)) != event.seq:
            return
        if event.node in self._down:
            del self._timers[event.node, action.tag]
            return
        resume_at = self._paused_until.get(event.node)
        if resume_at is not None:
            self._timers[event.node, action.tag] = self.scheduler.schedule_at(
                resume_at, event.node, action
            )
            return
        del self._timers[event.node, action.tag]
        node.on_timer(self._envs[event.node], action.tag)
