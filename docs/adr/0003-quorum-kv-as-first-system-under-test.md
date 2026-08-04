# 3. A quorum key-value store as the first system under test

- Status: accepted
- Date: 2026-08-03

## Context

The simulator needs something to simulate. The obvious candidate is Raft:
it is the algorithm everyone reaches for, it has a paper, and "I implemented
Raft" is a recognisable sentence.

That is most of the argument against it.

Raft is a large amount of work — elections, terms, log replication, commit
index, matching, and the handful of subtleties that only show up under
partition — and every hour spent on it is an hour not spent on the simulator,
the checker or the shrinker. Those are the parts of this project that are
actually unusual. A Raft implementation is not.

Raft is also, when correct, hard to break. That is its purpose. A tool whose
job is finding consistency bugs wants a subject that has some, so that the
tool can be shown to work rather than merely asserted to.

## Decision

The first system under test is a leaderless quorum store in the Dynamo family:
N replicas, a read quorum R, a write quorum W, last-writer-wins on a
`(counter, node)` version stamp. Any replica can coordinate any request.

Writes take two phases — read the current version from R replicas, then write
`version + 1` to W of them — which is the classic ABD register construction.
Reads take one.

`R + W > N` guarantees every read quorum intersects every write quorum. Whether
that is *sufficient* for linearizability is exactly the question this project
exists to ask, and the answer is written up in `docs/FINDINGS.md`.

## Consequences

- The store is roughly three hundred lines, so it was ready on day six rather
  than day twelve, and the remaining budget went to the checker and the
  shrinker.
- Its failure modes are real and well documented, which makes what the fuzzer
  finds defensible rather than a curiosity of a half-finished implementation.
- Compare-and-swap is included, and it cannot be made linearizable on a quorum
  store without consensus. That is not an accident to be hidden; it is a
  second finding, and it is the concrete argument for the Raft backend on the
  roadmap rather than a vague "would be nice".
- Nothing here is a consensus algorithm, so nothing here demonstrates one. The
  README says so.
- The simulator does not care. Swapping in Raft later means writing a new
  package under `cassette/` that implements the same `Node` protocol; not one
  line of `cassette/sim/` would change.
