import Link from "next/link";
import { CarShowcase } from "./_components/car-showcase";
import type { Circuit, Driver, SearchPageProps, Team } from "./_lib/contracts";
import {
  constructorStandings,
  driverStandings,
  homeCalendar,
  references,
  seasonContext,
  seasonEvents,
} from "./_lib/data";
import { formatSchedule } from "./_lib/format";
import {
  ConstructorStandingsTable,
  DriverStandingsTable,
  EventTable,
} from "./_components/tables";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SeasonSelector,
  SectionHeading,
  Status,
} from "./_components/ui";

export default async function HomePage({ searchParams }: SearchPageProps) {
  const { seasons, season } = await seasonContext(await searchParams);
  if (!season)
    return (
      <>
        <PageHeading title="A clearer view of the race.">
          <SeasonSelector seasons={seasons} selected={null} />
        </PageHeading>
        <NoSeason />
      </>
    );
  const [events, driverRows, constructorRows] = await Promise.all([
    seasonEvents(season.year),
    driverStandings(season.year),
    constructorStandings(season.year),
  ]);
  const { featured, calendar, sessions } = await homeCalendar(
    events,
    new Date(),
  );
  const topDrivers = driverRows.slice(0, 5);
  const topTeams = constructorRows.slice(0, 5);
  const [circuits, drivers, teams] = await Promise.all([
    references<Circuit>(
      "circuits",
      [...calendar, ...(featured ? [featured] : [])].map(
        (event) => event.circuit_id,
      ),
    ),
    references<Driver>(
      "drivers",
      topDrivers.map((row) => row.driver_id),
    ),
    references<Team>(
      "teams",
      topTeams.map((row) => row.team_id),
    ),
  ]);
  const circuit = featured ? circuits.get(featured.circuit_id) : null;
  const race = sessions.find((session) => session.type === "race");
  const driverSnapshot = events.find(
    (event) => event.id === driverRows[0]?.event_id,
  );
  const teamSnapshot = events.find(
    (event) => event.id === constructorRows[0]?.event_id,
  );
  return (
    <>
      <div className="home-toolbar">
        <p>{season.year} season</p>
        <SeasonSelector seasons={seasons} selected={season} />
      </div>
      {featured ? (
        <section className="race-hero" aria-labelledby="featured-race">
          <div>
            <h1 id="featured-race">{featured.name}</h1>
            <p className="hero-context">
              {calendar.length
                ? "Next on the calendar"
                : race?.status === "completed"
                  ? "Latest completed weekend"
                  : "Latest scheduled weekend"}
            </p>
            <p className="intro">
              {circuit?.name}
              {circuit && ` · ${circuit.country}`}
            </p>
            <Link
              className="button"
              href={`/races/${featured.id}`}
              prefetch={false}
            >
              Explore the weekend
            </Link>
          </div>
          <dl className="hero-facts">
            <div>
              <dt>Round</dt>
              <dd className="round-display">
                {String(featured.round).padStart(2, "0")}
              </dd>
            </div>
            <div>
              <dt>Race schedule</dt>
              <dd>
                <time
                  dateTime={
                    featured.starts_at ?? featured.scheduled_date ?? undefined
                  }
                >
                  {formatSchedule(featured)}
                </time>
              </dd>
            </div>
            <div>
              <dt>Race session</dt>
              <dd>{race ? <Status value={race.status} /> : "Not available"}</dd>
            </div>
          </dl>
          <CarShowcase />
        </section>
      ) : (
        <>
          <PageHeading title="The season, in focus." />
          <EmptyState title="The calendar is not available">
            <p>No events have been imported for {season.year} yet.</p>
          </EmptyState>
        </>
      )}
      <div className="championship-grid">
        <section>
          <SectionHeading title="Driver championship">
            <Link href={`/standings?season=${season.year}`} prefetch={false}>
              Full standings
            </Link>
          </SectionHeading>
          {topDrivers.length ? (
            <DriverStandingsTable
              rows={topDrivers}
              drivers={drivers}
              year={season.year}
              caption={
                driverSnapshot
                  ? `Snapshot after ${driverSnapshot.name}`
                  : "Latest imported snapshot"
              }
            />
          ) : (
            <EmptyState title="Standings not available">
              <p>
                No driver championship snapshot has been imported for this
                season.
              </p>
            </EmptyState>
          )}
        </section>
        <section>
          <SectionHeading title="Constructor championship">
            <Link
              href={`/standings?season=${season.year}&view=constructors`}
              prefetch={false}
            >
              Full standings
            </Link>
          </SectionHeading>
          {topTeams.length ? (
            <ConstructorStandingsTable
              rows={topTeams}
              teams={teams}
              caption={
                teamSnapshot
                  ? `Snapshot after ${teamSnapshot.name}`
                  : "Latest imported snapshot"
              }
            />
          ) : (
            <EmptyState title="Standings not available">
              <p>
                No constructor championship snapshot has been imported for this
                season.
              </p>
            </EmptyState>
          )}
        </section>
      </div>
      <section>
        <SectionHeading title="On the calendar">
          <Link href={`/races?season=${season.year}`} prefetch={false}>
            All race weekends
          </Link>
        </SectionHeading>
        {calendar.length ? (
          <EventTable
            events={calendar}
            circuits={circuits}
            caption="Next scheduled race weekends"
          />
        ) : (
          <p className="muted">
            No further race dates are recorded for this season. Browse the
            calendar for earlier weekends.
          </p>
        )}
      </section>
    </>
  );
}
