import type { Channel, ComparisonRequest, Lap } from "./telemetry-contracts";

export function comparisonRequest(
  laps: Pick<Lap, "id" | "driver_id">[],
  params: Record<string, string | undefined>,
): ComparisonRequest | null {
  const a = laps.find((lap) => lap.id === params.lap_a);
  const b = laps.find((lap) => lap.id === params.lap_b);
  const alignment = params.alignment || "normalized_distance";
  if (
    !a ||
    !b ||
    a.id === b.id ||
    (params.driver_a && params.driver_a !== a.driver_id) ||
    (params.driver_b && params.driver_b !== b.driver_id) ||
    !["normalized_distance", "elapsed_time"].includes(alignment) ||
    (params.allow_approximate !== undefined && params.allow_approximate !== "1")
  )
    return null;
  return {
    lap_a_id: a.id,
    lap_b_id: b.id,
    sample_count: 201,
    alignment: alignment as ComparisonRequest["alignment"],
    allow_approximate: params.allow_approximate === "1",
  };
}

export function channelNumber(
  value: string | number | boolean | null,
): number | null {
  if (value === null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
export function channelLabel(
  channel: Channel,
  value: string | number | boolean | null,
): string {
  const number = channelNumber(value);
  if (number === null) return "Unavailable";
  if (channel === "brake_applied") return number ? "Applied" : "Released";
  if (channel === "drs_state") return `Code ${number}`;
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits:
      channel === "speed_kph" || channel === "throttle_percent" ? 1 : 0,
  }).format(number);
}
export function signedDelta(value: string | null): string {
  const number = channelNumber(value);
  if (number === null) return "Unavailable";
  return `${number < 0 ? "−" : number > 0 ? "+" : ""}${Math.abs(number).toFixed(0)} ms`;
}

// Straight line segments for continuous traces; steps for discrete states.
// A null terminates a segment. Dots preserve isolated available points.
export function tracePaths(
  values: (number | null)[],
  min: number,
  max: number,
  discrete = false,
) {
  let path = "";
  let connected = false;
  const dots: { x: number; y: number }[] = [];
  const rounded = (value: number) => Number(value.toFixed(3));
  values.forEach((value, index) => {
    if (value === null) {
      connected = false;
      return;
    }
    const x = rounded((index * 1000) / Math.max(1, values.length - 1));
    const y = rounded(140 - ((value - min) / (max - min || 1)) * 140);
    path += `${path ? " " : ""}${connected ? (discrete ? `H${x} V${y}` : `L${x},${y}`) : `M${x},${y}`}`;
    dots.push({ x, y });
    connected = true;
  });
  return { path, dots };
}
