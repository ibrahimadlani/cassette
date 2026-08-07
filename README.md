# Cassette

Deterministic simulation testing for distributed systems — every bug reproduces, every time.

> Work in progress. The simulator, the replicated store and the linearizability
> checker are done, and the fuzzer has started finding real bugs in the store.
> The shrinker and the web replayer are next. See the [roadmap](#roadmap).

## The idea

A distributed system fails in the interleavings you did not think of. Those
failures are hard to catch and harder to reproduce, because the thing that
decides the interleaving — the OS scheduler, the network, the clock — is not
under your control and does not take instructions.

Cassette takes it under control. The system under test never touches a socket
or reads the wall clock; it talks to an `Env` supplied by a single-threaded
discrete-event simulator that decides, from one seed, which message is
delivered, in which order, which is lost, which node crashes and whose clock
drifts.

A seed therefore describes a run completely. Find a failure once and you can
replay it exactly, as many times as you like.

This is the approach FoundationDB, TigerBeetle and Antithesis take. It is
uncommon in a portfolio, which is why it is worth building.

## Status

| Component | State |
|---|---|
| Virtual clock, seeded RNG, event scheduler | done |
| Message bus with latency, loss, duplication | done |
| Partitions, crash-restart, pauses, clock skew | done |
| Determinism contract, enforced three ways | done |
| Quorum-replicated key-value store | done |
| Wing and Gong linearizability checker | done |
| Parallel fuzzer and regression corpus | done |
| Scenario shrinker | next |
| Web replayer | next |

## What it has found so far

Thirteen of the first two thousand seeds produce a stale read: a value that no
correct key-value store could have returned, given what the clients had already
been told.

They are reproducible down to the operation index, they are recorded in
[`regressions.txt`](regressions.txt), and they are not fixed yet. The next step
is reducing one of them to something small enough to read.

```
$ cassette fuzz --seeds 2000 --workers 8 --all

explored    2000 scenarios
throughput  1158 scenarios/s

NEW      seed 161: client 6 reads y -> 8 cannot be placed in any legal order
```

## Try it

```bash
git clone https://github.com/ibrahimadlani/cassette
cd cassette
make install
make fuzz          # explore 2000 seeds
cassette run --seed 161
```

The test that matters is `tests/test_determinism.py`: a thousand seeds, run
twice each, compared by the SHA-256 of their canonical trace.

## The determinism contract

Inside `cassette/sim/` and `cassette/kv/` there is no `time.time()`, no global
`random`, no `uuid4()`, no threads and no I/O. A node's only door to the outside
world is the `Env` it is handed.

The rules, and the three independent mechanisms that enforce them, are in
[docs/DETERMINISM.md](docs/DETERMINISM.md). The fault model is in
[docs/FAULTS.md](docs/FAULTS.md).

## Roadmap

- `v0.1.0` — the simulator, with determinism proven by a test
- `v0.2.0` — replicated KV store, linearizability checker and fuzzer
- `v0.3.0` — scenario shrinker
- `v1.0.0` — web replayer, deployed

## Licence

MIT.
