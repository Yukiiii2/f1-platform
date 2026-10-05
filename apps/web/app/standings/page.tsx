import type { Metadata } from "next";
import Link from "next/link";
import type {
  Driver,
  RaceEvent,
  SearchPageProps,
  Team,
} from "../_lib/contracts";
import {
  constructorStandings,
  detail,
  driverStandings,
  references,
  seasonContext,
} from "../_lib/data";
import { single } from "../_lib/format";
import {
  ConstructorStandingsTable,
  DriverStandingsTable,
} from "../_components/tables";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SeasonSelector,
} from "../_components/ui";
export const metadata: Metadata = { title: "Standings" };
export default async function StandingsPage({ searchParams }: SearchPageProps) {
  const query = await searchParams;
  const { seasons, season } = await seasonContext(query);
  const constructors = single(query.view) === "constructors";
  const driverRows =
    season && !constructors ? await driverStandings(season.year) : [];
  const teamRows =
    season && constructors ? await constructorStandings(season.year) : [];
  const snapshotId = driverRows[0]?.event_id ?? teamRows[0]?.event_id;
  const [drivers, teams, snapshot] = await Promise.all([
    references<Driver>(
      "drivers",
      driverRows.map((row) => row.driver_id),
    ),
    references<Team>(
      "teams",
      teamRows.map((row) => row.team_id),
    ),
    snapshotId
      ? detail<RaceEvent>("events", snapshotId)
      : Promise.resolve(null),
  ]);
  const caption = snapshot
    ? `${season?.year} · Snapshot after round ${snapshot.round}, ${snapshot.name}`
    : "Latest imported championship snapshot";
  return (
    <>
      <PageHeading
        title="Championship standings."
        intro="Positions, points and wins from recorded championship snapshots."
      >
        <SeasonSelector
          seasons={seasons}
          selected={season}
          preserve={{ view: constructors ? "constructors" : "drivers" }}
        />
      </PageHeading>
      {!season ? (
        <NoSeason />
      ) : (
        <>
          <nav className="session-nav" aria-label="Championship category">
            <Link
              href={`/standings?season=${season.year}&view=drivers`}
              prefetch={false}
              aria-current={!constructors ? "page" : undefined}
            >
              Drivers
            </Link>
            <Link
              href={`/standings?season=${season.year}&view=constructors`}
              prefetch={false}
              aria-current={constructors ? "page" : undefined}
            >
              Constructors
            </Link>
          </nav>
          {driverRows.length ? (
            <DriverStandingsTable
              rows={driverRows}
              drivers={drivers}
              year={season.year}
              caption={caption}
            />
          ) : teamRows.length ? (
            <ConstructorStandingsTable
              rows={teamRows}
              teams={teams}
              caption={caption}
            />
          ) : (
            <EmptyState title="Standings not available">
              <p>
                No {constructors ? "constructor" : "driver"} championship
                snapshot has been imported for {season.year}. Choose another
                season or championship category.
              </p>
            </EmptyState>
          )}
          <p className="section-note">
            This is the latest imported snapshot for this category. Drivers or
            constructors without a source rank are shown as not ranked.
          </p>
        </>
      )}
    </>
  );
}
