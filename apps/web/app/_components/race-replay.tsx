"use client";

import { useEffect, useMemo, useReducer } from "react";
import type { SessionReplay } from "../_lib/replay-contracts";
import {
  driverAt,
  initialPlayback,
  reducePlayback,
  replayTime,
  type Playback,
  type PlaybackAction,
} from "../_lib/replay";

const colors = [
  "#ff967f",
  "#82c9dc",
  "#dbc67b",
  "#b5a2dd",
  "#99c5a6",
  "#d6a9bb",
];
export function RaceReplay({ replay }: { replay: SessionReplay }) {
  const [state, dispatch] = useReducer(
    (state: Playback, action: PlaybackAction) =>
      reducePlayback(state, action, replay.duration_seconds),
    replay,
    initialPlayback,
  );
  useEffect(() => {
    if (!state.playing) return;
    // Local clock only. No network request per frame; do not skip hidden-tab gaps.
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      if (!document.hidden)
        dispatch({
          type: "tick",
          seconds: Math.min((now - previous) / 1000, 0.5),
        });
      previous = now;
    }, 100);
    return () => window.clearInterval(timer);
  }, [state.playing]);
  const rows = replay.drivers
    .map((entry, index) => ({
      entry,
      color: colors[index % colors.length],
      ...driverAt(entry, state.elapsed, replay.quality.max_hold_seconds),
    }))
    .filter((row) => state.visible.includes(row.entry.driver.id))
    .sort(
      (a, b) =>
        (a.position ?? Infinity) - (b.position ?? Infinity) ||
        a.entry.driver.family_name.localeCompare(b.entry.driver.family_name),
    );
  const maxRank = useMemo(
    () =>
      Math.max(
        2,
        ...replay.drivers.flatMap((row) =>
          row.positions.map((point) => point.position),
        ),
      ),
    [replay],
  );
  const events = replay.race_control
    .filter((row) => row.elapsed_seconds <= state.elapsed)
    .slice(-5);
  return (
    <section className="race-replay" aria-label="Recorded order replay">
      <div className="replay-controls">
        <button
          className="button"
          type="button"
          onClick={() => dispatch({ type: state.playing ? "pause" : "play" })}
        >
          {state.playing ? "Pause" : "Play"}
        </button>
        <button
          className="button button-quiet"
          type="button"
          onClick={() => dispatch({ type: "restart" })}
        >
          Restart
        </button>
        <label>
          Playback speed
          <select
            value={state.speed}
            onChange={(event) =>
              dispatch({ type: "speed", speed: Number(event.target.value) })
            }
          >
            {[0.5, 1, 2, 4].map((speed) => (
              <option key={speed} value={speed}>
                {speed}x
              </option>
            ))}
          </select>
        </label>
        <output aria-label="Elapsed replay time">
          {replayTime(state.elapsed)} / {replayTime(replay.duration_seconds)}
        </output>
      </div>
      <label className="replay-timeline">
        Replay time
        <input
          type="range"
          min={0}
          max={replay.duration_seconds}
          step={0.1}
          value={state.elapsed}
          aria-valuetext={`${replayTime(state.elapsed)} of ${replayTime(replay.duration_seconds)}`}
          onChange={(event) =>
            dispatch({ type: "scrub", elapsed: Number(event.target.value) })
          }
        />
      </label>
      <p className="section-note">
        Timing/order view. Markers show recorded ranks, not track positions.
        Between samples, order is held for up to{" "}
        {replay.quality.max_hold_seconds}s and labelled calculated; gaps stay
        unavailable. Lap windows may be estimates. Missing activity is not
        evidence of retirement.
      </p>
      <details className="replay-selection">
        <summary>
          Drivers · {state.visible.length} of {replay.drivers.length} shown
        </summary>
        <div className="replay-driver-options">
          {replay.drivers.map(({ driver }) => (
            <label key={driver.id}>
              <input
                type="checkbox"
                checked={state.visible.includes(driver.id)}
                aria-label={`Show ${driver.family_name}`}
                onChange={() => dispatch({ type: "toggle", id: driver.id })}
              />
              {driver.code ?? driver.family_name} · {driver.given_name}{" "}
              {driver.family_name}
            </label>
          ))}
        </div>
      </details>
      <label className="replay-focus">
        Focus driver
        <select
          value={state.focus ?? ""}
          onChange={(event) =>
            dispatch({ type: "focus", id: event.target.value || null })
          }
        >
          <option value="">All drivers</option>
          {replay.drivers.map(({ driver }) => (
            <option key={driver.id} value={driver.id}>
              Focus {driver.family_name}
            </option>
          ))}
        </select>
      </label>
      <ol className="replay-order" aria-label="Driver order at replay time">
        {rows.map((row) => {
          const driver = row.entry.driver;
          const focused = state.focus === driver.id;
          return (
            <li
              key={driver.id}
              className={focused ? "replay-row replay-row-focus" : "replay-row"}
            >
              <div className="replay-identity">
                <strong>{driver.code ?? driver.family_name}</strong>
                <span>
                  {driver.given_name} {driver.family_name}
                </span>
                <small>{row.entry.team?.name ?? "Team unavailable"}</small>
              </div>
              <div
                className="replay-lane"
                aria-label={
                  row.position === null
                    ? `${driver.family_name}: order unavailable`
                    : `${driver.family_name}: recorded P${row.position}`
                }
              >
                {row.position !== null ? (
                  <span
                    className="replay-marker"
                    style={{
                      left: `${((row.position - 1) / (maxRank - 1)) * 90}%`,
                      transform: `translateX(-${((row.position - 1) / (maxRank - 1)) * 90}%)`,
                      borderColor: row.color,
                    }}
                  >
                    {driver.code ?? driver.family_name} · P{row.position}
                  </span>
                ) : (
                  <span className="muted">Unavailable</span>
                )}
              </div>
              <div className="replay-reading">
                <strong>
                  {row.quality === "source"
                    ? "Source sample"
                    : row.quality === "held"
                      ? `Calculated hold · ${row.age!.toFixed(1)}s`
                      : "Order unavailable"}
                </strong>
                {row.sample && (
                  <small>
                    Recorded at +{replayTime(row.sample.elapsed_seconds)}
                  </small>
                )}
                <span>
                  {row.lap
                    ? `Lap ${row.lap.lap_number} · ${row.lap.approximate ? "estimated window" : "calculated window"}`
                    : "Lap unavailable"}
                </span>
                <span>
                  {row.inPit
                    ? "In pit lane · calculated duration window"
                    : "Pit state unavailable"}
                </span>
                <small>
                  {row.gap?.gap_to_leader_laps != null
                    ? `${row.gap.gap_to_leader_laps} lap(s) to leader · ${row.gap.elapsed_seconds < state.elapsed ? "calculated hold" : "source"}`
                    : row.gap?.gap_to_leader_seconds != null
                      ? `${row.gap.gap_to_leader_seconds}s to leader · ${row.gap.elapsed_seconds < state.elapsed ? "calculated hold" : "source"}`
                      : "Leader gap unavailable"}
                </small>
              </div>
            </li>
          );
        })}
      </ol>
      {!rows.length && (
        <p role="status">
          No drivers selected. Choose drivers above to show recorded order.
        </p>
      )}
      <section aria-label="Recorded race control">
        <h2>Race control</h2>
        <p className="section-note">
          Latest recorded messages at this replay time; no inferred incidents or
          intent.
        </p>
        {events.length ? (
          <ul className="replay-events">
            {events.map((row) => (
              <li key={row.id}>
                <time dateTime={row.timestamp}>
                  +{replayTime(row.elapsed_seconds)}
                </time>{" "}
                {row.flag ? `${row.flag} · ` : ""}
                {row.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            No race-control messages available at this time.
          </p>
        )}
      </section>
    </section>
  );
}
