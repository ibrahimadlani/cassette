# 5. Pre-generated traces for the web replayer

- Status: accepted
- Date: 2026-08-13

## Context

The demo has to be a link. A recruiter or an engineer who has to clone a
repository and install Python to see what the project does will not see what
the project does.

That means a browser needs traces. There were three ways to get them there.

**Run the simulator in the browser.** Pyodide, or the whole core rewritten in
TypeScript. The first ships several megabytes of WebAssembly to draw a diagram;
the second means two implementations of the determinism contract, which is the
one part of this project that must not have two implementations. Either way it
is days of work for a "try your own parameters" slider.

**A small backend.** Something to run `cassette run --seed N` on demand. Now
the demo has a server, a cost, a cold start and something that can be down when
somebody opens the link.

**Export a handful of traces at build time.** A static site.

## Decision

A script exports a small hand-picked catalogue — six runs, 359 KiB — into
`web/public/traces/`, and the replayer reads them. No simulator in the browser,
no server, no WebAssembly.

The catalogue is chosen rather than random: the reduced counterexample, the
same bug unreduced, a partition, crash-restart, everything at once, and a
healthy cluster. Those are the six things worth looking at.

## Consequences

- The demo is a GitHub Pages URL that costs nothing, cannot be down, and stays
  up long after I have stopped paying attention to it.
- Deep links work: `?trace=minimal-violation` opens on the bug.
- The trace format becomes a real contract between two languages rather than an
  internal detail, which is why `schema/trace.schema.json` exists and why both
  sides validate against it in CI.
- No "break it yourself" mode. A visitor cannot pick their own drop rate and
  watch what happens. That is the price, it was on the cut list from the start,
  and the six exhibits cover the same ground with none of the risk.
- The catalogue has to be rebuilt when the trace format changes. `make traces`
  does it, and the web tests read the exported files as fixtures, so forgetting
  turns the build red rather than shipping a replayer that draws the wrong
  picture.
