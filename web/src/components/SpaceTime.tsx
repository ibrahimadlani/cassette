/**
 * The space-time diagram.
 *
 * One horizontal lane per participant, logical time running left to right,
 * every message a diagonal from the sender's lane at the instant it was sent to
 * the recipient's lane at the instant it landed. The slope is the latency; a
 * message that crosses another is a reordering; a line that stops halfway is a
 * message that never arrived.
 *
 * Shapes are SVG, scaled by a viewBox so the chart fills whatever width it is
 * given. Text is not: it lives in an absolutely-positioned HTML overlay above
 * the same box, so labels stay on the device pixel grid instead of being
 * stretched with the drawing. Percentages tie the two together.
 */

import { useMemo } from "react";

import type { Flight, Frame } from "../model";
import { nodeOutages, partitionBands, ticks } from "../model";
import type { Operation, Trace } from "../trace";
import { clientLabels, duration, replicaIds } from "../trace";

const WIDTH = 1400;
const LEFT = 104;
const RIGHT = 40;
const TOP = 34;
const FOOT = 42;

/** Where the violation label flips to the left of its marker. */
const FLIP_AT = 0.68;

interface Props {
  trace: Trace;
  frames: Frame[];
  flights: Flight[];
  frame: number;
  laneHeight?: number;
  onScrub: (time: number) => void;
}

