# Benchmarks

Produced by `make bench`. Every number in the README comes from here.

Measured on: arm64, 8 cores, Python 3.12.10 on Darwin

| Metric | Value | Detail |
|---|---|---|
| Scenarios explored per second | **930** | 20,000 seeds on 8 workers, 21.5s |
| Simulated time per real second, under load | **13.4 minutes** | 134s of cluster life in 0.17s, 22,509 events |
| Simulated time per real second, idle cluster | **7 hours** | 6h of five-node gossip in 0.89s, 269,980 events |
| Median shrink ratio (events before → after) | **10.1x** | deletion alone 2.2x, median 4 operations left |
| Seeds in the regression corpus | **14** | all replayed on every test run, and asserted to fail again with --buggy |
| Scenarios to find the bug with --buggy | **7 in 0.24s** | the same fuzzer explores 20,000 with the fix in and finds nothing |
| Determinism check | **1,000 seeds x2 in 6.4s** | SHA-256 of the canonical trace, compared run to run |
| Consistency bugs found in my own implementation | **2 fixed, 1 unfixable by design** | see docs/FINDINGS.md |

## What these are not

Scenario throughput is a measure of this simulator, not of any real
cluster. Simulated time per real second is the same figure seen from the
other side: the point is that rare timing windows are cheap to explore,
not that anything here runs fast on a network.

The shrink ratio is measured in events, over every seed in the corpus,
against the store with its defects switched back on — there is nothing
left to shrink otherwise. Both phases are reported, because only the
first is a reduction of the original run. See ADR-0006.
