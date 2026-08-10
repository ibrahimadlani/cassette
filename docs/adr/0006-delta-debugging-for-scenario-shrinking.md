# 6. Delta debugging, plus a search, for scenario shrinking

- Status: accepted
- Date: 2026-08-10

## Context

The fuzzer hands back a seed. The seed is a perfect reproduction and a useless
explanation: five replicas, three clients, twenty-four operations, four
injected faults and roughly five hundred events, with the reason somewhere
inside.

Nobody debugs that. The gap between "I can reproduce it" and "I can see why"
is where most of the value of a tool like this lives.

## Decision

Two phases, reported separately.

**Deletion.** Classic delta debugging over the scenario: drop faults, drop
operations, drop clients, shrink the cluster, flatten the think times. Every
candidate is re-run and kept only if the violation survives on the same key.
Loop to a fixed point, bounded by a budget.

This needs the scenario to be an explicit list of things, which is why client
operations are a plan rather than a generator, and why the fault schedule is
captured into a list of `InjectedFault` before shrinking starts. You cannot
delete an element from a random number generator.

**Search.** When deletion stalls, build small scenarios from scratch — three
replicas, two or three clients, two to four operations, all on the key that
failed, across a range of seeds and latency profiles — and keep the first that
fails the same way.

## Why the second phase exists

Deletion stalls at about a third of the original size, every time, and the
reason is structural rather than a tuning problem.

The bug needs two rounds to overlap. Whether they overlap depends on the
traffic around them, so deleting the surrounding operations stops them
colliding. The minimal case — two clients writing the same key through the same
coordinator — is not a *subset* of the large random scenario. It is a different
arrangement of one. No sequence of deletions reaches it.

The predicate is not monotone either: removing an operation changes the number
of messages, which changes every latency draw after it. A scenario with one
operation removed is a different run that happens to be smaller.

So the honest description is that the shrinker does not isolate the cause of
*this* run. It finds the smallest scenario it can that fails the same way, and
`Reduction` carries both numbers — what deletion achieved, and what the search
found — so a 10x figure is never quietly presented as a 10x deletion.

## Consequences

- Median reduction across the corpus: 2.2x from deletion alone, 10.1x with the
  search. Every failing seed converges on the same four-operation scenario,
  which is a good sign: they are all the same bug.
- The result reads as four numbered lines with the offending operation marked.
  That is the form it reaches `docs/FINDINGS.md` and the README in.
- A reduced scenario carries its faults explicitly, so it replays with no
  adversary attached and nothing about it depends on a decision taken at run
  time. That also makes it a better corpus entry than a seed, which is
  invalidated by any change to the harness.
- Shrinking costs about half a second per seed. Cheap enough to run on
  anything the fuzzer reports.
- The search phase only knows how to build scenarios in the shapes it was
  taught. A bug needing five replicas or a specific partition would survive
  deletion but never be rebuilt, and would be reported at whatever size
  deletion reached. That is a real limit and it is why both numbers are kept.
