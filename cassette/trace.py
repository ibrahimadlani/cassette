"""The trace: what a run produced, in a form that outlives the process.

A trace has to be enough on its own. The web replayer never runs the simulator;
it reads one of these and draws it. So the envelope carries the scenario that
produced the run, every event in order, the client history, and the verdict —
and `schema/trace.schema.json` says so in a form a machine can check.

The version field earns its place the first time the format changes. A replayer
that meets a trace it does not understand should say so rather than draw
something misleading.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cassette.checker.history import History
from cassette.scenario import Scenario
from cassette.sim.recorder import digest_of
from cassette.sim.types import JsonDict, JsonValue

TRACE_VERSION = 1


@dataclass(frozen=True, slots=True)
class Trace:
    """One recorded run."""

    scenario: Scenario
    events: list[JsonDict] = field(default_factory=list)
    history: list[JsonDict] = field(default_factory=list)
    verdict: JsonDict | None = None
    version: int = TRACE_VERSION

    @property
    def seed(self) -> int:
        """The seed the run came from."""
        return self.scenario.seed

    def to_json(self) -> JsonDict:
        """The whole envelope."""
        return {
            "version": self.version,
            "seed": self.scenario.seed,
            "scenario": self.scenario.to_json(),
            "events": list(self.events),
            "history": list(self.history),
            "verdict": self.verdict,
        }

    @classmethod
    def from_json(cls, data: JsonDict) -> Trace:
        """Rebuild a trace, refusing a version this build does not know."""
        version = int(str(data["version"]))
        if version != TRACE_VERSION:
            raise ValueError(f"trace version {version} is not supported (this build reads v1)")
        verdict = data.get("verdict")
        return cls(
            scenario=Scenario.from_json(_as_dict(data["scenario"])),
            events=[_as_dict(entry) for entry in _as_list(data["events"])],
            history=[_as_dict(entry) for entry in _as_list(data["history"])],
            verdict=None if verdict is None else _as_dict(verdict),
            version=version,
        )

    def with_verdict(self, verdict: JsonDict) -> Trace:
        """The same trace, with the checker's answer attached."""
        return Trace(
            scenario=self.scenario,
            events=self.events,
            history=self.history,
            verdict=verdict,
            version=self.version,
        )

    def digest(self) -> str:
        """A fingerprint of the whole envelope, used by the determinism test."""
        return digest_of(self.to_json())


def _as_dict(raw: JsonValue) -> JsonDict:
    assert isinstance(raw, dict)
    return dict(raw)


def _as_list(raw: JsonValue) -> list[JsonValue]:
    assert isinstance(raw, list)
    return list(raw)


def trace_of(scenario: Scenario, events: list[JsonDict], history: History) -> Trace:
    """Assemble a trace from the pieces a run produces."""
    return Trace(scenario=scenario, events=events, history=history.to_json())
