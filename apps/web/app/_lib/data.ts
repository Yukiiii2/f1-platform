import { notFound } from "next/navigation";
import { ApiError, getEntity, getList } from "./api";
import type {
  Circuit,
  Driver,
  DriverStanding,
  ConstructorStanding,
  RaceEvent,
  RaceSession,
  Result,
  SearchParams,
  Season,
  Team,
} from "./contracts";
import { selectSeason, single } from "./format";

export async function seasonContext(params: SearchParams) {
  const seasons = await getList<Season>("seasons");
  const season = selectSeason(seasons, single(params.season));
  return { seasons, season };
}
export function seasonEvents(year: number) {
  return getList<RaceEvent>("events", { season: year });
}
export function eventSessions(id: string) {
  return getList<RaceSession>(`events/${id}/sessions`);
}
// Race detail and replay share UUID lookup, season validation and session scope.
export async function raceContext(eventId: string, query: SearchParams) {
  const event = await detail<RaceEvent>("events", eventId);
  const [sessions, seasons] = await Promise.all([
    eventSessions(event.id),
    getList<Season>("seasons"),
  ]);
  const season = seasons.find((row) => row.id === event.season_id);
  if (
    season &&
    single(query.season) !== undefined &&
    single(query.season) !== String(season.year)
  )
    notFound();
  const selectedId = single(query.session);
  const selected = selectedId
    ? sessions.find((session) => session.id === selectedId)
    : (sessions.find((session) => session.type === "race") ?? sessions[0]);
  if (selectedId && !selected) notFound();
  return { event, sessions, seasons, season, selected };
}
export async function homeCalendar(events: RaceEvent[], now: Date) {
  const today = now.toISOString().slice(0, 10);
  const calendar: RaceEvent[] = [];
  const sessions = new Map<string, RaceSession[]>();
  for (const event of events) {
    const scheduled = event.starts_at
      ? Date.parse(event.starts_at) >= now.getTime()
      : event.scheduled_date !== null && event.scheduled_date >= today;
    if (!scheduled) continue;
    const rows = await eventSessions(event.id);
    sessions.set(event.id, rows);
    const race = rows.find((row) => row.type === "race");
    if (race && ["completed", "cancelled", "in_progress"].includes(race.status))
      continue;
    calendar.push(event);
    if (calendar.length === 3) break;
  }
  const featured = calendar[0] ?? events.at(-1);
  return {
    calendar,
    featured,
    sessions: featured
      ? (sessions.get(featured.id) ?? (await eventSessions(featured.id)))
      : [],
  };
}
export function sessionResults(id: string) {
  return getList<Result>(`sessions/${id}/results`);
}
export function driverStandings(year: number) {
  return getList<DriverStanding>("standings/drivers", { season: year });
}
export function constructorStandings(year: number) {
  return getList<ConstructorStanding>("standings/constructors", {
    season: year,
  });
}
export async function detail<T>(
  resource: "events" | "circuits" | "drivers" | "teams" | "sessions",
  id: string,
): Promise<T> {
  try {
    return await getEntity<T>(resource, id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}
export async function references<T extends { id: string }>(
  resource: "circuits" | "drivers" | "teams",
  ids: string[],
): Promise<Map<string, T>> {
  const unique = [...new Set(ids)];
  const resolved = new Map<string, T>();
  for (let start = 0; start < unique.length; start += 200) {
    const batch = unique.slice(start, start + 200);
    const rows = await getList<T>(resource, { ids: batch.join(",") });
    for (const row of rows) resolved.set(row.id, row);
    if (batch.some((id) => !resolved.has(id))) throw new ApiError(404);
  }
  return resolved;
}
export async function resultNames(results: Result[]) {
  const [drivers, teams] = await Promise.all([
    references<Driver>(
      "drivers",
      results.map((row) => row.driver_id),
    ),
    references<Team>(
      "teams",
      results.map((row) => row.team_id),
    ),
  ]);
  return { drivers, teams };
}
export function circuitDetail(id: string) {
  return detail<Circuit>("circuits", id);
}
