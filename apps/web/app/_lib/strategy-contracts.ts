import type { Entity } from "./contracts";

interface SessionSource extends Entity {
  session_id: string;
  provider: string;
}
export interface SourceStint extends SessionSource {
  driver_id: string;
  stint_number: number;
  lap_start: number | null;
  lap_end: number | null;
  compound: string | null;
  tyre_age_at_start: number | null;
}
export interface SourcePit extends SessionSource {
  driver_id: string;
  timestamp: string;
  lap_number: number | null;
  lane_duration_seconds: string | null;
  stop_duration_seconds: string | null;
}
export interface StrategyControl extends SessionSource {
  driver_id: string | null;
  timestamp: string;
  category: string | null;
  message: string;
  flag: string | null;
  scope: string | null;
  lap_number: number | null;
  sector: number | null;
  qualifying_phase: number | null;
}
export interface StrategyStint {
  source: SourceStint;
  context_status: "available" | "ambiguous" | "unavailable";
  age_completed_lap: number | null;
  completed_laps_on_stint: number | null;
  total_tyre_age: number | null;
  age_classification: "derived";
  age_formula_version: "completed-laps-v1";
  pace: {
    recorded_laps: number;
    included_laps: number;
    excluded_laps: number;
    average_seconds: string | null;
    best_seconds: string | null;
    unavailable_reason:
      "stint_context" | "pit_lap_context" | "no_eligible_laps" | null;
    classification: "derived";
    policy_version: "observed-non-pit-v1";
  };
}
export interface DriverStrategy {
  driver_id: string;
  provider: string;
  recorded_lap_count: number;
  stints: StrategyStint[];
  pits: SourcePit[];
}
export interface Strategy {
  session_id: string;
  lap_axis_end: number | null;
  drivers: DriverStrategy[];
  race_control: StrategyControl[];
}
