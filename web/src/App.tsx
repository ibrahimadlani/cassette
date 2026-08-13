/**
 * The replayer.
 *
 * Loads a pre-generated trace, folds it into frames once, and steps through
 * them. There is no simulator in here — see ADR-0005 — which is why the whole
 * thing is a static site with no server behind it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Controls } from "./components/Controls";
import { HistoryPanel, NodePanel } from "./components/Panels";
import { SpaceTime } from "./components/SpaceTime";
import { buildFlights, buildFrames, frameAt } from "./model";
import type { CatalogueEntry, Trace } from "./trace";
import { duration, parseTrace } from "./trace";

const REPO = "https://github.com/ibrahimadlani/cassette";
const FRAME_MS = 40;

function traceUrl(slug: string): string {
  return `${import.meta.env.BASE_URL}traces/${slug}.json`;
}

/** The exhibit named in `?trace=`, falling back to the first in the catalogue. */
function requestedSlug(catalogue: CatalogueEntry[]): string {
  const wanted = new URLSearchParams(window.location.search).get("trace");
  if (wanted && catalogue.some((entry) => entry.slug === wanted)) return wanted;
  return catalogue[0]?.slug ?? "";
}

export function App() {
  const [catalogue, setCatalogue] = useState<CatalogueEntry[] | null>(null);
  const [slug, setSlug] = useState<string>("");
  const [trace, setTrace] = useState<Trace | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}traces/index.json`)
      .then((response) => response.json() as Promise<CatalogueEntry[]>)
      .then((entries) => {
        setCatalogue(entries);
        setSlug(requestedSlug(entries));
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

  const frames = useMemo(() => (trace ? buildFrames(trace) : []), [trace]);
  const flights = useMemo(() => (trace ? buildFlights(trace) : []), [trace]);
  const span = trace ? duration(trace) : 1;

  // Simulated milliseconds per real second, so 1x replays the run at the speed
  // the cluster would have lived it.
  const tick = useRef<number>(0);
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const handle = window.setInterval(() => {
      setFrame((current) => {
        if (current >= frames.length - 1) {
          setPlaying(false);
          return current;
        }
        tick.current += (FRAME_MS * speed) / 1000;
        const target = (frames[current]?.t ?? 0) + tick.current * 1000;
        const next = Math.max(current + 1, frameAt(frames, target));
        tick.current = 0;
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
    <div className="app">
      <header className="masthead">
        <h1>Cassette</h1>
        <span className="tagline">
          A recorded simulation of a replicated key-value store. Every message, every
          partition, every crash — and the operation that could not have happened.
        </span>
        <a href={REPO}>source ↗</a>
      </header>

      <nav className="catalogue" aria-label="Recorded runs">
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

      {failure && <p className="failure">{failure}</p>}
      {!trace && !failure && <p className="loading">loading…</p>}

      {trace && current && (
        <>
          <Verdict trace={trace} blurb={entry?.blurb} />

          <div className="stage">
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
          </div>

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

          <div className="panels">
            <NodePanel trace={trace} frame={current} />
            <HistoryPanel trace={trace} time={current.t} />
          </div>

          <p className="footnote">
            Seed {trace.seed} · {trace.scenario.store.replicas} replicas · R=
            {trace.scenario.store.read_quorum} W={trace.scenario.store.write_quorum} ·{" "}
            {trace.events.length} events. Space plays and pauses; the arrow keys step.
            Reproduce this run with <code>cassette run --seed {trace.seed}</code>.
          </p>
        </>
      )}
    </div>
  );
}

function Verdict({ trace, blurb }: { trace: Trace; blurb?: string | undefined }) {
  const verdict = trace.verdict;
  const linearizable = verdict === null || verdict.linearizable;

  return (
    <section className={`verdict verdict--${linearizable ? "ok" : "bad"}`}>
      <h2>{linearizable ? "Linearizable" : "Not linearizable"}</h2>
      <p>
        {linearizable
          ? blurb ?? "Every client observation can be explained by some ordering of the operations."
          : verdict?.explanation ?? "No legal ordering exists."}
      </p>
      {!linearizable && blurb && <p style={{ marginTop: 6 }}>{blurb}</p>}
    </section>
  );
}
