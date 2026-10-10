import type { Driver, RaceSession, Team } from "./contracts";

export interface ReplayPoint {
  id: string;
  timestamp: string;
  elapsed_seconds: number;
  position: number;
}
export interface ReplayDriver {
  driver: Driver;
  team: Team | null;
  source_sample_count: number;
  positions: ReplayPoint[];
  intervals: {
    timestamp: string;
    elapsed_seconds: number;
    gap_to_leader_seconds: string | null;
    gap_to_leader_laps: number | null;
  }[];
  laps: {
    lap_number: number;
    starts_at: string;
    start_seconds: number;
    end_seconds: number | null;
    approximate: boolean;
  }[];
  pits: {
    timestamp: string;
    elapsed_seconds: number;
    lane_duration_seconds: string | null;
    lap_number: number | null;
  }[];
  inactive_state: null;
}
export interface SessionReplay {
  session: RaceSession;
  event_id: string;
  event_name: string;
  season: number;
  capability: "available" | "partial" | "unavailable";
  mode: "timing_order";
  provisional: boolean;
  provider: string | null;
  starts_at: string | null;
  ends_at: string | null;
  duration_seconds: number;
  drivers: ReplayDriver[];
  race_control: {
    id: string;
    timestamp: string;
    elapsed_seconds: number;
    message: string;
    category: string | null;
    flag: string | null;
    scope: string | null;
    driver_id: string | null;
    lap_number: number | null;
  }[];
  quality: {
    method: "recorded-order-v1";
    interpolation: "previous_sample_hold";
    max_hold_seconds: number;
    coordinates_available: false;
    gaps_present: boolean;
    downsampled: boolean;
    truncated_context: boolean;
    omitted_driver_count: number;
    sampling_seconds: number;
    notes: string[];
  };
}
