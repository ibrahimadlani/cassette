# The determinism contract

Cassette makes one promise: **a seed describes a run completely.** Give it the
same seed and the same configuration and you get the same trace, byte for byte,
on any machine, on any supported Python.

Everything else in this repository — replay, shrinking, the regression corpus,
the web replayer — is downstream of that promise. A single leak and none of it
is worth anything, which is why the contract is written down, why it is
enforced three separate ways, and why the test that checks it was written
before the system it protects.

## The rules

Inside `cassette/sim/` and `cassette/kv/`:

| Forbidden | Use instead | Why |
|---|---|---|
| `time.time()`, `time.monotonic()`, `datetime.now()` | `env.now()` | wall time is not part of the seed |
| the global `random` module, `os.urandom`, `secrets` | `env.random()` | one seeded source, or none |
| `uuid.uuid4()` | a counter | identifiers have to replay |
| iterating a `set` | `sorted(...)` | set order depends on insertion history and hashing |
| relying on `dict` order for decisions | sort the keys | insertion order is a property of the code, not the run |
| `hash()` on a `str` | anything else | string hashes are salted per process |
| `threading`, `asyncio`, `multiprocessing` | the event queue | the OS scheduler is not seedable |
| file, socket or console I/O | inject it through `Env` | the outside world is not reproducible |

Two structural rules matter more than the list:

**A node's only door is `Env`.** A replica never imports the scheduler, the
clock, the network or the RNG. It receives an `Env` and can reach the outside
world through nothing else. This is what turns determinism from a discipline
somebody has to remember into a property of the architecture.

**Only the scheduler moves time.** `VirtualClock.advance_to` is called from
exactly one place, when an event is dequeued. Clock skew shifts what a node
*reads*; it never changes when a node is *scheduled*. Without that separation a
skewed clock becomes a second, hidden source of ordering.

## How it is enforced

**1. A lint rule.** `ruff` bans the modules above through `TID251`, with the
message attached to each one. It fails in the editor, before the code is even
saved. Lifted for `tests/` and for `cassette/sim/rng.py`.

**2. An AST guard.** `tests/test_determinism_guard.py` parses every file under
the two guarded packages and fails on a banned import or a banned builtin call.
It is precise where the lint rule is blunt — it allows `random` in exactly one
file and nowhere else — and it lives in the test suite rather than in a config
file that a `# noqa` can silence. Its allowlist has one entry, and a test
asserts it stays that way.

**3. T-3, the trace hash.** `tests/test_determinism.py` runs a thousand seeds
twice each and compares the SHA-256 of the canonical trace. This is the only
check that can catch a leak nobody thought to ban — the unordered set, the
floating-point path that happened to differ — and it is deliberately the
crudest assertion in the repository. It reports *that* something diverged, not
*what*, because an assertion clever enough to say what could also be clever
enough to miss it.

A fourth, in CI: the whole suite runs again under a `PYTHONHASHSEED` drawn at
random on every push.

## Two decisions that look like details

**Every helper on `Rng` derives from `Random.random()`.** `randint`, `choice`,
`sample` and `shuffle` are reimplemented on top of it rather than delegated.
`random()` is the one Mersenne Twister primitive CPython documents as stable;
the others have changed their internal draw patterns between releases. Twenty
lines buy trace hashes that survive a Python upgrade.

**Dice are rolled even when a fault is switched off.** `Rng.chance(0.0)`
consumes a draw and returns `False`. Setting `drop_rate` to zero therefore
changes what happens to each message without shifting every decision taken
afterwards.

That one is not cosmetic. The shrinker's entire method is "remove a fault and
see whether the bug survives", and that question only means something if
removing a fault leaves the rest of the schedule where it was.

## What is not covered

The guard reads imports and builtin calls. It cannot see an unordered set being
iterated, a float that lands differently, or a C extension with its own state.
T-3 is the net underneath, and the reason it runs a thousand seeds rather than
ten.

Cassette is also a logic simulator, not a performance model. It reproduces
*orderings*, not real thread contention, syscall latency or kernel behaviour.
