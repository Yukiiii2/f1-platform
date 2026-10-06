"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import type { Driver } from "../_lib/contracts";
import type { Lap } from "../_lib/telemetry-contracts";
import { driverName, formatDuration } from "../_lib/format";
import { channelNumber } from "../_lib/telemetry";

export function CompareForm({
  laps,
  drivers,
  context,
  selected,
}: {
  laps: Lap[];
  drivers: Driver[];
  context: { season: number; event: string; session: string };
  selected: Record<string, string | undefined>;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [driverA, setDriverA] = useState(
    selected.driver_a ??
      laps.find((lap) => lap.id === selected.lap_a)?.driver_id ??
      "",
  );
  const [driverB, setDriverB] = useState(
    selected.driver_b ??
      laps.find((lap) => lap.id === selected.lap_b)?.driver_id ??
      "",
  );
  const [lapA, setLapA] = useState(selected.lap_a ?? "");
  const [lapB, setLapB] = useState(selected.lap_b ?? "");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    data.forEach((value, key) => params.set(key, String(value)));
    startTransition(() => router.push(`/telemetry?${params}#comparison`));
  }
  function side(
    label: "A" | "B",
    driver: string,
    lap: string,
    changeDriver: (value: string) => void,
    changeLap: (value: string) => void,
  ) {
    const suffix = label.toLowerCase();
    const choices = laps
      .filter((row) => row.driver_id === driver)
      .sort(
        (a, b) =>
          a.lap_number - b.lap_number || a.provider.localeCompare(b.provider),
      );
    return (
      <fieldset className={`lap-choice lap-${suffix}`}>
        <legend>Lap {label}</legend>
        <div className="field">
          <label htmlFor={`driver-${suffix}`}>Driver {label}</label>
          <select
            id={`driver-${suffix}`}
            name={`driver_${suffix}`}
            required
            value={driver}
            onChange={(event) => {
              changeDriver(event.target.value);
              changeLap("");
            }}
          >
            <option value="" disabled>
              Choose a driver
            </option>
            {drivers.map((row) => (
              <option key={row.id} value={row.id}>
                {driverName(row)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`lap-${suffix}`}>Recorded lap {label}</label>
          <select
            id={`lap-${suffix}`}
            name={`lap_${suffix}`}
            required
            disabled={!driver}
            value={lap}
            onChange={(event) => changeLap(event.target.value)}
          >
            <option value="" disabled>
              Choose a lap
            </option>
            {choices.map((row) => {
              const duration = channelNumber(row.duration_seconds);
              return (
                <option
                  key={row.id}
                  value={row.id}
                  disabled={row.id === (label === "A" ? lapB : lapA)}
                >
                  Lap {row.lap_number} ·{" "}
                  {duration === null
                    ? "Time unavailable"
                    : formatDuration(Math.round(duration * 1000))}{" "}
                  · {row.provider}
                  {row.is_pit_out_lap ? " · Pit out" : ""}
                </option>
              );
            })}
          </select>
        </div>
      </fieldset>
    );
  }
  return (
    <form
      action="/telemetry"
      method="get"
      className="comparison-form"
      onSubmit={submit}
      aria-busy={pending}
    >
      {Object.entries(context).map(([key, value]) => (
        <input key={key} type="hidden" name={key} value={value} />
      ))}
      <input type="hidden" name="compare" value="1" />
      <div className="lap-choices">
        {side("A", driverA, lapA, setDriverA, setLapA)}
        {side("B", driverB, lapB, setDriverB, setLapB)}
      </div>
      <div className="comparison-options">
        <div className="field">
          <label htmlFor="alignment">Alignment</label>
          <select
            id="alignment"
            name="alignment"
            defaultValue={
              selected.alignment === "elapsed_time"
                ? "elapsed_time"
                : "normalized_distance"
            }
          >
            <option value="normalized_distance">
              Normalized integrated distance
            </option>
            <option value="elapsed_time">Elapsed time</option>
          </select>
        </div>
        <div className="approximate-option">
          <label htmlFor="allow-approximate">
            <input
              id="allow-approximate"
              type="checkbox"
              name="allow_approximate"
              value="1"
              defaultChecked={selected.allow_approximate === "1"}
              aria-describedby="approximate-note"
            />
            Allow estimated lap windows
          </label>
          <p id="approximate-note">
            Required for OpenF1 traces with approximate starts. Timing remains
            source data; aligned traces are estimates.
          </p>
        </div>
        <button
          className="button"
          type="submit"
          disabled={pending || !lapA || !lapB || lapA === lapB}
        >
          {pending ? "Comparing laps…" : "Compare laps"}
        </button>
      </div>
      <p className="section-note" role="status">
        {pending
          ? "Loading comparison. Your current result remains visible until the new one is ready."
          : "Choose two distinct laps from this session. Comparing different laps from the same driver is supported."}
      </p>
    </form>
  );
}
