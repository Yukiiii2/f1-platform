import type { Metadata } from "next";
import Link from "next/link";
import { Pitwall } from "../../_components/pitwall";
import { suggestedQuestions } from "../../_lib/pitwall";
import type { Driver, SearchParams, Team } from "../../_lib/contracts";
import { sessionNames } from "../../_lib/contracts";
import {
  detail,
  driverStandings,
  eventSessions,
  references,
  seasonContext,
  seasonEvents,
  sessionResults,
} from "../../_lib/data";
import { driverName, formatPoints, rank, single } from "../../_lib/format";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SeasonSelector,
  SectionHeading,
  TableRegion,
} from "../../_components/ui";
export const metadata: Metadata = { title: "Driver profile" };
export default async function DriverPage({
  params,
  searchParams,
}: {
  params: Promise<{ driverId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ driverId }, query] = await Promise.all([params, searchParams]);
  const [driver, context] = await Promise.all([
    detail<Driver>("drivers", driverId),
    seasonContext(query),
  ]);
  const { seasons, season } = context;
  const [standings, events] = season
    ? await Promise.all([
        driverStandings(season.year),
        seasonEvents(season.year),
      ])
    : [[], []];
  const standing = standings.find((row) => row.driver_id === driver.id);
  const snapshot = events.find((event) => event.id === standing?.event_id);
  const requestedEvent = single(query.event);
  const today = new Date().toISOString().slice(0, 10);
  const past = events.filter(
    (event) =>
      (event.scheduled_date ?? event.starts_at?.slice(0, 10) ?? "9999") <=
      today,
  );
  const selected = requestedEvent
    ? events.find((event) => event.id === requestedEvent)
    : (past.at(-1) ?? events[0]);
  const sessions = selected
    ? (await eventSessions(selected.id)).filter((session) =>
        ["race", "qualifying", "sprint"].includes(session.type),
      )
    : [];
  const weekend = await Promise.all(
    sessions.map(async (session) => ({
      session,
      result: (await sessionResults(session.id)).find(
        (row) => row.driver_id === driver.id,
      ),
    })),
  );
  const recorded = weekend.filter((row) => row.result !== undefined);
  const teams = await references<Team>(
    "teams",
    recorded.flatMap((row) => (row.result ? [row.result.team_id] : [])),
  );
  return (
    <>
      <Link className="back-link" href="/drivers" prefetch={false}>
        Back to drivers
      </Link>
      <PageHeading title={driverName(driver)} intro="Driver profile">
        <SeasonSelector seasons={seasons} selected={season} />
      </PageHeading>
      <a className="back-link" href="#pitwall">
        Ask Pitwall about this driver
      </a>
      <dl className="facts">
        <div>
          <dt>Permanent number</dt>
          <dd>{driver.permanent_number ?? "Not available"}</dd>
        </div>
        <div>
          <dt>Driver code</dt>
          <dd>{driver.code ?? "Not available"}</dd>
        </div>
        <div>
          <dt>Nationality</dt>
          <dd>{driver.nationality ?? "Not available"}</dd>
        </div>
      </dl>
      {!season ? (
        <NoSeason />
      ) : (
        <>
          <section>
            <SectionHeading title={`${season.year} championship`} />
            {standing ? (
              <>
                <p className="section-note">
                  {snapshot
                    ? `Snapshot after ${snapshot.name}`
                    : "Latest imported driver snapshot"}
                  .
                </p>
                <dl className="facts championship-facts">
                  <div>
                    <dt>Position</dt>
                    <dd>{rank(standing.position)}</dd>
                  </div>
                  <div>
                    <dt>Points</dt>
                    <dd>{formatPoints(standing.points)}</dd>
                  </div>
                  <div>
                    <dt>Wins</dt>
                    <dd>{standing.wins}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <EmptyState title="Championship record not available">
                <p>
                  This driver has no record in the latest imported {season.year}{" "}
                  standings snapshot. Choose another season to explore their
                  records.
                </p>
              </EmptyState>
            )}
          </section>
          <section>
            <SectionHeading title="Weekend results" />
            {events.length > 0 && (
              <form className="filter-form weekend-filter" method="get">
                <input type="hidden" name="season" value={season.year} />
                <div className="field">
                  <label htmlFor="event">Race weekend</label>
                  <select
                    key={selected?.id ?? "missing"}
                    id="event"
                    name="event"
                    defaultValue={selected?.id ?? ""}
                  >
                    {!selected && (
                      <option value="" disabled>
                        Choose a weekend
                      </option>
                    )}
                    {events.map((event) => (
                      <option key={event.id} value={event.id}>
                        Round {event.round} · {event.name}
                      </option>
                    ))}
                  </select>
                </div>
                <button className="button button-quiet" type="submit">
                  View results
                </button>
              </form>
            )}
            {recorded.length ? (
              <TableRegion label="Driver weekend results">
                <table>
                  <caption>
                    {selected?.name}. Constructors reflect each recorded
                    session.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Session</th>
                      <th scope="col">Constructor</th>
                      <th scope="col" className="numeric">
                        Position
                      </th>
                      <th scope="col" className="numeric">
                        Points
                      </th>
                      <th scope="col">Finish status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recorded.map(
                      ({ session, result }) =>
                        result && (
                          <tr key={result.id}>
                            <th scope="row">
                              <Link
                                href={`/races/${selected?.id}?session=${session.id}#results`}
                                prefetch={false}
                              >
                                {sessionNames[session.type]}
                              </Link>
                            </th>
                            <td>
                              {teams.get(result.team_id)?.name ??
                                "Not available"}
                            </td>
                            <td className="numeric">{rank(result.position)}</td>
                            <td className="numeric">
                              {formatPoints(result.points)}
                            </td>
                            <td>{result.status ?? "Not available"}</td>
                          </tr>
                        ),
                    )}
                  </tbody>
                </table>
              </TableRegion>
            ) : (
              <EmptyState title="No driver results for this weekend">
                <p>
                  {selected
                    ? "No classification for this driver has been imported for the selected weekend. Try another race weekend."
                    : "Choose an available race weekend in this season to view results."}
                </p>
              </EmptyState>
            )}
          </section>
        </>
      )}
      <Pitwall
        context={{
          route: `/drivers/${driver.id}`,
          driver_id: driver.id,
          ...(season ? { season: season.year } : {}),
          ...(selected ? { event_id: selected.id } : {}),
        }}
        label={driverName(driver)}
        contextDetails={[
          ...(season ? [{ label: "Season", value: String(season.year) }] : []),
          { label: "Weekend", value: selected?.name ?? "No weekend selected" },
        ]}
        names={{ [driver.id]: driverName(driver) }}
        suggestions={suggestedQuestions({
          page: "driver",
          hasWeekend: Boolean(selected),
          hasResults: recorded.length > 0,
          hasSeason: Boolean(season),
          hasStanding: Boolean(standing),
        })}
      />
    </>
  );
}
