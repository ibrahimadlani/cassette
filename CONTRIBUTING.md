# Contributing

## Getting set up

```bash
make install     # virtualenv + the project with dev extras
make test        # the whole suite
make demo        # the project in one command
```

For the replayer:

```bash
cd web && npm ci && npm run dev
```

## Before you open a pull request

```bash
make lint types test
```

CI runs the same three, on Python 3.11 and 3.12, plus a job that repeats the
suite under a randomised `PYTHONHASHSEED`. Coverage is gated at 85 %.

## The one rule that matters

Nothing in `cassette/sim/` or `cassette/kv/` may read the wall clock, draw from
the global `random` module, start a thread, or do I/O. A node reaches the
outside world through the `Env` it is handed and through nothing else.

This is enforced three ways — a `ruff` rule, an AST guard in
`tests/test_determinism_guard.py`, and the trace-hash comparison in
`tests/test_determinism.py`. If a change makes any of them fail, the change is
wrong, not the check. [docs/DETERMINISM.md](docs/DETERMINISM.md) explains why.

If you genuinely need an exception, it goes in the guard's allowlist with a
comment saying why, and a test asserts that the allowlist stays short.

## Adding a fault

1. Add the parameter to `FaultConfig` and validate it in `__post_init__`.
2. Add the action to `cassette/sim/events.py` and handle it in
   `Simulation._dispatch`.
3. Teach `FaultInjector.tick` to roll for it and record it as an
   `InjectedFault`, so the shrinker can delete it.
4. Write one test that shows it firing and one that shows it replaying.
5. Add a section to [docs/FAULTS.md](docs/FAULTS.md) with the semantics, and be
   explicit about *when* it applies — send time or delivery time, dropped or
   deferred.
6. Extend `schema/trace.schema.json` if it appears in a trace.

Roll the die unconditionally, even when the rate is zero. Turning a fault off
must change what happens without shifting every decision taken afterwards, or
the shrinker's central question stops meaning anything.

## Changing the trace format

The trace is a contract between Python and TypeScript.

1. Bump `TRACE_VERSION` in `cassette/trace.py` and `web/src/trace.ts`.
2. Update `schema/trace.schema.json`.
3. Run `make traces` to rebuild the replayer's catalogue.
4. Run `cd web && npm test` — it reads the exported traces as fixtures, so a
   format change that only lands on one side turns the build red.

## Commits

Conventional Commits, imperative mood, under 72 characters on the first line:

```
feat(sim): inject symmetric network partitions
fix(kv): write back the winning version before returning a read
test(sim): verify identical trace hash across 1000 seeds
docs(adr): record the decision to pre-generate traces
```

Use the body for *why*, whenever the why is not obvious from the diff. That is
most of the time, and it is what the log is for.

## Reporting a bug the fuzzer found

Include the seed and the exact command. If `cassette shrink --seed N` produces
something readable, include that instead of the raw trace — four lines beat four
hundred events.
