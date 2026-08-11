# Cassette

Deterministic simulation testing for distributed systems — every bug reproduces, every time.

[![CI](https://github.com/ibrahimadlani/cassette/actions/workflows/ci.yml/badge.svg)](https://github.com/ibrahimadlani/cassette/actions/workflows/ci.yml)
[![Fuzz](https://github.com/ibrahimadlani/cassette/actions/workflows/fuzz.yml/badge.svg)](https://github.com/ibrahimadlani/cassette/actions/workflows/fuzz.yml)
[![codecov](https://codecov.io/gh/ibrahimadlani/cassette/branch/main/graph/badge.svg)](https://codecov.io/gh/ibrahimadlani/cassette)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Work in progress. Everything but the web replayer is done: the simulator, the
> store, the checker, the fuzzer and the shrinker. Two real consistency bugs
> found, reduced and fixed. See the [roadmap](#roadmap).

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
| Delta-debugging shrinker | done |
| Web replayer | next |

## A bug it found

Fourteen of the first two thousand seeds returned a value no correct key-value
store could have returned. The shrinker reduced every one of them to the same
four operations, on three replicas, **with no injected faults at all**:

```
1. client A writes x=1    via n2   -> ok
2. client B writes x=2    via n2   -> ok
3. client B reads  x      via n0   -> 2   <-- no legal order can explain this
4. client A reads  x      via n1   -> 1
```

Both writes go through the same coordinator. Both rounds read the quorum before
either writes, so both derive the same version stamp for different values.
Replicas keep the first and reject the second — while still acknowledging it.
The losing write is reported successful and lands on half the cluster.

The `(counter, node_id)` tiebreak only ever distinguished different
coordinators. It did nothing about one coordinator racing itself.

Fixing that left three violations, which turned out to be the missing
write-back on the read path — the second phase of ABD. Both are written up in
[docs/FINDINGS.md](docs/FINDINGS.md), and both are still reachable with
`--buggy`:

| | scenarios | wall time | violations |
|---|---|---|---|
| `--buggy` | 7 | 0.37 s | 1 |
| fixed | 20 000 | 24.5 s | 0 |

## Try it

```bash
git clone https://github.com/ibrahimadlani/cassette
cd cassette
make install
make fuzz          # explore 2000 seeds, finds nothing now
cassette fuzz --seeds 2000 --buggy   # switch the bugs back on
cassette shrink --seed 6 --buggy
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
- `v0.3.0` — scenario shrinker, and both bugs fixed
- `v1.0.0` — web replayer, deployed

## Licence

MIT.
