import Link from "next/link";
import type {
  Circuit,
  ConstructorStanding,
  Driver,
  DriverStanding,
  RaceEvent,
  Result,
  SessionType,
  Team,
} from "../_lib/contracts";
import {
  driverName,
  formatDuration,
  formatPoints,
  formatSchedule,
  rank,
} from "../_lib/format";
import { TableRegion } from "./ui";
export function EventTable({
  events,
  circuits,
  caption = "Race calendar",
}: {
  events: RaceEvent[];
  circuits: Map<string, Circuit>;
  caption?: string;
}) {
  return (
    <TableRegion label={caption}>
      <table className="race-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Round</th>
            <th scope="col">Grand Prix</th>
            <th scope="col">Race schedule</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => {
            const circuit = circuits.get(event.circuit_id);
            return (
              <tr key={event.id}>
                <td className="numeric round">
                  {String(event.round).padStart(2, "0")}
                </td>
                <th scope="row">
                  <Link href={`/races/${event.id}`} prefetch={false}>
                    {event.name}
                  </Link>
                  <span className="cell-detail">
                    {circuit
                      ? `${circuit.name} · ${circuit.country}`
                      : "Circuit unavailable"}
                  </span>
                </th>
                <td>
                  <time
                    dateTime={
                      event.starts_at ?? event.scheduled_date ?? undefined
                    }
                  >
                    {formatSchedule(event)}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableRegion>
  );
}
export function DriverStandingsTable({
  rows,
  drivers,
  year,
  caption,
}: {
  rows: DriverStanding[];
  drivers: Map<string, Driver>;
  year: number;
  caption: string;
}) {
  return (
    <TableRegion label="Driver championship standings">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Position</th>
            <th scope="col">Driver</th>
            <th scope="col" className="numeric">
              Wins
            </th>
            <th scope="col" className="numeric">
              Points
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const driver = drivers.get(row.driver_id);
            return (
              <tr key={row.id}>
                <td className="numeric position">{rank(row.position)}</td>
                <th scope="row">
                  <Link
                    href={`/drivers/${row.driver_id}?season=${year}`}
                    prefetch={false}
                  >
                    {driver ? driverName(driver) : "Driver unavailable"}
                  </Link>
                  {driver?.code && (
                    <span className="cell-detail">{driver.code}</span>
                  )}
                </th>
                <td className="numeric">{row.wins}</td>
                <td className="numeric points">{formatPoints(row.points)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableRegion>
  );
}
export function ConstructorStandingsTable({
  rows,
  teams,
  caption,
}: {
  rows: ConstructorStanding[];
  teams: Map<string, Team>;
  caption: string;
}) {
  return (
    <TableRegion label="Constructor championship standings">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Position</th>
            <th scope="col">Constructor</th>
            <th scope="col" className="numeric">
              Wins
            </th>
            <th scope="col" className="numeric">
              Points
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="numeric position">{rank(row.position)}</td>
              <th scope="row">
                {teams.get(row.team_id)?.name ?? "Constructor unavailable"}
              </th>
              <td className="numeric">{row.wins}</td>
              <td className="numeric points">{formatPoints(row.points)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableRegion>
  );
}
export function ResultsTable({
  results,
  drivers,
  teams,
  type,
  year,
}: {
  results: Result[];
  drivers: Map<string, Driver>;
  teams: Map<string, Team>;
  type: SessionType;
  year?: number;
}) {
  const classifiedRace = type === "race" || type === "sprint";
  return (
    <TableRegion label="Session classification">
      <table>
        <caption>
          Imported session classification. Missing values remain unavailable.
        </caption>
        <thead>
          <tr>
            <th scope="col">Position</th>
            <th scope="col">Driver</th>
            <th scope="col">Constructor</th>
            {classifiedRace && (
              <>
                <th scope="col" className="numeric">
                  Grid
                </th>
                <th scope="col" className="numeric">
                  Laps
                </th>
                <th scope="col">Elapsed / gap</th>
                <th scope="col" className="numeric">
                  Points
                </th>
                <th scope="col">Finish status</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {results.map((row) => {
            const driver = drivers.get(row.driver_id);
            return (
              <tr key={row.id}>
                <td className="numeric position">{rank(row.position)}</td>
                <th scope="row">
                  <Link
                    href={`/drivers/${row.driver_id}${year ? `?season=${year}` : ""}`}
                    prefetch={false}
                  >
                    {driver ? driverName(driver) : "Driver unavailable"}
                  </Link>
                </th>
                <td>
                  {teams.get(row.team_id)?.name ?? "Constructor unavailable"}
                </td>
                {classifiedRace && (
                  <>
                    <td className="numeric">
                      {row.grid_position === 0
                        ? "Pit lane"
                        : (row.grid_position ?? "Not available")}
                    </td>
                    <td className="numeric">
                      {row.completed_laps ?? "Not available"}
                    </td>
                    <td className="numeric">
                      {row.gap_ms !== null
                        ? `+${(row.gap_ms / 1000).toFixed(3)} s`
                        : formatDuration(row.total_time_ms)}
                    </td>
                    <td className="numeric points">
                      {formatPoints(row.points)}
                    </td>
                    <td>{row.status ?? "Not available"}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableRegion>
  );
}
