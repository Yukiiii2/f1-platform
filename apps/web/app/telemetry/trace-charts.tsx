"use client";

import { useMemo, useState } from "react";
import type { Channel, Comparison } from "../_lib/telemetry-contracts";
import {
  channelLabel,
  channelNumber,
  signedDelta,
  tracePaths,
} from "../_lib/telemetry";

const channels: {
  key: Channel;
  title: string;
  unit: string;
  discrete?: boolean;
}[] = [
  { key: "speed_kph", title: "Speed", unit: "km/h" },
  { key: "throttle_percent", title: "Throttle", unit: "%" },
  {
    key: "brake_applied",
    title: "Brake state",
    unit: "Applied / released",
    discrete: true,
  },
  { key: "gear", title: "Gear", unit: "Gear number", discrete: true },
  { key: "rpm", title: "RPM", unit: "rev/min" },
  { key: "drs_state", title: "DRS state", unit: "Source code", discrete: true },
];

export function TraceCharts({
  trace,
  labelA,
  labelB,
}: {
  trace: Comparison["trace"];
  labelA: string;
  labelB: string;
}) {
  const [selected, setSelected] = useState(0);
  const point = trace.points[selected];
  const distance = trace.axis === "fraction_of_integrated_distance";
  function coordinate(value: string) {
    const number = channelNumber(value);
    return number === null
      ? "Unavailable"
      : distance
        ? `${(number * 100).toFixed(1)}%`
        : `${number.toFixed(3)} s`;
  }
  const plots = useMemo(() => {
    const definitions = [
      ...channels,
      {
        key: "delta" as const,
        title: "Delta · A − B",
        unit: "ms",
        discrete: false,
      },
    ];
    return definitions.map((definition) => {
      const delta = definition.key === "delta";
      const a = trace.points.map((row) =>
        channelNumber(
          delta ? row.delta_ms : row.channels_a[definition.key as Channel],
        ),
      );
      const b = delta
        ? []
        : trace.points.map((row) =>
            channelNumber(row.channels_b[definition.key as Channel]),
          );
      const known = [...a, ...b].filter(
        (value): value is number => value !== null,
      );
      let min = delta ? Math.min(0, ...known) : 0;
      let max = Math.max(0, ...known);
      if (definition.key === "brake_applied") max = 1;
      if (max === min) {
        min -= delta ? 1 : 0;
        max += 1;
      }
      return {
        ...definition,
        delta,
        a,
        b,
        min,
        max,
        hasData: known.length > 0,
        pathA: tracePaths(a, min, max, definition.discrete),
        pathB: tracePaths(b, min, max, definition.discrete),
      };
    });
  }, [trace]);
  function elapsed(value: string | null) {
    const number = channelNumber(value);
    return number === null ? "Unavailable" : `${number.toFixed(3)} s`;
  }
  return (
    <div className="trace-charts">
      <div className="trace-inspector">
        <label htmlFor="trace-sample">
          Inspect a shared sample ·{" "}
          {distance ? "Normalized integrated distance" : "Elapsed time"}
        </label>
        <input
          id="trace-sample"
          type="range"
          min={0}
          max={trace.points.length - 1}
          step={1}
          value={selected}
          onChange={(event) => setSelected(Number(event.target.value))}
          aria-describedby="trace-inspector-help"
          aria-valuetext={`${coordinate(point.coordinate)}; A ${elapsed(point.elapsed_seconds_a)}; B ${elapsed(point.elapsed_seconds_b)}; delta ${signedDelta(point.delta_ms)}`}
        />
        <p id="trace-inspector-help" className="section-note">
          Use arrow keys, drag the slider, or point at a chart to inspect the
          same sample across all channels. Gaps indicate unavailable data.
        </p>
        <p className="trace-readout" role="status">
          {coordinate(point.coordinate)} · A {elapsed(point.elapsed_seconds_a)}{" "}
          · B {elapsed(point.elapsed_seconds_b)} · Delta{" "}
          {signedDelta(point.delta_ms)}
        </p>
      </div>
      <p className="comparison-legend">
        <span className="legend-a">A · {labelA} · solid line</span>
        <span className="legend-b">B · {labelB} · dashed line</span>
      </p>
      {plots.map((plot) => {
        const { key, delta, min, max } = plot;
        const valueA = delta
          ? signedDelta(point.delta_ms)
          : channelLabel(key as Channel, point.channels_a[key as Channel]);
        const valueB = delta
          ? ""
          : channelLabel(key as Channel, point.channels_b[key as Channel]);
        if (delta && !trace.delta_available)
          return (
            <div key={key} className="delta-unavailable">
              <h3>Delta trace unavailable</h3>
              <p className="section-note">
                Elapsed-time alignment has no position reference for a delta
                trace. The source lap and sector deltas remain above.
              </p>
            </div>
          );
        const axisLabel = (value: number) =>
          key === "brake_applied"
            ? value === 1
              ? "Applied"
              : value === 0
                ? "Released"
                : ""
            : new Intl.NumberFormat("en-GB", {
                maximumFractionDigits: delta || plot.discrete ? 0 : 1,
              }).format(value);
        return (
          <figure key={key} className="trace-figure">
            <figcaption>
              <h3 id={`chart-${key}`}>
                {plot.title} <span className="muted">{plot.unit}</span>
              </h3>
              <div className="trace-values">
                {delta ? (
                  <span>{valueA}</span>
                ) : (
                  <>
                    <span className="legend-a">A {valueA}</span>
                    <span className="legend-b">B {valueB}</span>
                  </>
                )}
              </div>
            </figcaption>
            {!plot.hasData ? (
              <p className="section-note">
                No {plot.title.toLowerCase()} samples are available for either
                lap. Choose other recorded laps.
              </p>
            ) : (
              <>
                <div className="trace-plot">
                  <div className="trace-y-axis" aria-hidden="true">
                    <span>{axisLabel(max)}</span>
                    <span>{axisLabel((min + max) / 2)}</span>
                    <span>{axisLabel(min)}</span>
                  </div>
                  <svg
                    viewBox="0 0 1000 140"
                    preserveAspectRatio="none"
                    role="img"
                    aria-labelledby={`chart-${key}`}
                    aria-describedby={`chart-description-${key}`}
                    onPointerMove={(event) => {
                      const bounds =
                        event.currentTarget.getBoundingClientRect();
                      setSelected(
                        Math.max(
                          0,
                          Math.min(
                            trace.points.length - 1,
                            Math.round(
                              ((event.clientX - bounds.left) / bounds.width) *
                                (trace.points.length - 1),
                            ),
                          ),
                        ),
                      );
                    }}
                  >
                    <desc id={`chart-description-${key}`}>
                      {delta
                        ? "Calculated timing delta"
                        : "Lap A is solid; Lap B is dashed"}
                      . Horizontal axis:{" "}
                      {distance
                        ? "normalized integrated distance from 0 to 100 percent"
                        : "elapsed seconds"}
                      . Nulls break the line. Selected values are shown above;
                      use the shared slider to inspect with a keyboard.
                    </desc>
                    {[0, 70, 140].map((y) => (
                      <line
                        key={y}
                        className="trace-grid"
                        x1={0}
                        x2={1000}
                        y1={y}
                        y2={y}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                    {delta && min < 0 && max > 0 && (
                      <line
                        className="trace-zero"
                        x1={0}
                        x2={1000}
                        y1={140 - ((0 - min) / (max - min)) * 140}
                        y2={140 - ((0 - min) / (max - min)) * 140}
                        vectorEffect="non-scaling-stroke"
                      />
                    )}
                    {[plot.pathA, plot.pathB].map((series, index) => (
                      <g
                        key={index}
                        className={index === 0 ? "trace-a" : "trace-b"}
                      >
                        <path
                          d={series.path}
                          fill="none"
                          vectorEffect="non-scaling-stroke"
                        />
                        {series.dots.map((dot, i) => (
                          <circle
                            key={i}
                            cx={dot.x}
                            cy={dot.y}
                            r="1.5"
                            vectorEffect="non-scaling-stroke"
                          />
                        ))}
                      </g>
                    ))}
                    <line
                      className="trace-cursor"
                      x1={
                        (selected * 1000) / Math.max(1, trace.points.length - 1)
                      }
                      x2={
                        (selected * 1000) / Math.max(1, trace.points.length - 1)
                      }
                      y1={0}
                      y2={140}
                      vectorEffect="non-scaling-stroke"
                    />
                  </svg>
                </div>
                <div className="trace-x-axis" aria-hidden="true">
                  <span>{coordinate(trace.points[0].coordinate)}</span>
                  <span>
                    {coordinate(
                      trace.points[Math.floor((trace.points.length - 1) / 2)]
                        .coordinate,
                    )}
                  </span>
                  <span>{coordinate(trace.points.at(-1)!.coordinate)}</span>
                </div>
              </>
            )}
          </figure>
        );
      })}
    </div>
  );
}
