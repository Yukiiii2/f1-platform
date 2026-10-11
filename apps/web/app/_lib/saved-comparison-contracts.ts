export type ComparisonContext = {
  version: 1;
  season: number;
  event_id: string;
  session_id: string;
  driver_a_id: string;
  driver_b_id: string;
};
export type TelemetryPreset = {
  comparison_type: "telemetry_laps";
  configuration: ComparisonContext & {
    lap_a_id: string;
    lap_b_id: string;
    alignment: "normalized_distance" | "elapsed_time";
    allow_approximate: boolean;
  };
};
export type StrategyPreset = {
  comparison_type: "strategy_tyres";
  configuration: ComparisonContext & { provider_a: string; provider_b: string };
};
export type Preset = TelemetryPreset | StrategyPreset;
export type SavedComparison = {
  comparison_type: Preset["comparison_type"];
  configuration: { season: number; version?: number | null } & Partial<
    Omit<ComparisonContext, "season" | "version">
  >;
  id: string;
  title: string;
  source_route: "/telemetry" | "/strategy";
  created_at: string;
  updated_at: string;
  event_name: string | null;
  session_name: string | null;
  driver_a_name: string | null;
  driver_b_name: string | null;
  lap_a_number: number | null;
  lap_b_number: number | null;
  availability: "available" | "partial" | "unavailable";
  notices: string[];
  open_url: string | null;
};
export type SaveResult =
  | { response: SavedComparison; error?: never }
  | { response?: never; error: string };
