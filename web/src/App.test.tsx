/**
 * T-8: the replayer renders a real trace.
 *
 * The trace is the one the build script exports, read off disk rather than
 * hand-written, so this fails if the Python side changes the format without
 * the TypeScript side following. That is the whole reason to have the test:
 * the two halves of this project only meet at the schema.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App, requestedSlug } from "./App";
import { buildFrames } from "./model";
import { humanise } from "./narrate";
import { applyTheme, currentTheme, otherTheme, storedTheme } from "./theme";
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

describe("requestedSlug", () => {
  it("defaults to the first exhibit", () => {
    expect(requestedSlug(catalogue, "")).toBe(catalogue[0].slug);
  });

  it("honours ?trace=", () => {
    expect(requestedSlug(catalogue, "?trace=partition")).toBe("partition");
  });

  it("honours ?seed= as well, because that is what the README says", () => {
    const entry = catalogue[0];
    expect(requestedSlug(catalogue, `?seed=${entry.seed}`)).toBe(entry.slug);
  });

  it("ignores a slug that is not in the catalogue", () => {
    expect(requestedSlug(catalogue, "?trace=nonsense")).toBe(catalogue[0].slug);
  });

  it("ignores a seed that is not in the catalogue", () => {
    expect(requestedSlug(catalogue, "?seed=999999")).toBe(catalogue[0].slug);
  });
});

describe("App", () => {
  it("renders the catalogue as chips", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelectorAll(".chip").length).toBeGreaterThan(0));
    const titles = Array.from(container.querySelectorAll(".chip")).map((c) => c.textContent);
    for (const entry of catalogue) {
      expect(titles.some((title) => title?.includes(entry.title))).toBe(true);
    }
  });

  it("marks the open run as the pressed chip", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".chip")).not.toBeNull());
    expect(container.querySelectorAll('.chip[aria-pressed="true"]')).toHaveLength(1);
  });

  it("leads with the run title and its blurb", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector("h1")).not.toBeNull());
    expect(container.querySelector("h1")?.textContent).toBe(catalogue[0].title);
    expect(container.querySelector(".hero p")?.textContent).toBe(catalogue[0].blurb);
  });

  it("shows the run's headline numbers", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".stats")).not.toBeNull());
    const trace = parseTrace(fixture("minimal-violation"));
    const values = Array.from(container.querySelectorAll(".stats b")).map((b) => b.textContent);
    expect(values).toContain(String(trace.seed));
    expect(values).toContain(String(trace.scenario.store.replicas));
    expect(values).toContain(String(trace.events.length));
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
    await waitFor(() => expect(container.querySelector(".panels")).not.toBeNull());
    const trace = parseTrace(fixture("minimal-violation"));
    const rows = container.querySelectorAll(".panels table tbody tr");
    expect(rows.length).toBeGreaterThanOrEqual(trace.history.length);
  });

  it("draws a labelled time axis", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    const labels = Array.from(container.querySelectorAll(".tick-label")).map((t) => t.textContent);
    expect(labels.length).toBeGreaterThan(2);
    expect(labels[0]).toBe("0 ms");
  });

  it("names the lanes for replicas and clients", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    const labels = Array.from(container.querySelectorAll(".lane-label")).map((l) => l.textContent);
    expect(labels).toContain("n0");
    expect(labels.some((label) => label?.startsWith("client "))).toBe(true);
  });

  it("points at the violating operation", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    expect(container.querySelector(".marker-label")?.textContent).toContain("no legal order");
  });

  it("says in words what the playhead is sitting on", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".narration")).not.toBeNull());
    expect(container.querySelector(".narration")?.textContent).toContain("idle");
  });

  it("narrates the event once it has stepped onto one", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".narration")).not.toBeNull());
    fireEvent.click(screen.getByLabelText("Step forward"));
    const text = container.querySelector(".narration")?.textContent ?? "";
    expect(text).not.toContain("idle");
    expect(text.length).toBeGreaterThan(10);
  });

  it("keeps a fading trail of the events just before", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".narration")).not.toBeNull());
    for (let i = 0; i < 5; i++) fireEvent.click(screen.getByLabelText("Step forward"));
    expect(container.querySelectorAll(".recent div").length).toBeGreaterThan(0);
  });

  it("raises an alert once the violating read has returned", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".spacetime")).not.toBeNull());
    fireEvent.change(screen.getByLabelText("Position in the run"), {
      target: { value: "10000" },
    });
    expect(container.querySelector(".alert")?.textContent).toContain("No ordering");
  });

  it("names clients the same way the checker does not", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".verdict")).not.toBeNull());
    const text = container.querySelector(".verdict p")?.textContent ?? "";
    expect(text).toMatch(/client [A-Z]\b/);
    expect(text).not.toMatch(/client \d/);
  });

  it("reports how much the checker looked at", async () => {
    const { container } = render(<App />);
    await waitFor(() => expect(container.querySelector(".verdict")).not.toBeNull());
    expect(container.querySelector(".verdict-checker")?.textContent).toContain(
      "operations checked",
    );
  });

  it("toggles the colour theme", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Toggle colour theme")).toBeDefined());
    const before = currentTheme();
    fireEvent.click(screen.getByLabelText("Toggle colour theme"));
    expect(currentTheme()).toBe(otherTheme(before));
    expect(screen.getByLabelText("Toggle colour theme").textContent).toBe(before);
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

describe("theme", () => {
  it("reads back what was applied", () => {
    applyTheme("dark");
    expect(currentTheme()).toBe("dark");
    applyTheme("light");
    expect(currentTheme()).toBe("light");
  });

  it("remembers the choice when storage allows it", () => {
    // jsdom does not always expose localStorage, and the point here is the
    // round trip rather than the browser, so install one that works.
    const store = new Map<string, string>();
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => void store.set(key, value),
      },
    });

    applyTheme("dark");
    expect(storedTheme()).toBe("dark");
    applyTheme("light");
    expect(storedTheme()).toBe("light");

    if (original) Object.defineProperty(window, "localStorage", original);
    else Reflect.deleteProperty(window, "localStorage");
  });

  it("ignores a stored value that is not a theme", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: () => "chartreuse", setItem: () => undefined },
    });

    expect(storedTheme()).toBeNull();

    if (original) Object.defineProperty(window, "localStorage", original);
    else Reflect.deleteProperty(window, "localStorage");
  });

  it("survives storage that throws", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("denied");
      },
    });
    expect(() => applyTheme("dark")).not.toThrow();
    expect(currentTheme()).toBe("dark");
    expect(storedTheme()).toBeNull();
    if (original) Object.defineProperty(window, "localStorage", original);
  });

  it("flips", () => {
    expect(otherTheme("dark")).toBe("light");
    expect(otherTheme("light")).toBe("dark");
  });
});

describe("humanise", () => {
  const trace = parseTrace(fixture("minimal-violation"));

  it("swaps a client node id for its label", () => {
    const first = trace.history[0]!.client;
    expect(humanise(trace, `client ${first} reads y -> 2`)).toBe("client A reads y -> 2");
  });

  it("leaves replica ids alone", () => {
    expect(humanise(trace, "n2 coordinated both writes")).toBe("n2 coordinated both writes");
  });

  it("leaves an unknown client alone", () => {
    expect(humanise(trace, "client 99 did something")).toBe("client 99 did something");
  });

  it("rewrites every mention", () => {
    const [a, b] = [trace.history[0]!.client, trace.history[1]!.client];
    expect(humanise(trace, `client ${a} and client ${b}`)).toBe("client A and client B");
  });
});
