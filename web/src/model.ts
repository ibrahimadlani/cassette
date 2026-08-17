/**
 * Reconstructing what the cluster looked like at a given moment.
 *
 * The trace is a list of things that happened. The diagram needs the opposite:
 * what was true at time t. So this folds the events once into a frame per
 * event, and every view afterwards is an index lookup rather than a scan.
 *
 * Values are recovered from `msg_send` bodies matched to their `msg_deliver`
 * by id. That indirection is deliberate on the Python side — the body appears
 * once, not on every copy of a duplicated message — and it means the replayer
 * knows exactly what each replica stored without the simulator telling it.
 */

import type { Trace, TraceEvent, Value } from "./trace";
import { replicaIds } from "./trace";

export type NodeStatus = "up" | "down" | "paused";

export interface NodeState {
  status: NodeStatus;
  value: Value;
  version: [number, number];
  /** Index of the partition group this node is in, or null when whole. */
  group: number | null;
}

export interface Flight {
  id: number;
  from: number;
  to: number;
  kind: string;
  sentAt: number;
  arrivesAt: number;
  /** Set when the message never lands. */
  lostAt: number | null;
  lostBecause: string | null;
}

export interface Frame {
  /** Index into trace.events. -1 is the state before anything happened. */
  index: number;
  t: number;
  nodes: Map<number, NodeState>;
  partition: number[][] | null;
}

const ZERO: [number, number] = [0, -1];

function blankNodes(trace: Trace): Map<number, NodeState> {
  const nodes = new Map<number, NodeState>();
  for (const id of replicaIds(trace)) {
    nodes.set(id, { status: "up", value: null, version: ZERO, group: null });
  }
  return nodes;
}

function copyNodes(nodes: Map<number, NodeState>): Map<number, NodeState> {
  return new Map(Array.from(nodes, ([id, state]) => [id, { ...state }]));
}

function groupOf(partition: number[][] | null, node: number): number | null {
  if (!partition) return null;
  const index = partition.findIndex((group) => group.includes(node));
  return index === -1 ? null : index;
}

function newer(left: [number, number], right: [number, number]): boolean {
  return left[0] !== right[0] ? left[0] > right[0] : left[1] > right[1];
}

/**
 * One frame per event, plus a frame for the state before the run started.
 *
 * `frames[i + 1]` is the state after `trace.events[i]`.
 */
export function buildFrames(trace: Trace): Frame[] {
  const bodies = new Map<number, TraceEvent>();
  let nodes = blankNodes(trace);
  let partition: number[][] | null = null;

  const frames: Frame[] = [{ index: -1, t: 0, nodes: copyNodes(nodes), partition: null }];

  trace.events.forEach((event, index) => {
    nodes = copyNodes(nodes);

    switch (event.type) {
      case "msg_send":
        if (event.id !== undefined) bodies.set(event.id, event);
        break;

      case "msg_deliver": {
        const sent = event.id === undefined ? undefined : bodies.get(event.id);
        const body = sent?.body;
        const target = event.to;
        if (sent?.kind === "write_request" && body && target !== undefined) {
          const state = nodes.get(target);
          const version = body["version"] as [number, number] | undefined;
          if (state && version && newer(version, state.version)) {
            state.value = (body["value"] ?? null) as Value;
            state.version = version;
          }
        }
        break;
      }

      case "partition_start":
        partition = event.groups ?? null;
        break;

      case "partition_end":
        partition = null;
        break;

      case "node_crash":
        setStatus(nodes, event.node, "down");
        break;

      case "node_restart":
        setStatus(nodes, event.node, "up");
        break;

      case "node_pause":
        setStatus(nodes, event.node, "paused");
        break;

      case "node_resume":
        setStatus(nodes, event.node, "up");
        break;

      case "msg_drop":
        break;
    }

    for (const [id, state] of nodes) {
      state.group = groupOf(partition, id);
    }

    frames.push({ index, t: event.t, nodes: copyNodes(nodes), partition });
  });

  return frames;
}

function setStatus(
  nodes: Map<number, NodeState>,
  node: number | undefined,
  status: NodeStatus,
): void {
  if (node === undefined) return;
  const state = nodes.get(node);
  if (state) state.status = status;
}

/**
 * Every message, matched to its delivery or to its death.
 *
 * A duplicated message has one send and two deliveries under the same id, so
 * it appears twice here — which is exactly how it should be drawn.
 */
