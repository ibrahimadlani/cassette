import { describe, expect, it } from "vitest";

import { buildFlights, buildFrames, frameAt } from "./model";
import type { Trace, TraceEvent } from "./trace";
import { clientLabels, duration, parseTrace, replicaIds } from "./trace";

function trace(events: TraceEvent[], replicas = 3): Trace {
  return {
    version: 1,
    seed: 1,
    scenario: {
      seed: 1,
      store: {
        replicas,
        read_quorum: 2,
        write_quorum: 2,
        request_timeout_ms: 400,
        stable_versions: true,
        read_repair: true,
      },
      faults: {},
      plans: [],
      horizon_ms: 60000,
      schedule: [],
    },
    events,
    history: [],
    verdict: null,
  };
}

function write(id: number, to: number, at: number, value: number, version: [number, number]) {
  return {
    t: at,
    type: "msg_send" as const,
    id,
    sender: 0,
    to,
    kind: "write_request",
    body: { key: "x", value, version },
  };
}

describe("parseTrace", () => {
  it("accepts a well-formed trace", () => {
    expect(parseTrace(trace([])).version).toBe(1);
  });

  it("refuses a version it does not know", () => {
    expect(() => parseTrace({ ...trace([]), version: 99 })).toThrow(/version 99 is not supported/);
  });

  it("refuses something that is not an object", () => {
    expect(() => parseTrace("nope")).toThrow(/expected an object/);
  });

  it("refuses a trace with no events array", () => {
    expect(() => parseTrace({ ...trace([]), events: null })).toThrow(/events must be an array/);
  });

  it("refuses a trace with no scenario", () => {
    expect(() => parseTrace({ version: 1, events: [], history: [] })).toThrow(/scenario is missing/);
  });
});

