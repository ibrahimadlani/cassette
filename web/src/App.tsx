/**
 * The replayer.
 *
 * Loads a pre-generated trace, folds it into frames once, and steps through
 * them. There is no simulator in here — see ADR-0005 — which is why the whole
 * thing is a static site with no server behind it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Controls } from "./components/Controls";
import {
  HistoryPanel,
  NodePanel,
  WhatIsHappening,
  alertFor,
  divergentAt,
} from "./components/Panels";
import { SpaceTime } from "./components/SpaceTime";
import { buildFlights, buildFrames, frameAt } from "./model";
import { humanise, idleNarration, makeNarrator } from "./narrate";
import type { Theme } from "./theme";
import { applyTheme, currentTheme, otherTheme } from "./theme";
import type { CatalogueEntry, Trace } from "./trace";
import { duration, parseTrace } from "./trace";

const REPO = "https://github.com/ibrahimadlani/cassette";
const FRAME_MS = 40;

function traceUrl(slug: string): string {
  return `${import.meta.env.BASE_URL}traces/${slug}.json`;
}

/**
 * The exhibit asked for in the URL, falling back to the first in the catalogue.
 *
 * `?trace=<slug>` is the canonical form. `?seed=<n>` also works, because that
 * is what somebody who has just read the README will try.
 */
export function requestedSlug(catalogue: CatalogueEntry[], search: string): string {
  const params = new URLSearchParams(search);

  const slug = params.get("trace");
  if (slug && catalogue.some((entry) => entry.slug === slug)) return slug;

  const seed = params.get("seed");
  if (seed !== null) {
    const bySeed = catalogue.find((entry) => String(entry.seed) === seed);
    if (bySeed) return bySeed.slug;
  }

  return catalogue[0]?.slug ?? "";
}