export function buildFlights(trace: Trace): Flight[] {
  const sends = new Map<number, TraceEvent>();
  const flights: Flight[] = [];

  for (const event of trace.events) {
    if (event.id === undefined) continue;

    if (event.type === "msg_send") {
      sends.set(event.id, event);
      continue;
    }

    const sent = sends.get(event.id);
    if (!sent || sent.sender === undefined || sent.to === undefined) continue;

    if (event.type === "msg_deliver") {
      flights.push({
        id: event.id,
        from: sent.sender,
        to: sent.to,
        kind: sent.kind ?? "?",
        sentAt: sent.t,
        arrivesAt: event.t,
        lostAt: null,
        lostBecause: null,
      });
    } else if (event.type === "msg_drop") {
      flights.push({
        id: event.id,
        from: sent.sender,
        to: sent.to,
        kind: sent.kind ?? "?",
        sentAt: sent.t,
        arrivesAt: event.t,
        lostAt: event.t,
        lostBecause: event.reason ?? "loss",
      });
    }
  }

  // A message dropped on the wire has no msg_send in front of it, so it never
  // reaches the loop above. Those are already accounted for: the simulator
  // reports the drop instead of the send, and there is nothing to draw.
  return flights;
}

export interface Band {
  from: number;
  to: number;
}

export interface Outage extends Band {
  node: number;
  kind: "down" | "paused";
}

/** When the cluster was split, as spans of logical time. */
export function partitionBands(trace: Trace, span: number): Band[] {
  const bands: Band[] = [];
  let open: number | null = null;
  for (const event of trace.events) {
    if (event.type === "partition_start" && open === null) open = event.t;
    if (event.type === "partition_end" && open !== null) {
      bands.push({ from: open, to: event.t });
      open = null;
    }
  }
  // A partition still open when the run stopped runs to the end of the chart
  // rather than vanishing, which is what actually happened.
  if (open !== null) bands.push({ from: open, to: span });
  return bands;
}

/** When each node was down or frozen. */
export function nodeOutages(trace: Trace, span: number): Outage[] {
  const outages: Outage[] = [];
  const open = new Map<number, { from: number; kind: "down" | "paused" }>();

  for (const event of trace.events) {
    const node = event.node;
    if (node === undefined) continue;

    if (event.type === "node_crash") open.set(node, { from: event.t, kind: "down" });
    else if (event.type === "node_pause") open.set(node, { from: event.t, kind: "paused" });
    else if (event.type === "node_restart" || event.type === "node_resume") {
      const started = open.get(node);
      if (started) {
        outages.push({ node, from: started.from, to: event.t, kind: started.kind });
        open.delete(node);
      }
    }
  }

  for (const [node, started] of open) {
    outages.push({ node, from: started.from, to: span, kind: started.kind });
  }
  return outages;
}

/**
 * A round spacing for the time axis, close to a tenth of the span.
 *
 * Ticks at 137 ms are worse than no ticks: the reader stops reading the run and
 * starts reading the axis.
 */
export function tickStep(span: number): number {
  const rough = span / 10;
  const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(rough, 1))));
  const nice = [1, 2, 5, 10].map((multiple) => multiple * magnitude);
  return nice.find((candidate) => candidate >= rough) ?? magnitude * 10;
}

/** Every tick on the axis, including both ends. */
export function ticks(span: number): number[] {
  const step = tickStep(span);
  const out: number[] = [];
  for (let t = 0; t <= span; t += step) out.push(t);
  return out;
}

/** A version stamp as `counter.node`, or an em dash for the initial value. */
export function stamp(version: [number, number] | undefined): string {
  if (!version) return "—";
  const [counter, node] = version;
  return counter === 0 ? "—" : `${counter}.${node}`;
}

/**
 * Whether two replicas hold different values under the same version stamp.
 *
 * This is the shape of the bug the demo exists to show, and it is visible in
 * the replica table several seconds before any client notices.
 */
export function disagreeUnderTheSameStamp(
  values: (number | null)[],
  stamps: string[],
): boolean {
  const byStamp = new Map<string, Set<number | null>>();
  stamps.forEach((key, index) => {
    if (key === "—") return;
    const seen = byStamp.get(key) ?? new Set<number | null>();
    seen.add(values[index] ?? null);
    byStamp.set(key, seen);
  });
  return Array.from(byStamp.values()).some((seen) => seen.size > 1);
}

/** The index of the last frame at or before `t`. */
export function frameAt(frames: Frame[], t: number): number {
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    const frame = frames[middle];
    if (frame && frame.t <= t) low = middle;
    else high = middle - 1;
  }
  return low;
}
