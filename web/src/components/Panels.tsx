/**
 * What every replica holds right now, and what the clients have seen so far.
 *
 * The replica table is the one that pays for itself: when two replicas hold
 * different values under the same version stamp, the divergence is visible in
 * the table long before it reaches a client.
 */

import type { Frame } from "../model";
import type { Operation, Trace } from "../trace";
import { clientLabels, replicaIds } from "../trace";

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
    <section className="panel">
      <h2>Replicas at {frame.t} ms</h2>
      <table>
        <thead>
          <tr>
            <th>node</th>
            <th>status</th>
            <th>value</th>
            <th>version</th>
            <th>group</th>
          </tr>
        </thead>
        <tbody>
          {replicas.map((id) => {
            const state = frame.nodes.get(id);
            if (!state) return null;
            return (
              <tr key={id} className={divergent ? "divergent" : undefined}>
                <td>n{id}</td>
                <td className={`status--${state.status}`}>{state.status}</td>
                <td>{state.value === null ? "—" : state.value}</td>
                <td>{stamp(state.version)}</td>
                <td>{state.group === null ? "—" : String.fromCharCode(65 + state.group)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {divergent && (
        <p className="footnote">
          Two replicas hold different values under the same version stamp. Nothing in the
          cluster can tell which one is right.
        </p>
      )}
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
    <section className="panel">
      <h2>Client history</h2>
      <table>
        <thead>
          <tr>
            <th>t</th>
            <th>client</th>
            <th>operation</th>
            <th>result</th>
          </tr>
        </thead>
        <tbody>
          {trace.history.map((op) => (
            <tr key={op.index} className={rowClass(op, time, violating)}>
              <td>{op.invoked}</td>
              <td>{labels.get(op.client) ?? op.client}</td>
              <td>{operationText(op)}</td>
              <td>{resultText(op, time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function rowClass(op: Operation, time: number, violating: number | null): string {
  if (op.invoked > time) return "op-row--future";
  if (op.index === violating) return "op-row--violating";
  if (op.returned === -1 || op.returned > time) return "op-row--pending";
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

function stamp(version: [number, number] | undefined): string {
  if (!version) return "—";
  const [counter, node] = version;
  return counter === 0 ? "—" : `${counter}.${node}`;
}

function disagreeUnderTheSameStamp(values: (number | null)[], stamps: string[]): boolean {
  const byStamp = new Map<string, Set<number | null>>();
  stamps.forEach((key, index) => {
    if (key === "—") return;
    const seen = byStamp.get(key) ?? new Set<number | null>();
    seen.add(values[index] ?? null);
    byStamp.set(key, seen);
  });
  return Array.from(byStamp.values()).some((seen) => seen.size > 1);
}
