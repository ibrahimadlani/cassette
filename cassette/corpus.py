"""The regression corpus.

Every seed that ever produced a violation goes in `regressions.txt` and stays
there. `tests/test_regressions.py` replays all of them on every run, so a bug
that has been fixed once cannot come back quietly.

The file is a plain list of `key=value` lines rather than JSON, because it is
read far more often by people than by programs: it should be greppable, it
should diff usefully, and adding an entry by hand after a manual investigation
should not require knowing a schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cassette.kv.config import StoreConfig
from cassette.scenario import PRESETS, Scenario, WorkloadSpec, generate

DEFAULT_PATH = Path("regressions.txt")

HEADER = """\
# Cassette regression corpus.
#
# Every seed here produced a linearizability violation at some point. They are
# all replayed by tests/test_regressions.py, so a bug that has been fixed once
# cannot come back without the suite going red.
#
# Written by `cassette fuzz`. Entries are only ever removed by hand, and only
# with a note in docs/FINDINGS.md saying why.
"""


@dataclass(frozen=True, slots=True)
class Entry:
    """One reproducible failure."""

    seed: int
    preset: str = "standard"
    nodes: int = 5
    read_quorum: int = 3
    write_quorum: int = 3
    clients: int = 3
    operations: int = 8
    horizon_ms: int = 60_000
    note: str = ""

    def to_line(self) -> str:
        """The corpus file's one-line form."""
        fields = (
            f"seed={self.seed}",
            f"preset={self.preset}",
            f"nodes={self.nodes}",
            f"read={self.read_quorum}",
            f"write={self.write_quorum}",
            f"clients={self.clients}",
            f"ops={self.operations}",
            f"horizon={self.horizon_ms}",
        )
        line = " ".join(fields)
        return f"{line}  # {self.note}" if self.note else line

    @classmethod
    def from_line(cls, line: str) -> Entry:
        """Parse one line, ignoring any trailing note."""
        body, _, note = line.partition("#")
        fields = dict(token.split("=", 1) for token in body.split())
        return cls(
            seed=int(fields["seed"]),
            preset=fields.get("preset", "standard"),
            nodes=int(fields.get("nodes", 5)),
            read_quorum=int(fields.get("read", 3)),
            write_quorum=int(fields.get("write", 3)),
            clients=int(fields.get("clients", 3)),
            operations=int(fields.get("ops", 8)),
            horizon_ms=int(fields.get("horizon", 60_000)),
            note=note.strip(),
        )

    def to_scenario(self) -> Scenario:
        """Rebuild the exact scenario this entry describes."""
        return generate(
            seed=self.seed,
            store=StoreConfig(
                replicas=self.nodes,
                read_quorum=self.read_quorum,
                write_quorum=self.write_quorum,
            ),
            faults=PRESETS[self.preset],
            workload=WorkloadSpec(clients=self.clients, operations=self.operations),
            horizon_ms=self.horizon_ms,
        )


def load(path: Path = DEFAULT_PATH) -> list[Entry]:
    """Read the corpus. A missing file is an empty corpus, not an error."""
    if not path.is_file():
        return []
    entries: list[Entry] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(Entry.from_line(line))
    return entries


def save(entries: list[Entry], path: Path = DEFAULT_PATH) -> None:
    """Write the corpus, sorted by seed so the file diffs cleanly."""
    ordered = sorted(entries, key=lambda entry: (entry.preset, entry.seed))
    body = "\n".join(entry.to_line() for entry in ordered)
    path.write_text(f"{HEADER}\n{body}\n" if body else HEADER, encoding="utf-8")


def add(new: list[Entry], path: Path = DEFAULT_PATH) -> int:
    """Merge `new` into the corpus, keeping it unique. Returns how many were added."""
    existing = load(path)
    known = {(entry.preset, entry.seed) for entry in existing}
    fresh = [entry for entry in new if (entry.preset, entry.seed) not in known]
    if fresh:
        save(existing + fresh, path)
    return len(fresh)
