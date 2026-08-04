"""The system under test: a quorum-replicated key-value store.

Nothing in this package imports the simulator. Replicas and clients receive an
`Env` and reach the world through it and nothing else, which is what makes the
whole thing reproducible. See `docs/DETERMINISM.md`.
"""
