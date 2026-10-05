import type { Metadata } from "next";
import type { Circuit, SearchPageProps } from "../_lib/contracts";
import { references, seasonContext, seasonEvents } from "../_lib/data";
import { EventTable } from "../_components/tables";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SeasonSelector,
} from "../_components/ui";
export const metadata: Metadata = { title: "Races" };
export default async function RacesPage({ searchParams }: SearchPageProps) {
  const { seasons, season } = await seasonContext(await searchParams);
  const events = season ? await seasonEvents(season.year) : [];
  const circuits = await references<Circuit>(
    "circuits",
    events.map((event) => event.circuit_id),
  );
  return (
    <>
      <PageHeading
        title="Race weekends."
        intro="The calendar, the sessions, the classification."
      >
        <SeasonSelector seasons={seasons} selected={season} />
      </PageHeading>
      {!season ? (
        <NoSeason />
      ) : events.length ? (
        <>
          <p className="section-note">
            {events.length} recorded weekends in {season.year}. Dates without
            source times remain date-only.
          </p>
          <EventTable events={events} circuits={circuits} />
        </>
      ) : (
        <EmptyState title="No race weekends yet">
          <p>
            The {season.year} calendar has not been imported. Choose another
            season or check back after data has been added.
          </p>
        </EmptyState>
      )}
    </>
  );
}
