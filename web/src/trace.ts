/**
 * The trace format, as the replayer sees it.
 *
 * These types mirror `schema/trace.schema.json`. The schema is the contract;
 * this file is one half of it, and `cassette/trace.py` is the other. If they
 * disagree, the schema is right.
 */

export const TRACE_VERSION = 1;

export type Value = number | null;

export type EventType =
  | "msg_send"
  | "msg_deliver"
  | "msg_drop"
  | "partition_start"
  | "partition_end"
  | "node_crash"
  | "node_restart"
  | "node_pause"
  | "node_resume";

export interface TraceEvent {
  t: number;
  type: EventType;
  id?: number;
  sender?: number;
  to?: number;
  node?: number;
  kind?: string;
  reason?: "loss" | "partition" | "crashed";
  copies?: number;
  until?: number;
  body?: Record<string, unknown>;
  groups?: number[][];
}

export type OperationKind = "read" | "write" | "cas";

export interface Operation {
  index: number;
  client: number;
  kind: OperationKind;
  key: string;
  argument: Value;
  expected: Value;
  invoked: number;
  returned: number;
  outcome: "ok" | "unknown";
  result: Value;
}

export interface StoreConfig {
  replicas: number;
  read_quorum: number;
  write_quorum: number;
  request_timeout_ms: number;
  stable_versions: boolean;
  read_repair: boolean;
}

export interface InjectedFault {
  at_ms: number;
  kind: "partition" | "crash" | "pause";
  duration_ms: number;
  targets: number[];
}

export interface Scenario {
  seed: number;
  store: StoreConfig;
  faults: Record<string, unknown>;
  plans: unknown[][];
  horizon_ms: number;
  schedule: InjectedFault[] | null;
}

export interface Verdict {
  linearizable: boolean;
  key: string | null;
  operation: number | null;
  explanation: string | null;
  checked_operations: number;
  exhausted: boolean;
}

export interface Trace {
  version: number;
  seed: number;
  scenario: Scenario;
  events: TraceEvent[];
  history: Operation[];
  verdict: Verdict | null;
}

export interface CatalogueEntry {
  slug: string;
  title: string;
  blurb: string;
  seed: number;
  replicas: number;
  operations: number;
  events: number;
  faulty: boolean;
  linearizable: boolean;
  bytes: number;
}

/**
 * Turn a parsed JSON payload into a Trace, refusing anything it does not
 * understand.
 *
 * A replayer that quietly draws a trace from a format it does not know is
 * worse than one that refuses: it produces a picture that looks right.
 */
export function parseTrace(payload: unknown): Trace {
  if (typeof payload !== "object" || payload === null) {
    throw new Error("not a trace: expected an object");
  }
  const trace = payload as Partial<Trace>;

  if (trace.version !== TRACE_VERSION) {
    throw new Error(
      `trace version ${String(trace.version)} is not supported (this build reads v${TRACE_VERSION})`,
    );
  }
  if (!Array.isArray(trace.events)) {
    throw new Error("not a trace: events must be an array");
  }
  if (!Array.isArray(trace.history)) {
    throw new Error("not a trace: history must be an array");
  }
  if (typeof trace.scenario !== "object" || trace.scenario === null) {
    throw new Error("not a trace: scenario is missing");
  }

  return {
    version: trace.version,
    seed: Number(trace.seed ?? trace.scenario.seed),
    scenario: trace.scenario,
    events: trace.events,
    history: trace.history,
    verdict: trace.verdict ?? null,
  };
}

/** Replica ids, which are always the low node ids. */
export function replicaIds(trace: Trace): number[] {
  return Array.from({ length: trace.scenario.store.replicas }, (_, index) => index);
}

/** Client ids, in the order they first appear in the history. */
export function clientIds(trace: Trace): number[] {
  const seen: number[] = [];
  for (const op of trace.history) {
    if (!seen.includes(op.client)) seen.push(op.client);
  }
  return seen.sort((left, right) => left - right);
}

/** Name clients A, B, C… so the diagram does not have to say "client 6". */
export function clientLabels(trace: Trace): Map<number, string> {
  const labels = new Map<number, string>();
  clientIds(trace).forEach((id, index) => {
    labels.set(id, String.fromCharCode(65 + (index % 26)));
  });
  return labels;
}

/** The last timestamp anything happens at. */
export function duration(trace: Trace): number {
  const lastEvent = trace.events.at(-1)?.t ?? 0;
  const lastReturn = trace.history.reduce((latest, op) => Math.max(latest, op.returned), 0);
  return Math.max(lastEvent, lastReturn, 1);
}
