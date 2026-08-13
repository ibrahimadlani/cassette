/**
 * T-8: the replayer renders a real trace.
 *
 * The trace is the one the build script exports, read off disk rather than
 * hand-written, so this fails if the Python side changes the format without
 * the TypeScript side following. That is the whole reason to have the test:
 * the two halves of this project only meet at the schema.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { buildFrames } from "./model";
import { parseTrace } from "./trace";

const TRACES = join(__dirname, "..", "public", "traces");

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(join(TRACES, `${name}.json`), "utf-8"));
}

const catalogue = JSON.parse(readFileSync(join(TRACES, "index.json"), "utf-8"));

beforeEach(() => {
  vi.stubGlobal("fetch", (input: string) => {
    const name = input.endsWith("index.json")
      ? "index"
      : (input.split("/").pop() ?? "").replace(".json", "");
    const payload = name === "index" ? catalogue : fixture(name);
    return Promise.resolve({ json: () => Promise.resolve(payload) } as Response);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the exported traces", () => {
  it("all parse", () => {
    for (const entry of catalogue) {
      expect(parseTrace(fixture(entry.slug)).version).toBe(1);
    }
  });

  it("all fold into frames without losing an event", () => {
    for (const entry of catalogue) {
      const trace = parseTrace(fixture(entry.slug));
      expect(buildFrames(trace)).toHaveLength(trace.events.length + 1);
    }
  });

  it("include at least one violation and at least one clean run", () => {
    const verdicts = catalogue.map((entry: { linearizable: boolean }) => entry.linearizable);
    expect(verdicts).toContain(true);
    expect(verdicts).toContain(false);
  });

  it("keeps the reduced counterexample small enough to read", () => {
    const trace = parseTrace(fixture("minimal-violation"));
    expect(trace.history.length).toBeLessThanOrEqual(6);
    expect(trace.verdict?.linearizable).toBe(false);
  });
});

describe("App", () => {
  it("renders the catalogue", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("The bug, reduced")).toBeDefined());
  });

  it("shows the verdict for a failing run", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Not linearizable")).toBeDefined());
  });

  it("draws the space-time diagram", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    expect(container.querySelectorAll(".flight").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".lane").length).toBeGreaterThan(0);
  });

  it("marks exactly one operation as the violation", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    expect(container.querySelectorAll(".operation--violating")).toHaveLength(1);
  });

  it("lists every client operation in the history panel", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".panel")).not.toBeNull());
    const trace = parseTrace(fixture("minimal-violation"));
    const rows = container.querySelectorAll(".panels table tbody tr");
    expect(rows.length).toBeGreaterThanOrEqual(trace.history.length);
  });

  it("offers play, step and scrub controls", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Play")).toBeDefined());
    expect(screen.getByLabelText("Step forward")).toBeDefined();
    expect(screen.getByLabelText("Position in the run")).toBeDefined();
    expect(screen.getByLabelText("Playback speed")).toBeDefined();
  });

  it("reports a trace it cannot read instead of drawing it", async () => {
    vi.stubGlobal("fetch", (input: string) =>
      Promise.resolve({
        json: () =>
          Promise.resolve(input.endsWith("index.json") ? catalogue : { version: 99, events: [] }),
      } as Response),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/version 99 is not supported/)).toBeDefined());
  });
});
