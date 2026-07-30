# The fault model

Everything the simulator is allowed to do to the system under test, and the
exact semantics of each one. All of it is driven by
[`FaultConfig`](../cassette/sim/faults.py), which is a frozen dataclass with a
JSON round trip so that a schedule can travel into a trace, into the regression
corpus and into the shrinker unchanged.

## Where each fault is applied

| Fault | Parameter | Applied in |
|---|---|---|
| Latency | `latency_ms` | `Network.send` |
| Loss | `drop_rate` | `Network.send` |
| Duplication | `dup_rate` | `Network.send` |
| Reordering | — | emergent |
| Partition | `partition_rate`, `partition_duration_ms` | `Network.can_reach`, at delivery |
| Crash / restart | `crash_rate`, `crash_duration_ms` | `Simulation._crash` |
| Pause | `pause_rate`, `pause_duration_ms` | `Simulation._deliver` |
| Clock skew | `clock_skew_ms` | `Simulation.now_for` |

Rates are probabilities rolled once per `tick_ms` by the
[`FaultInjector`](../cassette/sim/injector.py), except loss and duplication,
which are rolled per message.

## Latency

Every message waits a delay drawn uniformly from `latency_ms`, healthy network
included. There is no such thing as a synchronous delivery, so no protocol can
accidentally depend on one.

## Loss

`drop_rate` is the probability that a message is never delivered. The sender is
not told. A lost message still consumes an identifier and still appears in the
trace as `msg_drop` with `reason: "loss"`, so a replay shows the gap rather
than hiding it.

## Duplication

`dup_rate` is the probability that a message is delivered twice, with two
independently drawn delays. Both copies carry the same identifier, so a
duplicate shows up in the trace as two `msg_deliver` entries sharing an `id`.

The second copy can land arbitrarily later than the first, which is the case
that catches handlers assuming they will only ever see a reply once.

## Reordering

Not a configurable fault: it falls out of variable latency. Widening
`latency_ms` widens the reordering window. Setting `latency_ms` to a single
value — `(7, 7)` — turns the bus back into a FIFO channel, which is
occasionally useful when bisecting whether reordering is what broke something.

## Partition

A partition splits the replicas into two non-empty groups. Messages between
groups are dropped; messages inside a group are unaffected. Only one partition
is ever open at a time.

Two decisions worth stating:

- **Reachability is evaluated at delivery, not at send.** A message that leaves
  before the link breaks and arrives after it has is dropped, because that is
  what happens to a packet in flight.
- **Participants outside every group stay reachable.** Clients live there. A
  partition is a statement about the replicas; a client cut off from the whole
  cluster would just stall, and a stalled client teaches the checker nothing.

Split sizes are drawn uniformly over proper subsets rather than aimed at
halves. The interesting case is the lopsided one, where a minority keeps
accepting work it has no right to accept.

## Crash and restart

A crash calls `Node.on_crash()`, cancels every timer the node had armed, and
drops messages addressed to it for the duration. Whatever a replica still holds
after `on_crash()` is, by definition, its durable state — the simulator does not
need a disk to make that distinction meaningful.

A restart calls `Node.on_restart(env)`. Timers do not come back on their own;
a node that wants one re-arms it.

## Pause

A pause freezes a node without killing it. Nothing is lost and nothing is
discarded: messages and timers queue up and land in a burst the moment the node
resumes.

That burst is the whole point. A crash looks like absence, which most protocols
handle. A pause looks like presence followed by a node acting on information
that is hundreds of milliseconds stale, which is what breaks reasoning built on
leases and timeouts.

Pauses do not extend a crash: crashing a paused node cancels the pause.

## Clock skew

Each node draws a fixed offset in `[-clock_skew_ms, +clock_skew_ms]` when it is
registered, and keeps it for the whole run. `env.now()` returns the shifted
value, never below zero.

Skew changes what a node *reads*, never when it gets *scheduled*. The event
queue stays the single authority on ordering. Without that separation a skewed
clock would become a second, hidden source of interleavings, and the seed would
no longer describe the run.

## Turning faults off does not move the run

Loss and duplication draw from the seeded source on every send whether the rate
is zero or not. Setting `drop_rate` to `0.0` therefore changes what happens to
each message without shifting every decision taken afterwards.

This matters for shrinking. The shrinker's whole method is "remove one fault
and see whether the bug survives", and that question is only meaningful if
removing a fault leaves the rest of the schedule where it was.
