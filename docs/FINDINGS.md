# What it found

Three real defects and one methodological one, in the order they were found.
Every bug here is in code I wrote, found by a tool I wrote, and reduced to a
scenario short enough to read.

Reproduce any of them with `--buggy`, which switches both fixed defects back
on:

```bash
cassette fuzz --seeds 2000 --buggy      # a violation within a second
cassette shrink --seed 6 --buggy        # reduced to four operations
```

---

## Finding 0 — the checker's own clock

**Found:** while writing the linearizability checker, before it had ever seen
the store.
**Severity:** would have made every later result meaningless.

The very first violation the checker reported was its own fault.

Clients stamped their invoke and return times with `env.now()`. `env.now()`
applies clock drift — that is the whole point of `clock_skew_ms` — so two
clients with different offsets were being compared on different time bases.
Operations appeared to return before they were invoked, and the checker
faithfully reported the impossible orderings that resulted.

Linearizability is defined against real time. Drift belongs to the system under
test; the observer's clock is what "real time" means when judging a history,
exactly as the harness clock does in a Jepsen-style setup. Clients are now
registered with `skewed=False`.

**Fix:** `fix(sim): record client observations on the unskewed clock`

The lesson is the reason `tests/checker/test_linear.py` exists in the shape it
does: twenty-odd histories worked out on paper, half of them non-linearizable
on purpose, all written before the checker was pointed at anything real. An
oracle has to be trusted before its answers are worth reading.

---

## Finding 1 — one coordinator, two identical version stamps

**Found:** first fuzzing run, 14 violations in the first 2000 seeds.
**Shrunk to:** 4 operations, 3 replicas, 2 clients, **no injected faults at
all**.

```
1. client A writes x=1    via n2   -> ok
2. client B writes x=2    via n2   -> ok
3. client B reads  x      via n0   -> 2   <-- no legal order can explain this
4. client A reads  x      via n1   -> 1
```

Two clients write the same key through the same coordinator. Both rounds read
the quorum before either writes, so both see the same current version, and both
derive the same successor: `(2, n2)` — identical stamp, different value.

Replicas keep the first stamp that arrives and reject the second, because the
rule is *strictly* newer. But they acknowledge it anyway, which is correct in
itself: a replica holding something newer has still seen the write, and staying
silent would stall a coordinator that has done nothing wrong.

So the second write gathers its quorum, is reported successful, and lands on
some replicas and not others. The cluster is permanently split, and the two
reads afterwards each see a different half.

The version tiebreak I was so pleased with — `(counter, node_id)` — only
distinguishes *different* coordinators. It does nothing about one coordinator
racing itself, which is the case that actually happens.

**Fix:** `fix(kv): never mint the same version twice from one coordinator`

A replica remembers the highest stamp it has issued per key and mints strictly
above both that and whatever the quorum reported. The record is durable, for
the same reason a Raft term is: a node that forgot it across a restart could
reissue a stamp it had already used.

Violations in the first 2000 seeds: **14 → 3.**

### Worth noting

This one needs no faults. No loss, no partition, no crash. Ordinary variable
latency between two clients talking to the same node is enough, and a fixed
latency hides it completely — which is exactly why it would survive any amount
of testing on a quiet machine.

---

## Finding 2 — a read that does not stay read

**Found:** re-fuzzing after Finding 1 was fixed. 3 violations survived.
**Shrunk to:** 10 operations, one partition.

The symptom is a read going backwards:

```
 8. client A reads  x      via n0   -> 7
12. client B reads  x      via n4   -> 6
15. client A reads  x      via n0   -> 6   <-- no legal order can explain this
```

`R + W > N` guarantees that every read quorum meets every write quorum, so a
read cannot miss a write that has *completed*. It says nothing about a write
still in flight.

A write that has reached three of five replicas but has not yet been
acknowledged is in a genuinely ambiguous state. A read whose quorum happens to
include one of those three sees the new value and returns it. A later read
whose quorum happens to miss all three sees the old one. The first read has
already told a client the new value, so the second read has gone backwards, and
no ordering of the operations can explain both.

This is the classic reason the ABD register construction has two phases on the
read path, and I had implemented one.

**Fix:** `fix(kv): write back the winning version before returning a read`

A read now writes the value it is about to return back to a write quorum before
answering. What it reports becomes durable, and the next read cannot fail to
see it. Reads cost a second round trip; there is no cheaper correct option
without consensus.

Violations in the first 2000 seeds: **3 → 0.** In 20 000: **0.** In 20 000 on
the `harsh` preset: **0.**

---

## Finding 3 — compare-and-swap cannot be fixed here

**Status:** open, and unfixable in this design. Out of scope, deliberately.

`cassette fuzz --cas-ratio 0.4` finds violations that no amount of write-back
repairs, and the reason is not a bug in the implementation.

Two coordinators can both read a quorum, both observe the expected value, and
both decide to swap. Neither is wrong about what it saw. There is no point at
which either could have learned about the other, because a quorum store has no
mechanism for one node to prevent another from acting — that mechanism is
called consensus, and this store does not have one.

A compare-and-swap is a consensus problem wearing a key-value store's clothes.
It cannot be made linearizable on a leaderless quorum register at any quorum
size.

This is the concrete argument for the Raft backend on the roadmap. Not "it
would be interesting to implement Raft" — a specific operation that this design
cannot support and that one could.

---

## The demonstration

The two fixed defects live behind `--buggy`, so the difference is measurable
rather than asserted:

| | scenarios | wall time | violations |
|---|---|---|---|
| `--buggy` | 7 | 0.37 s | 1 |
| fixed | 20 000 | 24.5 s | 0 |

Both defects also stay in the corpus. `regressions.txt` holds fourteen seeds
that used to fail; the suite asserts they are clean now *and* that they fail
again with `--buggy`, because a corpus of seeds that pass could otherwise just
be a corpus of seeds that never failed.

## A limitation of the corpus

The corpus stores seeds. A seed only means something relative to the exact
harness that interprets it, so a change to the simulator invalidates the whole
file — which happened once already, when the fault injector was given its own
random stream, and all fourteen entries had to be re-derived.

Storing reduced scenarios instead would fix it: a shrunk scenario carries its
operations and its faults explicitly and does not depend on how the generator
happens to consume randomness. The shrinker already produces exactly that. It
is on the list.
