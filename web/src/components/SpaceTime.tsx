/**
 * The space-time diagram.
 *
 * One horizontal lane per participant, logical time running left to right,
 * every message a diagonal from the sender's lane at the instant it was sent to
 * the recipient's lane at the instant it landed. The slope is the latency; a
 * message that crosses another is a reordering; a line that stops short is a
 * message that never arrived.
 *
 * Everything is SVG. There are a few thousand elements at most, the whole thing
 * is inspectable in devtools, and it scales without going blurry — none of
 * which is true of a canvas.
 */

import { useMemo } from "react";

import type { Flight, Frame } from "../model";
import type { Operation, Trace } from "../trace";
import { clientLabels, duration, replicaIds } from "../trace";

const LANE_HEIGHT = 46;
const TOP = 28;
const LEFT = 74;
const RIGHT = 24;
const WIDTH = 1100;

interface Props {
  trace: Trace;
  frames: Frame[];
  flights: Flight[];
  frame: number;
  onScrub: (time: number) => void;
}

export function SpaceTime({ trace, frames, flights, frame, onScrub }: Props) {
  const replicas = replicaIds(trace);
  const labels = clientLabels(trace);
  const clients = Array.from(labels.keys());
  const lanes = [...replicas, ...clients];
  const height = TOP + lanes.length * LANE_HEIGHT + 24;
  const span = duration(trace);
  const now = frames[frame]?.t ?? 0;

  const x = (t: number) => LEFT + (t / span) * (WIDTH - LEFT - RIGHT);
  const y = (node: number) => TOP + lanes.indexOf(node) * LANE_HEIGHT + LANE_HEIGHT / 2;

  const bands = useMemo(() => partitionBands(trace, span), [trace, span]);
  const outages = useMemo(() => nodeOutages(trace, span), [trace, span]);
  const violating = trace.verdict?.operation ?? null;

  function scrub(event: React.MouseEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    const position = (ratio * WIDTH - LEFT) / (WIDTH - LEFT - RIGHT);
    onScrub(Math.max(0, Math.min(1, position)) * span);
  }

  return (
    <svg
      className="spacetime"
      viewBox={`0 0 ${WIDTH} ${height}`}
      role="img"
      aria-label="Space-time diagram of the simulated run"
      onClick={scrub}
    >
      {bands.map((band, index) => (
        <rect
          key={`partition-${index}`}
          className="band band--partition"
          x={x(band.from)}
          y={TOP - 8}
          width={Math.max(1, x(band.to) - x(band.from))}
          height={lanes.length * LANE_HEIGHT + 8}
        >
          <title>partition, {band.from}–{band.to} ms</title>
        </rect>
      ))}

      {outages.map((outage, index) => (
        <rect
          key={`outage-${index}`}
          className={`band band--${outage.kind}`}
          x={x(outage.from)}
          y={y(outage.node) - 11}
          width={Math.max(2, x(outage.to) - x(outage.from))}
          height={22}
        >
          <title>
            n{outage.node} {outage.kind}, {outage.from}–{outage.to} ms
          </title>
        </rect>
      ))}

      {lanes.map((node) => (
        <g key={`lane-${node}`}>
          <line className="lane" x1={LEFT} y1={y(node)} x2={WIDTH - RIGHT} y2={y(node)} />
          <text className="lane-label" x={LEFT - 12} y={y(node) + 4} textAnchor="end">
            {labels.has(node) ? `client ${labels.get(node)}` : `n${node}`}
          </text>
        </g>
      ))}

      {flights.map((flight, index) => (
        <line
          key={`flight-${index}`}
          className={[
            "flight",
            `flight--${flight.kind.split("_")[0]}`,
            flight.lostAt ? "flight--lost" : "",
            flight.arrivesAt <= now ? "flight--past" : "flight--future",
          ]
            .filter(Boolean)
            .join(" ")}
          x1={x(flight.sentAt)}
          y1={y(flight.from)}
          x2={x(flight.arrivesAt)}
          y2={flight.lostAt ? midpoint(y(flight.from), y(flight.to)) : y(flight.to)}
        >
          <title>
            {flight.kind} n{flight.from} to n{flight.to}, {flight.sentAt}–{flight.arrivesAt} ms
            {flight.lostBecause ? ` (dropped: ${flight.lostBecause})` : ""}
          </title>
        </line>
      ))}

      {flights
        .filter((flight) => flight.lostAt !== null)
        .map((flight, index) => (
          <text
            key={`lost-${index}`}
            className="lost-mark"
            x={x(flight.arrivesAt)}
            y={midpoint(y(flight.from), y(flight.to)) + 4}
            textAnchor="middle"
          >
            ×
          </text>
        ))}

      {trace.history.map((op) => (
        <g key={`op-${op.index}`}>
          <rect
            className={[
              "operation",
              `operation--${op.kind}`,
              op.outcome === "unknown" ? "operation--unknown" : "",
              op.index === violating ? "operation--violating" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            x={x(op.invoked)}
            y={y(op.client) - 9}
            width={Math.max(3, x(returnedAt(op, span)) - x(op.invoked))}
            height={18}
            rx={3}
          >
            <title>{describe(op, labels.get(op.client) ?? String(op.client))}</title>
          </rect>
          <text className="operation-label" x={x(op.invoked) + 4} y={y(op.client) + 4}>
            {shortLabel(op)}
          </text>
        </g>
      ))}

      <line className="playhead" x1={x(now)} y1={TOP - 12} x2={x(now)} y2={height - 16} />
      <text className="playhead-label" x={x(now) + 6} y={TOP - 16}>
        {now} ms
      </text>
    </svg>
  );
}

function midpoint(a: number, b: number): number {
  return (a + b) / 2;
}

function returnedAt(op: Operation, span: number): number {
  return op.returned === -1 ? span : op.returned;
}

function shortLabel(op: Operation): string {
  if (op.kind === "write") return `w ${op.key}=${op.argument}`;
  if (op.kind === "read") return `r ${op.key}${op.outcome === "ok" ? `→${op.result}` : ""}`;
  return `cas ${op.key}`;
}

function describe(op: Operation, label: string): string {
  const window = `${op.invoked}–${op.returned === -1 ? "…" : op.returned} ms`;
  if (op.outcome === "unknown") {
    return `client ${label} ${op.kind} ${op.key} — no answer (${window})`;
  }
  if (op.kind === "read") return `client ${label} reads ${op.key} → ${op.result} (${window})`;
  if (op.kind === "write") return `client ${label} writes ${op.key}=${op.argument} (${window})`;
  return `client ${label} cas ${op.key} ${op.expected}→${op.argument} (${window})`;
}

interface Band {
  from: number;
  to: number;
}

function partitionBands(trace: Trace, span: number): Band[] {
  const bands: Band[] = [];
  let open: number | null = null;
  for (const event of trace.events) {
    if (event.type === "partition_start" && open === null) open = event.t;
    if (event.type === "partition_end" && open !== null) {
      bands.push({ from: open, to: event.t });
      open = null;
    }
  }
  if (open !== null) bands.push({ from: open, to: span });
  return bands;
}

interface Outage extends Band {
  node: number;
  kind: "down" | "paused";
}

function nodeOutages(trace: Trace, span: number): Outage[] {
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
