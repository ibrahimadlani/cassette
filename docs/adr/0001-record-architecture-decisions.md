# 1. Record architecture decisions

- Status: accepted
- Date: 2026-07-27

## Context

Cassette is built around a handful of decisions that are cheap to make now and
expensive to reverse later: how time advances, how randomness is threaded
through the system, what the system under test looks like, and how correctness
is judged. Six months from now the code will still be there, but the reasoning
behind it will not.

I also expect to be asked about these choices out loud. A decision I cannot
justify is indistinguishable from a decision I never made.

## Decision

Architecture decisions are recorded as short markdown files under `docs/adr/`,
numbered sequentially, in the format described by Michael Nygard.

Each record states the context, the decision, and the consequences — including
the ones I do not like. Records are immutable: a decision that stops being true
gets a new record that supersedes the old one, and the old one stays in the
repository with its status updated.

## Consequences

- Reviewing the `docs/adr/` directory gives a complete picture of why the
  codebase looks the way it does, in reading order.
- Writing a record forces the alternatives to be named. Several of the records
  in this repository exist because writing them changed my mind.
- There is a small cost per decision. I only pay it for choices that are
  structural — not for every library or naming preference.
