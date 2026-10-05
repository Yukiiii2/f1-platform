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
  const rows = await Promise.all(
    [...new Set(ids)].map((id) => getEntity<T>(resource, id)),
  );
  return new Map(rows.map((row) => [row.id, row]));
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