export function App() {
  const [catalogue, setCatalogue] = useState<CatalogueEntry[] | null>(null);
  const [slug, setSlug] = useState<string>("");
  const [trace, setTrace] = useState<Trace | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(currentTheme);

  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}traces/index.json`)
      .then((response) => response.json() as Promise<CatalogueEntry[]>)
      .then((entries) => {
        setCatalogue(entries);
        setSlug(requestedSlug(entries, window.location.search));
      })
      .catch((reason: unknown) => setFailure(`could not load the catalogue: ${String(reason)}`));
  }, []);

  useEffect(() => {
    if (!slug) return;
    setTrace(null);
    setFailure(null);
    setFrame(0);
    setPlaying(false);

    fetch(traceUrl(slug))
      .then((response) => response.json())
      .then((payload) => setTrace(parseTrace(payload)))
      .catch((reason: unknown) => setFailure(String(reason)));

    const url = new URL(window.location.href);
    url.searchParams.set("trace", slug);
    window.history.replaceState(null, "", url);
  }, [slug]);

  const toggleTheme = useCallback(() => {
    setTheme((was) => applyTheme(otherTheme(was)));
  }, []);

  const frames = useMemo(() => (trace ? buildFrames(trace) : []), [trace]);
  const flights = useMemo(() => (trace ? buildFlights(trace) : []), [trace]);
  const narrator = useMemo(() => (trace ? makeNarrator(trace) : null), [trace]);
  const span = trace ? duration(trace) : 1;

  // Simulated milliseconds per real second, so 1x replays the run at the speed
  // the cluster would have lived it.
  const carry = useRef<number>(0);
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const handle = window.setInterval(() => {
      setFrame((current) => {
        if (current >= frames.length - 1) {
          setPlaying(false);
          return current;
        }
        carry.current += FRAME_MS * speed;
        const target = (frames[current]?.t ?? 0) + carry.current;
        const next = Math.max(current + 1, frameAt(frames, target));
        carry.current = 0;
        return Math.min(next, frames.length - 1);
      });
    }, FRAME_MS);
    return () => window.clearInterval(handle);
  }, [playing, speed, frames]);

  const step = useCallback(
    (delta: number) => {
      setPlaying(false);
      setFrame((current) => Math.max(0, Math.min(frames.length - 1, current + delta)));
    },
    [frames.length],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === " ") {
        event.preventDefault();
        setPlaying((was) => !was);
      } else if (event.key === "ArrowLeft") step(-1);
      else if (event.key === "ArrowRight") step(1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  const entry = catalogue?.find((candidate) => candidate.slug === slug);
  const current = frames[frame];

  return (
    <>
      <header className="masthead">
        <div className="wordmark">
          <b>Cassette</b>
          <span>trace replayer</span>
        </div>
        <span className="tagline">
          Deterministic simulation testing for distributed systems. Every bug reproduces,
          every time.
        </span>
        <nav>
          <button className="pill" onClick={toggleTheme} aria-label="Toggle colour theme">
            {otherTheme(theme)}
          </button>
          <a className="pill pill--link" href={REPO}>
            source ↗
          </a>
        </nav>
      </header>

      <div className="app">
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">Recorded run</span>
            <h1>{entry?.title ?? "Loading the catalogue"}</h1>
            <p>
              {entry?.blurb ??
                "One seed describes a run completely, so the same interleaving replays exactly."}
            </p>
          </div>
          {trace && (
            <div className="stats">
              <div>
                <span className="eyebrow">seed</span>
                <b>{trace.seed}</b>
              </div>
              <div>
                <span className="eyebrow">replicas</span>
                <b>{trace.scenario.store.replicas}</b>
              </div>
              <div>
                <span className="eyebrow">quorums</span>
                <b>
                  R={trace.scenario.store.read_quorum} W={trace.scenario.store.write_quorum}
                </b>
              </div>
              <div>
                <span className="eyebrow">events</span>
                <b>{trace.events.length}</b>
              </div>
            </div>
          )}
        </section>

        <section className="catalogue">
          <span className="eyebrow">Runs in the catalogue</span>
          <nav className="chips" aria-label="Recorded runs">
            {(catalogue ?? []).map((option) => (
              <button
                key={option.slug}
                className="chip"
                aria-pressed={option.slug === slug}
                onClick={() => setSlug(option.slug)}
              >
                <span className={option.linearizable ? "dot" : "dot dot--bad"} />
                {option.title}
              </button>
            ))}
          </nav>
        </section>

        {failure && <p className="failure">{failure}</p>}
        {!trace && !failure && <p className="loading">loading trace…</p>}

        {trace && current && narrator && (
          <>
            <Verdict trace={trace} />

            <div className="card">
              <div className="card-head">
                <span className="eyebrow">Space–time</span>
                <Legend />
              </div>

              <SpaceTime
                trace={trace}
                frames={frames}
                flights={flights}
                frame={frame}
                onScrub={(time) => {
                  setPlaying(false);
                  setFrame(frameAt(frames, time));
                }}
              />

              <Controls
                frame={frame}
                frames={frames.length}
                time={current.t}
                span={span}
                playing={playing}
                speed={speed}
                onPlayPause={() =>
                  setPlaying((was) => {
                    if (!was && frame >= frames.length - 1) setFrame(0);
                    return !was;
                  })
                }
                onStep={step}
                onSeek={(next) => {
                  setPlaying(false);
                  setFrame(next);
                }}
                onSpeed={setSpeed}
              />
            </div>

            <div className="panels">
              <WhatIsHappening
                trace={trace}
                frame={current}
                narrator={narrator}
                idle={idleNarration()}
                alert={alertFor(trace, current, divergentAt(trace, current))}
              />
              <NodePanel trace={trace} frame={current} />
              <HistoryPanel trace={trace} time={current.t} />
            </div>

            <p className="footnote">
              Space plays and pauses; the arrow keys step one event at a time. Reproduce this
              run with <code>cassette run --seed {trace.seed}</code>
            </p>
          </>
        )}
      </div>
    </>
  );
}

function Legend() {
  return (
    <div className="legend">
      <span>
        <i className="swatch swatch--write" /> write msg
      </span>
      <span>
        <i className="swatch swatch--read" /> read msg
      </span>
      <span>
        <i className="swatch swatch--dropped" /> dropped
      </span>
      <span>
        <i className="swatch swatch--partition" /> partition
      </span>
      <span>
        <i className="swatch swatch--down" /> node down
      </span>
      <span>
        <i className="swatch swatch--violation" /> violation
      </span>
    </div>
  );
}

function Verdict({ trace }: { trace: Trace }) {
  const verdict = trace.verdict;
  const linearizable = verdict === null || verdict.linearizable;

  return (
    <section className={`verdict verdict--${linearizable ? "ok" : "bad"}`}>
      <div className="verdict-main">
        <h2>{linearizable ? "Linearizable" : "Not linearizable"}</h2>
        <p>
          {linearizable
            ? "Every client observation can be explained by some ordering of the operations."
            : verdict?.explanation
              ? humanise(trace, verdict.explanation)
              : "No legal ordering of these operations explains what the clients saw."}
        </p>
      </div>
      <div className="verdict-checker">
        <span className="eyebrow">checker</span>
        <span>
          {verdict
            ? `${verdict.checked_operations} operations checked${
                verdict.exhausted ? " · search exhausted" : ""
              }`
            : "not checked"}
        </span>
      </div>
    </section>
  );
}
