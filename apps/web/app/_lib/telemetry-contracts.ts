// Phase 4/5 application contracts. Decimal values arrive as strings.
export interface Lap {
  id: string;
  session_id: string;
  driver_id: string;
  provider: string;
  lap_number: number;
  starts_at: string | null;
  duration_seconds: string | null;
  sector_1_seconds: string | null;
  sector_2_seconds: string | null;
  sector_3_seconds: string | null;
  is_pit_out_lap: boolean | null;
  start_time_is_approximate: boolean;
}
export interface TyreContext {
  status: "available" | "unavailable" | "ambiguous";
  stint_id: string | null;
  compound: string | null;
  lap_start: number | null;
  lap_end: number | null;
  tyre_age_at_start: number | null;
  completed_laps_before: number | null;
  completed_laps_after: number | null;
  total_age_before: number | null;
  total_age_after: number | null;
  age_classification: "derived";
  formula_version: string;
}
export interface Channels {
  speed_kph: string | null;
  throttle_percent: string | null;
  rpm: string | null;
  brake_applied: boolean | null;
  gear: number | null;
  drs_state: number | null;
}
export type Channel = keyof Channels;
export type Alignment = "normalized_distance" | "elapsed_time";
export interface ComparisonRequest {
  lap_a_id: string;
  lap_b_id: string;
  sample_count: number;
  alignment: Alignment;
  allow_approximate: boolean;
}
export interface TracePoint {
  coordinate: string;
  elapsed_seconds_a: string | null;
  elapsed_seconds_b: string | null;
  delta_ms: string | null;
  channels_a: Channels;
  channels_b: Channels;
}
export interface Comparison {
  lap_a: { lap: Lap; tyres: TyreContext };
  lap_b: { lap: Lap; tyres: TyreContext };
  lap_delta_ms: string | null;
  sector_delta_ms: {
    sector_1: string | null;
    sector_2: string | null;
    sector_3: string | null;
  };
  delta_classification: "derived";
  delta_sign: "a_minus_b_positive_a_slower";
  formula_version: string;
  trace: {
    requested_alignment: Alignment;
    alignment: Alignment | null;
    axis: "fraction_of_integrated_distance" | "elapsed_seconds" | null;
    availability: "available" | "partial" | "unavailable";
    classification: "derived" | "estimate";
    association_a: "confirmed" | "approximate_window" | "unavailable";
    association_b: "confirmed" | "approximate_window" | "unavailable";
    sample_count_a: number;
    sample_count_b: number;
    sample_resolution: string | null;
    max_interpolation_gap_seconds: string;
    continuous_interpolation: "linear";
    discrete_interpolation: "previous_sample";
    distance_method: "trapezoidal_speed_integration" | null;
    distance_a_m: string | null;
    distance_b_m: string | null;
    distance_is_track_position: false;
    delta_available: boolean;
    warnings: string[];
    points: TracePoint[];
  };
}
