# 2. Discrete-event simulation over real threads

- Status: accepted
- Date: 2026-07-28

## Context

The project needs to run a replicated system under adversarial network
conditions and, when something breaks, reproduce the failure exactly. Three
approaches were on the table.

**Real threads and real sockets, with a fault proxy.** Closest to production,
and the easiest to argue is "realistic". It also makes reproduction impossible:
the OS scheduler decides the interleaving, and no seed recovers it. Jepsen sits
here and pays for it by running the same scenario hundreds of times hoping to
hit the window again.

**`asyncio` with a controlled event loop.** Tempting, because a custom loop can
be made deterministic. But every third-party coroutine, every `async` context
manager and every `await` on something outside the loop is a chance to reorder
work in a way the seed does not describe. The determinism boundary would be the
whole language runtime.

**A single-threaded discrete-event simulation.** Time is a number. The
scheduler holds every pending event in one priority queue and delivers them one
at a time. There is no concurrency at all — only interleavings the scheduler
chose, from a seed.

## Decision

Single-threaded discrete-event simulation. One loop, one queue, one seeded
random source, and a virtual clock that only the scheduler may advance.

Concurrency is modelled, not used. Two operations are concurrent because their
invoke/return intervals overlap in virtual time, not because two OS threads
were running.

## Consequences

- A seed identifies a run completely. Reproduction is exact and free, which is
  what makes shrinking and regression corpora possible at all.
- Simulated time is decoupled from wall time: six hours of cluster life costs
  milliseconds, so rare timing windows become cheap to explore.
- The system under test must be written as a state machine reacting to events.
  That is a real constraint, and it is the constraint that makes it testable.
  It is also why `Env` exists.
- Nothing is learned about real thread contention, syscall latency or kernel
  behaviour. This is a logic simulator, not a performance model — stated as a
  non-goal in the README.
- Parallelism is still available where it costs nothing: the fuzzer runs whole
  seeds in separate processes, each of which is internally single-threaded.