export function SpaceTime({ trace, frames, flights, frame, laneHeight = 50, onScrub }: Props) {
  const laneH = Math.max(34, laneHeight);
  const labels = clientLabels(trace);
  const lanes = [...replicaIds(trace), ...labels.keys()];
  const height = TOP + lanes.length * laneH + FOOT;
  const span = duration(trace);
  const now = frames[frame]?.t ?? 0;
  const violating = trace.verdict?.operation ?? null;

  const x = (t: number) => LEFT + (t / span) * (WIDTH - LEFT - RIGHT);
  const y = (node: number) => TOP + lanes.indexOf(node) * laneH + laneH / 2;
  const px = (value: number) => `${(value / WIDTH) * 100}%`;
  const py = (value: number) => `${(value / height) * 100}%`;

  const bands = useMemo(() => partitionBands(trace, span), [trace, span]);
  const outages = useMemo(() => nodeOutages(trace, span), [trace, span]);
  const axis = useMemo(() => ticks(span), [span]);

  function scrub(event: React.MouseEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    const position = (ratio * WIDTH - LEFT) / (WIDTH - LEFT - RIGHT);
    onScrub(Math.max(0, Math.min(1, position)) * span);
  }

  const culprit = violating === null ? undefined : trace.history.find((op) => op.index === violating);
  const markerX = culprit ? x(culprit.invoked) : 0;
  const markerRight = markerX < WIDTH * FLIP_AT;

  return (
    <div className="stage">
      <div className="stage-inner">
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
              y={TOP - 10}
              width={Math.max(1, x(band.to) - x(band.from))}
              height={lanes.length * laneH + 10}
              fill="color-mix(in srgb, var(--warn) 12%, transparent)"
              stroke="color-mix(in srgb, var(--warn) 45%, transparent)"
              strokeDasharray="4 3"
            >
              <title>
                partition, {band.from}–{band.to} ms
              </title>
            </rect>
          ))}

          {axis.map((t) => (
            <line
              key={`tick-${t}`}
              x1={x(t)}
              y1={TOP - 10}
              x2={x(t)}
              y2={TOP + lanes.length * laneH}
              stroke="var(--grid)"
              strokeWidth={1}
            />
          ))}

          {outages.map((outage, index) => (
            <rect
              key={`outage-${index}`}
              className={`band band--${outage.kind}`}
              x={x(outage.from)}
              y={y(outage.node) - 11}
              width={Math.max(2, x(outage.to) - x(outage.from))}
              height={22}
              rx={3}
              fill={
                outage.kind === "down"
                  ? "color-mix(in srgb, var(--bad) 24%, transparent)"
                  : "color-mix(in srgb, var(--warn) 24%, transparent)"
              }
            >
              <title>
                n{outage.node} {outage.kind}, {outage.from}–{outage.to} ms
              </title>
            </rect>
          ))}

          {lanes.map((node) => (
            <line
              key={`lane-${node}`}
              className="lane"
              x1={LEFT}
              y1={y(node)}
              x2={WIDTH - RIGHT}
              y2={y(node)}
              stroke="var(--edge)"
              strokeWidth={1}
            />
          ))}

          {flights.map((flight, index) => {
            const past = flight.arrivesAt <= now;
            const lost = flight.lostAt !== null;
            const endY = lost ? (y(flight.from) + y(flight.to)) / 2 : y(flight.to);
            return (
              <line
                key={`flight-${index}`}
                className={`flight flight--${flight.kind.split("_")[0] ?? "other"} ${
                  past ? "flight--past" : "flight--future"
                } ${lost ? "flight--lost" : ""}`}
                x1={x(flight.sentAt)}
                y1={y(flight.from)}
                x2={x(flight.arrivesAt)}
                y2={endY}
                stroke={past ? strokeFor(flight.kind) : "var(--faint)"}
                strokeWidth={past ? 1.2 : 1}
                strokeDasharray={lost ? "3 2" : undefined}
                opacity={past ? (lost ? 0.6 : 0.85) : 0.18}
              >
                <title>
                  {flight.kind} n{flight.from} to n{flight.to}, {flight.sentAt}–
                  {flight.arrivesAt} ms
                  {flight.lostBecause ? ` (dropped: ${flight.lostBecause})` : ""}
                </title>
              </line>
            );
          })}

          {flights
            .filter((flight) => flight.lostAt !== null)
            .map((flight, index) => (
              <text
                key={`lost-${index}`}
                x={x(flight.arrivesAt)}
                y={(y(flight.from) + y(flight.to)) / 2 + 4}
                textAnchor="middle"
                fill="var(--bad)"
                opacity={flight.arrivesAt <= now ? 0.9 : 0.2}
                style={{ font: "12px var(--mono)" }}
              >
                ×
              </text>
            ))}

          {trace.history.map((op) => {
            const bad = op.index === violating;
            const base = colourFor(op.kind);
            return (
              <rect
                key={`op-${op.index}`}
                className={`operation operation--${op.kind} ${
                  bad ? "operation--violating" : ""
                } ${op.outcome === "unknown" ? "operation--unknown" : ""}`}
                x={x(op.invoked)}
                y={y(op.client) - 10}
                width={Math.max(4, x(returnedAt(op, span)) - x(op.invoked))}
                height={20}
                rx={4}
                fill={
                  bad
                    ? "color-mix(in srgb, var(--bad) 26%, var(--panel))"
                    : `color-mix(in srgb, ${base} 16%, var(--panel))`
                }
                stroke={bad ? "var(--bad)" : `color-mix(in srgb, ${base} 55%, transparent)`}
                strokeWidth={bad ? 2 : 1}
                strokeDasharray={op.outcome === "unknown" ? "3 2" : undefined}
              >
                <title>{describe(op, labels.get(op.client) ?? String(op.client))}</title>
              </rect>
            );
          })}

          {culprit && (
            <line
              x1={markerX}
              y1={TOP - 6}
              x2={markerX}
              y2={y(culprit.client) - 12}
              stroke="var(--bad)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          )}

          <line
            className="playhead"
            x1={x(now)}
            y1={TOP - 6}
            x2={x(now)}
            y2={height - 30}
            stroke="var(--accent)"
            strokeWidth={1.5}
          />
        </svg>

        <div className="overlay">
          {lanes.map((node) => (
            <span
              key={`lane-label-${node}`}
              className={`lane-label ${labels.has(node) ? "lane-label--client" : ""}`}
              style={{ left: px(LEFT - 14), top: py(y(node)) }}
            >
              {labels.has(node) ? `client ${labels.get(node)}` : `n${node}`}
            </span>
          ))}

          {axis.map((t) => (
            <span
              key={`tick-label-${t}`}
              className="tick-label"
              style={{ left: px(x(t)), top: py(height - 24) }}
            >
              {t}
              {t === 0 ? " ms" : ""}
            </span>
          ))}

          {trace.history.map((op) => (
            <span
              key={`op-label-${op.index}`}
              className={`op-label ${op.invoked > now ? "op-label--future" : ""}`}
              style={{ left: px(x(op.invoked) + 6), top: py(y(op.client)) }}
            >
              {shortLabel(op)}
            </span>
          ))}

          {culprit && (
            <span
              className="marker-label"
              style={{
                left: px(markerRight ? markerX + 8 : markerX - 8),
                transform: markerRight ? "translate(0,0)" : "translate(-100%,0)",
              }}
            >
              no legal order explains this read
            </span>
          )}

          <span
            className="play-badge"
            style={{
              left: px(Math.min(WIDTH - RIGHT - 30, Math.max(LEFT + 26, x(now)))),
            }}
          >
            {now} ms
          </span>
        </div>
      </div>
    </div>
  );
}

function colourFor(kind: string): string {
  if (kind === "write") return "var(--write)";
  if (kind === "read") return "var(--read)";
  return "var(--client)";
}

function strokeFor(kind: string): string {
  const head = kind.split("_")[0] ?? "";
  if (head === "write") return "var(--write)";
  if (head === "read") return "var(--read)";
  if (head === "client") return "var(--client)";
  return "var(--dim)";
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
