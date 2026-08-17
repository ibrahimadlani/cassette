# Architecture decisions

Short records of the choices that were expensive to reverse. Each one states
the alternatives that lost and why, including the consequences I do not like.

Numbered in the order they were assigned, which is not quite the order they were
decided: 0005 was reserved for the replayer early and written up once the
replayer existed.

| # | Decision | Date |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | 2026-07-27 |
| [0002](0002-discrete-event-simulation-over-real-threads.md) | Discrete-event simulation over real threads | 2026-07-28 |
| [0003](0003-quorum-kv-as-first-system-under-test.md) | A quorum key-value store as the first system under test | 2026-08-03 |
| [0004](0004-wing-gong-linearizability-checker.md) | A Wing and Gong search as the linearizability checker | 2026-08-06 |
| [0005](0005-pregenerated-traces-for-the-web-replayer.md) | Pre-generated traces for the web replayer | 2026-08-13 |
| [0006](0006-delta-debugging-for-scenario-shrinking.md) | Delta debugging, plus a search, for scenario shrinking | 2026-08-10 |

Records are immutable. A decision that stops being true gets a new record that
supersedes the old one; the old one stays, with its status updated.