describe("buildFrames", () => {
  it("starts from a clean cluster", () => {
    const frames = buildFrames(trace([]));
    expect(frames).toHaveLength(1);
    expect(frames[0]!.nodes.get(0)).toEqual({
      status: "up",
      value: null,
      version: [0, -1],
      group: null,
    });
  });

  it("produces one frame per event, plus the initial one", () => {
    expect(buildFrames(trace([{ t: 5, type: "node_crash", node: 1 }]))).toHaveLength(2);
  });

  it("applies a delivered write to the recipient", () => {
    const frames = buildFrames(
      trace([
        write(0, 1, 10, 7, [1, 0]),
        { t: 20, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
      ]),
    );
    expect(frames.at(-1)!.nodes.get(1)!.value).toBe(7);
    expect(frames.at(-1)!.nodes.get(1)!.version).toEqual([1, 0]);
  });

  it("leaves a replica untouched until the write actually lands", () => {
    const frames = buildFrames(trace([write(0, 1, 10, 7, [1, 0])]));
    expect(frames.at(-1)!.nodes.get(1)!.value).toBeNull();
  });

  it("ignores a write older than what the replica holds", () => {
    const frames = buildFrames(
      trace([
        write(0, 1, 10, 9, [2, 0]),
        { t: 11, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
        write(1, 1, 12, 3, [1, 0]),
        { t: 13, type: "msg_deliver", id: 1, sender: 0, to: 1, kind: "write_request" },
      ]),
    );
    expect(frames.at(-1)!.nodes.get(1)!.value).toBe(9);
  });

  it("breaks a version tie on the node id", () => {
    const frames = buildFrames(
      trace([
        write(0, 1, 10, 5, [1, 0]),
        { t: 11, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
        write(1, 1, 12, 6, [1, 2]),
        { t: 13, type: "msg_deliver", id: 1, sender: 0, to: 1, kind: "write_request" },
      ]),
    );
    expect(frames.at(-1)!.nodes.get(1)!.value).toBe(6);
  });

  it("tracks crash and restart", () => {
    const frames = buildFrames(
      trace([
        { t: 10, type: "node_crash", node: 2 },
        { t: 50, type: "node_restart", node: 2 },
      ]),
    );
    expect(frames[1]!.nodes.get(2)!.status).toBe("down");
    expect(frames[2]!.nodes.get(2)!.status).toBe("up");
  });

  it("tracks pause and resume", () => {
    const frames = buildFrames(
      trace([
        { t: 10, type: "node_pause", node: 1, until: 60 },
        { t: 60, type: "node_resume", node: 1 },
      ]),
    );
    expect(frames[1]!.nodes.get(1)!.status).toBe("paused");
    expect(frames[2]!.nodes.get(1)!.status).toBe("up");
  });

  it("assigns partition groups and clears them on heal", () => {
    const frames = buildFrames(
      trace([
        { t: 10, type: "partition_start", groups: [[0], [1, 2]] },
        { t: 90, type: "partition_end" },
      ]),
    );
    expect(frames[1]!.nodes.get(0)!.group).toBe(0);
    expect(frames[1]!.nodes.get(2)!.group).toBe(1);
    expect(frames[2]!.nodes.get(0)!.group).toBeNull();
    expect(frames[2]!.partition).toBeNull();
  });

  it("does not let a later frame mutate an earlier one", () => {
    const frames = buildFrames(
      trace([
        { t: 10, type: "node_crash", node: 0 },
        { t: 20, type: "node_restart", node: 0 },
      ]),
    );
    expect(frames[1]!.nodes.get(0)!.status).toBe("down");
  });
});

describe("buildFlights", () => {
  it("pairs a send with its delivery", () => {
    const flights = buildFlights(
      trace([
        write(0, 1, 10, 7, [1, 0]),
        { t: 25, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
      ]),
    );
    expect(flights).toEqual([
      {
        id: 0,
        from: 0,
        to: 1,
        kind: "write_request",
        sentAt: 10,
        arrivesAt: 25,
        lostAt: null,
        lostBecause: null,
      },
    ]);
  });

  it("marks a message that was dropped after it was sent", () => {
    const flights = buildFlights(
      trace([
        write(0, 1, 10, 7, [1, 0]),
        { t: 25, type: "msg_drop", id: 0, sender: 0, to: 1, reason: "partition" },
      ]),
    );
    expect(flights[0]!.lostAt).toBe(25);
    expect(flights[0]!.lostBecause).toBe("partition");
  });

  it("draws a duplicate twice", () => {
    const flights = buildFlights(
      trace([
        { ...write(0, 1, 10, 7, [1, 0]), copies: 2 },
        { t: 20, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
        { t: 40, type: "msg_deliver", id: 0, sender: 0, to: 1, kind: "write_request" },
      ]),
    );
    expect(flights).toHaveLength(2);
    expect(flights.map((flight) => flight.arrivesAt)).toEqual([20, 40]);
  });

  it("ignores a drop with no send in front of it", () => {
    const flights = buildFlights(
      trace([{ t: 5, type: "msg_drop", id: 7, sender: 0, to: 1, reason: "loss" }]),
    );
    expect(flights).toEqual([]);
  });
});

describe("frameAt", () => {
  const frames = buildFrames(
    trace([
      { t: 10, type: "node_crash", node: 0 },
      { t: 40, type: "node_restart", node: 0 },
      { t: 90, type: "node_crash", node: 1 },
    ]),
  );

  it("returns the initial frame before anything happens", () => {
    expect(frameAt(frames, 0)).toBe(0);
    expect(frameAt(frames, 9)).toBe(0);
  });

  it("lands exactly on an event", () => {
    expect(frames[frameAt(frames, 40)]!.t).toBe(40);
  });

  it("returns the last frame at or before the time", () => {
    expect(frames[frameAt(frames, 60)]!.t).toBe(40);
  });

  it("clamps past the end", () => {
    expect(frameAt(frames, 10_000)).toBe(frames.length - 1);
  });
});

describe("trace helpers", () => {
  it("lists replica ids from the store size", () => {
    expect(replicaIds(trace([], 4))).toEqual([0, 1, 2, 3]);
  });

  it("labels clients A, B, C in id order", () => {
    const withHistory = {
      ...trace([]),
      history: [
        { client: 6, index: 0 } as never,
        { client: 5, index: 1 } as never,
        { client: 6, index: 2 } as never,
      ],
    };
    expect(Array.from(clientLabels(withHistory).entries())).toEqual([
      [5, "A"],
      [6, "B"],
    ]);
  });

  it("takes the duration from the last event", () => {
    expect(duration(trace([{ t: 250, type: "node_crash", node: 0 }]))).toBe(250);
  });

  it("never reports a duration of zero", () => {
    expect(duration(trace([]))).toBe(1);
  });
});
