# Cassette

Deterministic simulation testing for distributed systems — every bug reproduces, every time.

> Work in progress. The simulator core is done and its determinism is proven by
> a test; the replicated store, the linearizability checker and the shrinker are
> next. See the [roadmap](#roadmap).

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
| Replicated key-value store | next |
| Linearizability checker | next |
| Scenario shrinker | next |
| Web replayer | next |

## Try it

```bash
git clone https://github.com/ibrahimadlani/cassette
cd cassette
make install
make test
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
- `v0.2.0` — replicated KV store and linearizability checker
- `v0.3.0` — scenario shrinker
- `v1.0.0` — web replayer, deployed

## Licence

MIT.
