# 4. A Wing and Gong search as the linearizability checker

- Status: accepted
- Date: 2026-08-06

## Context

The simulator can produce a history. Something has to say whether that history
was possible.

Weaker oracles were tempting and were rejected in turn. **Hand-written
invariants** — "a read never returns a value nobody wrote" — are cheap and
catch almost nothing; the store passed every one of them while returning stale
values. **Sequential consistency** is easier to check and is not the property
being claimed. **Inspecting the replicas' internal state** is the worst of the
three: an oracle that reads the implementation cannot catch the implementation
being wrong, only being inconsistent with itself.

Linearizability is the property a key-value store is actually expected to have,
and deciding it is NP-complete in general.

## Decision

The search Wing and Gong describe: pick an operation that is legal to place
next, apply it to a register model, recurse, backtrack on failure.

Three things make it affordable in practice:

**Memoisation on `(placed, state)`.** Two orders that have placed the same set
of operations and left the register holding the same value are
indistinguishable from that point on. This is what turns a factorial search
into one that finishes.

**P-compositionality.** A history over independent objects is linearizable
exactly when its restriction to each object is. Keys are independent, so a
twenty-four operation history over two keys is two twelve-operation searches.
The difference between those two is not a constant factor.

**A budget.** An adversarial history can still explode. When the search exceeds
its budget the verdict is `exhausted`, and an exhausted verdict is never
reported as a violation.

## Consequences

- Histories of a few dozen operations per key decide in milliseconds, which is
  what makes fuzzing thousands of seeds possible at all.
- Operations that never returned are handled explicitly: they may be placed
  anywhere or left out. Dropping them would turn a genuine stale read into a
  false alarm; assuming they happened would do the reverse.
- A violation is reported with the operation that caused it, found by replaying
  the history under later and later cuts and stopping at the first cut that
  fails. "Operation 7 could not be placed" is a usable answer; "this history is
  not linearizable" is not.
- Never reporting an undecided search as a violation means the checker can miss
  things. That is the right way round. A tool that cries wolf stops being run.
- Checking is not free: it is roughly a third of the fuzzer's per-seed cost.
  Worth it, and the reason the budget exists.

## What this cost, and what it bought

The first violation the checker reported was its own fault. Clients were
stamping the history with `env.now()`, which applies clock drift, so operations
from different clients were being compared on different time bases. Some
appeared to return before they were invoked.

That is recorded here because it is the general lesson of this ADR: an oracle
has to be trusted before its answers mean anything, and the way you earn that
trust is by writing the histories whose answers you already know — half of them
non-linearizable — before you point it at anything real.
