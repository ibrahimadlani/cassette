/**
 * The three panels under the diagram.
 *
 * `WhatIsHappening` is the one that makes the demo work for somebody who has
 * never read a space-time diagram: it says in words what the playhead is
 * sitting on, keeps the last few events fading out behind it, and raises an
 * alert the moment the cluster has already lost.
 *
 * `NodePanel` earns its place for the opposite reason — it is where the bug
 * becomes visible first. Two replicas holding different values under the same
 * version stamp is the defect itself, several seconds before a client sees it.
 */

import type { Frame } from "../model";
import { disagreeUnderTheSameStamp, stamp } from "../model";
import type { Narrator } from "../narrate";
import type { Operation, Trace } from "../trace";
import { clientLabels, replicaIds } from "../trace";

const TRAIL = 3;

interface HappeningProps {
  trace: Trace;
  frame: Frame;
  narrator: Narrator;
  idle: string;
  alert: string | null;
}

export function WhatIsHappening({ trace, frame, narrator, idle, alert }: HappeningProps) {
  const index = frame.index;
  const trail: { t: number; text: string; opacity: number }[] = [];
  for (let i = Math.max(0, index - TRAIL); i < index; i++) {
    const event = trace.events[i];
    if (!event) continue;
    trail.push({
      t: event.t,
      text: narrator.at(i),
      opacity: 0.35 + 0.2 * (i - Math.max(0, index - TRAIL)),
    });
  }

  return (
    <section className="card">
      <div className="panel-head">
        <span className="eyebrow">What is happening</span>
        <span className="now">{frame.t} ms</span>
      </div>
      <div className="panel-body">
        <p className="narration">{index < 0 ? idle : narrator.at(index)}</p>
        {alert && <p className="alert">{alert}</p>}
        {trail.length > 0 && (
          <div className="recent">
            {trail.map((line, position) => (
              <div key={position} style={{ opacity: line.opacity }}>
                <span className="t">{line.t} ms</span>
                <span className="text">{line.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

interface NodeProps {
  trace: Trace;
  frame: Frame;
}

export function NodePanel({ trace, frame }: NodeProps) {
  const replicas = replicaIds(trace);
  const values = replicas.map((id) => frame.nodes.get(id)?.value ?? null);
  const stamps = replicas.map((id) => stamp(frame.nodes.get(id)?.version));
  const divergent = disagreeUnderTheSameStamp(values, stamps);

  return (
    <section className="card">
      <div className="panel-head">
        <span className="eyebrow">Replicas now</span>
      </div>
      <div className="panel-body panel-body--table">
        <table>
          <thead>
            <tr>
              <th>node</th>
              <th>status</th>
              <th className="num">value</th>
              <th className="num">version</th>
              <th className="num">grp</th>
            </tr>
          </thead>
          <tbody>
            {replicas.map((id, index) => {
              const state = frame.nodes.get(id);
              if (!state) return null;
              return (
                <tr key={id} className={divergent ? "divergent" : undefined}>
                  <td>n{id}</td>
                  <td className={`status--${state.status}`}>{state.status}</td>
                  <td className="num">{values[index] === null ? "—" : values[index]}</td>
                  <td className="num subtle">{stamps[index]}</td>
                  <td className="num subtle">
                    {state.group === null ? "—" : String.fromCharCode(65 + state.group)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {divergent && (
          <p className="note">
            Two replicas hold different values under the same version stamp. Nothing in the
            cluster can tell which one is right.
          </p>
        )}
      </div>
    </section>
  );
}

interface HistoryProps {
  trace: Trace;
  time: number;
}

export function HistoryPanel({ trace, time }: HistoryProps) {
  const labels = clientLabels(trace);
  const violating = trace.verdict?.operation ?? null;

  return (
    <section className="card">
      <div className="panel-head">
        <span className="eyebrow">Client history</span>
      </div>
      <div className="panel-body panel-body--table scroller">
        <table>
          <thead>
            <tr>
              <th>t</th>
              <th>client</th>
              <th>operation</th>
              <th className="num">result</th>
            </tr>
          </thead>
          <tbody>
            {trace.history.map((op) => (
              <tr key={op.index} className={rowClass(op, time, violating)}>
                <td className="subtle">{op.invoked} ms</td>
                <td>{labels.get(op.client) ?? op.client}</td>
                <td>{operationText(op)}</td>
                <td className="num">{resultText(op, time)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/**
 * The sentence shown when the run has already gone wrong.
 *
 * Two cases, and the order matters: once the violating read has returned, say
 * what it read. Before that, if the replicas have already diverged, say that
 * the outcome is settled — the interesting moment is the one where nothing has
 * visibly broken yet and the cluster is already doomed.
 */
export function alertFor(trace: Trace, frame: Frame, divergent: boolean): string | null {
  const violating = trace.verdict?.operation ?? null;
  const labels = clientLabels(trace);

  if (violating !== null) {
    const op = trace.history.find((candidate) => candidate.index === violating);
    if (op && op.invoked <= frame.t) {
      const who = labels.get(op.client) ?? op.client;
      return (
        `Client ${who} read ${op.key} → ${op.result}. No ordering of these operations ` +
        `puts that read after a write of ${op.result} and still explains what the other ` +
        "client saw."
      );
    }
    if (divergent) {
      return "Two replicas already disagree under the same version stamp. The violation is now unavoidable.";
    }
    return null;
  }

  return divergent ? "Replicas disagree under the same version stamp." : null;
}

/** Whether the cluster has diverged at this instant. */
export function divergentAt(trace: Trace, frame: Frame): boolean {
  const replicas = replicaIds(trace);
  return disagreeUnderTheSameStamp(
    replicas.map((id) => frame.nodes.get(id)?.value ?? null),
    replicas.map((id) => stamp(frame.nodes.get(id)?.version)),
  );
}

function rowClass(op: Operation, time: number, violating: number | null): string {
  if (op.invoked > time) return "row--future";
  if (op.index === violating) return "row--violating";
  if (op.returned === -1 || op.returned > time) return "row--pending";
  return "";
}

function operationText(op: Operation): string {
  if (op.kind === "write") return `write ${op.key} = ${op.argument}`;
  if (op.kind === "read") return `read ${op.key}`;
  return `cas ${op.key} ${op.expected} → ${op.argument}`;
}

function resultText(op: Operation, time: number): string {
  if (op.invoked > time) return "";
  if (op.returned === -1 || op.returned > time) return "…";
  if (op.outcome === "unknown") return "no answer";
  if (op.kind === "read") return op.result === null ? "—" : String(op.result);
  if (op.kind === "cas") return op.result ? "swapped" : "refused";
  return "ok";
}
