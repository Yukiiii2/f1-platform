import type {
  Preset,
  TelemetryPreset,
  StrategyPreset,
} from "./saved-comparison-contracts";

type Scope = { season: number; event_id: string; session_id: string };

export function telemetryPreset(
  scope: Scope,
  laps: { id: string; driver_id: string }[],
  selection: {
    lap_a_id: string;
    lap_b_id: string;
    alignment: "normalized_distance" | "elapsed_time";
    allow_approximate: boolean;
  },
): TelemetryPreset | null {
  const a = laps.find((lap) => lap.id === selection.lap_a_id);
  const b = laps.find((lap) => lap.id === selection.lap_b_id);
  if (!a || !b || a.id === b.id) return null;
  return {
    comparison_type: "telemetry_laps",
    configuration: {
      version: 1,
      ...scope,
      driver_a_id: a.driver_id,
      driver_b_id: b.driver_id,
      lap_a_id: a.id,
      lap_b_id: b.id,
      alignment: selection.alignment,
      allow_approximate: selection.allow_approximate,
    },
  };
}
export function strategyPreset(
  scope: Scope,
  rows: { driver_id: string; provider: string }[],
): StrategyPreset | null {
  if (
    rows.length !== 2 ||
    (rows[0].driver_id === rows[1].driver_id &&
      rows[0].provider === rows[1].provider)
  )
    return null;
  return {
    comparison_type: "strategy_tyres",
    configuration: {
      version: 1,
      ...scope,
      driver_a_id: rows[0].driver_id,
      driver_b_id: rows[1].driver_id,
      provider_a: rows[0].provider,
      provider_b: rows[1].provider,
    },
  };
}
export function comparisonError(status: number) {
  return status === 404
    ? "This saved comparison is no longer available. Return to Saved Comparisons."
    : status === 422
      ? "The title or selections are no longer valid. Reload the source page and check the recorded selections."
      : "Saved comparisons are temporarily unavailable. Your selections are unchanged; retry when the service is available.";
}
export function comparisonTitle(preset: Preset) {
  return preset.comparison_type === "telemetry_laps"
    ? "Telemetry lap comparison"
    : "Strategy and tyres";
}
