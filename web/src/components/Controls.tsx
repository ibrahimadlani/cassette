/** Play, pause, step, scrub, and choose how fast simulated time runs. */

interface Props {
  frame: number;
  frames: number;
  time: number;
  span: number;
  playing: boolean;
  speed: number;
  onPlayPause: () => void;
  onStep: (delta: number) => void;
  onSeek: (frame: number) => void;
  onSpeed: (speed: number) => void;
}

const SPEEDS = [0.25, 0.5, 1, 2, 4, 16];

export function Controls({
  frame,
  frames,
  time,
  span,
  playing,
  speed,
  onPlayPause,
  onStep,
  onSeek,
  onSpeed,
}: Props) {
  const atEnd = frame >= frames - 1;

  return (
    <div className="controls">
      <button className="primary" onClick={onPlayPause} aria-label={playing ? "Pause" : "Play"}>
        {playing ? "❚❚ pause" : atEnd ? "↻ replay" : "▶ play"}
      </button>

      <button onClick={() => onStep(-1)} disabled={frame <= 0} aria-label="Step back">
        ‹ step
      </button>
      <button onClick={() => onStep(1)} disabled={atEnd} aria-label="Step forward">
        step ›
      </button>

      <input
        type="range"
        min={0}
        max={Math.max(0, frames - 1)}
        value={frame}
        onChange={(event) => onSeek(Number(event.target.value))}
        aria-label="Position in the run"
      />

      <span className="readout">
        {time} / {span} ms · event {frame}/{frames - 1}
      </span>

      <select
        value={speed}
        onChange={(event) => onSpeed(Number(event.target.value))}
        aria-label="Playback speed"
      >
        {SPEEDS.map((option) => (
          <option key={option} value={option}>
            {option}×
          </option>
        ))}
      </select>
    </div>
  );
}
