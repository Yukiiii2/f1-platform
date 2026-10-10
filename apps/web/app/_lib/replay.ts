import type { ReplayDriver, SessionReplay } from "./replay-contracts";

// Binary lookup: never use a future sample or interpolate numerical race ranks.
function preceding<T extends { elapsed_seconds: number }>(
  samples: T[],
  time: number,
): T | null {
  let low = 0,
    high = samples.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (samples[middle].elapsed_seconds <= time) low = middle + 1;
    else high = middle;
  }
  return samples[low - 1] ?? null;
}
export function driverAt(driver: ReplayDriver, time: number, maxHold: number) {
  const sample = preceding(driver.positions, time);
  const age = sample ? time - sample.elapsed_seconds : Infinity;
  const valid = age <= maxHold;
  const interval = preceding(driver.intervals, time);
  const gap =
    interval && time - interval.elapsed_seconds <= maxHold ? interval : null;
  const lap =
    driver.laps.find(
      (row) =>
        row.end_seconds !== null &&
        row.start_seconds <= time &&
        time < row.end_seconds,
    ) ?? null;
  // Duration supplied by source; outside a known pit window the state is unknown.
  const inPit = driver.pits.some(
    (row) =>
      row.lane_duration_seconds !== null &&
      row.elapsed_seconds <= time &&
      time < row.elapsed_seconds + Number(row.lane_duration_seconds),
  )
    ? true
    : null;
  return {
    position: valid ? sample!.position : null,
    quality: !valid
      ? ("unavailable" as const)
      : age === 0
        ? ("source" as const)
        : ("held" as const),
    sample: valid ? sample : null,
    age: valid ? age : null,
    gap,
    lap,
    inPit,
  };
}
export interface Playback {
  elapsed: number;
  playing: boolean;
  speed: number;
  visible: string[];
  focus: string | null;
}
export type PlaybackAction =
  | { type: "play" | "pause" | "restart" }
  | { type: "tick"; seconds: number }
  | { type: "scrub"; elapsed: number }
  | { type: "speed"; speed: number }
  | { type: "toggle"; id: string }
  | { type: "focus"; id: string | null };
export function initialPlayback(replay: SessionReplay): Playback {
  return {
    elapsed: 0,
    playing: false,
    speed: 1,
    visible: replay.drivers.map((row) => row.driver.id),
    focus: null,
  };
}
export function reducePlayback(
  state: Playback,
  action: PlaybackAction,
  duration: number,
): Playback {
  switch (action.type) {
    case "play":
      return {
        ...state,
        elapsed: state.elapsed >= duration ? 0 : state.elapsed,
        playing: duration > 0,
      };
    case "pause":
      return { ...state, playing: false };
    case "restart":
      return { ...state, elapsed: 0, playing: false };
    case "scrub":
      return {
        ...state,
        elapsed: Math.max(0, Math.min(duration, action.elapsed)),
        playing: false,
      };
    case "speed":
      return [0.5, 1, 2, 4].includes(action.speed)
        ? { ...state, speed: action.speed }
        : state;
    case "tick": {
      if (!state.playing) return state;
      const elapsed = Math.min(
        duration,
        state.elapsed + Math.max(0, action.seconds) * state.speed,
      );
      return { ...state, elapsed, playing: elapsed < duration };
    }
    case "toggle": {
      const visible = state.visible.includes(action.id)
        ? state.visible.filter((id) => id !== action.id)
        : [...state.visible, action.id];
      return {
        ...state,
        visible,
        focus: visible.includes(state.focus ?? "") ? state.focus : null,
      };
    }
    case "focus":
      return {
        ...state,
        focus: action.id,
        visible:
          action.id && !state.visible.includes(action.id)
            ? [...state.visible, action.id]
            : state.visible,
      };
  }
}
export function replayHref(
  event: string,
  year: number | undefined,
  session: string,
) {
  return `/races/${event}/replay?${new URLSearchParams({ ...(year !== undefined ? { season: String(year) } : {}), session })}`;
}
export function replayTime(seconds: number) {
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
}
