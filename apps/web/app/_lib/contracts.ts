// Phase 2 application contracts: UUID references, ISO dates, Decimal strings.
export interface Entity {
  id: string;
  created_at: string;
  updated_at: string;
}
export interface Season extends Entity {
  year: number;
}
export interface Schedule {
  scheduled_date: string | null;
  starts_at: string | null;
  ends_at: string | null;
}
export interface RaceEvent extends Entity, Schedule {
  season_id: string;
  circuit_id: string;
  round: number;
  name: string;
}
export interface Circuit extends Entity {
  name: string;
  country: string;
  locality: string | null;
  timezone: string | null;
}
export type SessionType =
  | "practice_1"
  | "practice_2"
  | "practice_3"
  | "qualifying"
  | "sprint_qualifying"
  | "sprint"
  | "race";
export type SessionStatus =
  | "unknown"
  | "upcoming"
  | "in_progress"
  | "completed"
  | "delayed"
  | "cancelled";
export interface RaceSession extends Entity, Schedule {
  event_id: string;
  type: SessionType;
  status: SessionStatus;
}
export interface Driver extends Entity {
  given_name: string;
  family_name: string;
  code: string | null;
  permanent_number: number | null;
  nationality: string | null;
}
export interface Team extends Entity {
  name: string;
  nationality: string | null;
}
export interface Result extends Entity {
  session_id: string;
  driver_id: string;
  team_id: string;
  position: number | null;
  grid_position: number | null;
  points: string | null;
  completed_laps: number | null;
  status: string | null;
  total_time_ms: number | null;
  gap_ms: number | null;
}
export interface Standing extends Entity {
  season_id: string;
  event_id: string;
  position: number | null;
  points: string;
  wins: number;
}
export interface DriverStanding extends Standing {
  driver_id: string;
}
export interface ConstructorStanding extends Standing {
  team_id: string;
}
export type SearchParams = Record<string, string | string[] | undefined>;
export interface SearchPageProps {
  searchParams: Promise<SearchParams>;
}
export const sessionNames: Record<SessionType, string> = {
  practice_1: "Practice 1",
  practice_2: "Practice 2",
  practice_3: "Practice 3",
  qualifying: "Qualifying",
  sprint_qualifying: "Sprint qualifying",
  sprint: "Sprint",
  race: "Race",
};
export const statusNames: Record<SessionStatus, string> = {
  unknown: "Status unavailable",
  upcoming: "Upcoming",
  in_progress: "In progress",
  completed: "Completed",
  delayed: "Delayed",
  cancelled: "Cancelled",
};
