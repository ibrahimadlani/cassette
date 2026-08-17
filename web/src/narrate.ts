/**
 * Saying, in English, what just happened.
 *
 * The diagram shows a reader *that* a line was drawn. This says what the line
 * meant. Between the two, somebody who has never seen a space-time diagram can
 * follow a partition all the way to the read it broke — which is the only
 * reason the demo is worth putting in front of anyone.
 *
 * Sends are indexed once per trace rather than scanned backwards per event:
 * the narration runs for the current event and the three behind it on every
 * frame, and a linear scan through seven hundred events at 25 fps is the kind
 * of thing that makes a page feel slow for no reason.
 */

import type { Trace, TraceEvent } from "./trace";
import { clientLabels } from "./trace";

export interface Narrator {
  /** What `trace.events[index]` did, as a sentence. */
  at(index: number): string;
}

const IDLE =
  "The cluster is idle. Nothing has been sent yet — press play and every " +
  "message, partition and crash replays in the order the seed chose.";

export function idleNarration(): string {
  return IDLE;
}

/**
 * Rewrite the checker's node ids into the labels the page uses.
 *
 * The verdict text comes from the Python checker, which speaks in node ids
 * ("client 4 reads y -> 2"). The rest of the interface calls that participant
 * client B. Two names for the same actor, side by side, reads like two
 * different systems talking — so the id is swapped for the label on the way in.
 * Anything that is not a known client is left exactly as it was.
 */
export function humanise(trace: Trace, text: string): string {
  const labels = clientLabels(trace);
  return text.replace(/\bclient (\d+)\b/g, (whole, id: string) => {
    const label = labels.get(Number(id));
    return label === undefined ? whole : `client ${label}`;
  });
}

export function makeNarrator(trace: Trace): Narrator {
  const labels = clientLabels(trace);
  const sends = new Map<number, TraceEvent>();
  for (const event of trace.events) {
    if (event.type === "msg_send" && event.id !== undefined && !sends.has(event.id)) {
      sends.set(event.id, event);
    }
  }

  const who = (id: number | undefined): string => {
    if (id === undefined) return "somebody";
    const label = labels.get(id);
    return label === undefined ? `n${id}` : `client ${label}`;
  };

  return {
    at(index: number): string {
      const event = trace.events[index];
      if (!event) return "";
      const kind = (event.kind ?? "message").replace(/_/g, " ");

      switch (event.type) {
        case "msg_send":
          return `${who(event.sender)} sends a ${kind} to ${who(event.to)}.`;

        case "msg_deliver": {
          const sent = event.id === undefined ? undefined : sends.get(event.id);
          const value = sent?.body?.["value"];
          const carrying = value === undefined || value === null ? "" : ` carrying ${value}`;
          return `A ${kind}${carrying} lands at ${who(event.to)}.`;
        }

        case "msg_drop":
          return (
            `A ${kind} to ${who(event.to)} is lost (${event.reason ?? "loss"}). ` +
            "Nobody is told."
          );

        case "partition_start":
          return (
            `The network splits into ${event.groups?.length ?? 2} groups. ` +
            "Messages across the split will not arrive."
          );

        case "partition_end":
          return "The partition heals. The two halves can talk again.";

        case "node_crash":
          return `n${event.node} crashes and loses its volatile state.`;

        case "node_restart":
          return `n${event.node} restarts. Acknowledged writes are still there.`;

        case "node_pause":
          return `n${event.node} is paused — running, but answering nothing.`;

        case "node_resume":
          return `n${event.node} resumes where it left off.`;
      }
    },
  };
}
