import type { Metadata } from "next";
import Link from "next/link";
import {
  NoSeason,
  PageHeading,
  SectionHeading,
  SeasonSelector,
} from "../_components/ui";
import { seasonContext } from "../_lib/data";
import { seasonHref, single } from "../_lib/format";
import type { SearchPageProps } from "../_lib/contracts";
import "./pitwall.css";

export const metadata: Metadata = { title: "Pitwall" };
export default async function PitwallPage({ searchParams }: SearchPageProps) {
  const query = await searchParams;
  const { seasons, season } = await seasonContext(query);
  const requested = single(query.season);
  const year =
    season?.year ??
    (requested && /^\d{4}$/.test(requested) && Number(requested) >= 1950
      ? Number(requested)
      : undefined);
  return (
    <>
      <PageHeading
        title="Pitwall."
        intro="Ask about the race data you are exploring. Open a page, choose your context, then ask Pitwall for analysis."
      >
        <SeasonSelector seasons={seasons} selected={season} />
      </PageHeading>
      {!season && <NoSeason />}
      <section aria-label="Choose an analysis context">
        <SectionHeading title="Start with the records" />
        <ul className="pitwall-entry-list">
          <li>
            <Link href={seasonHref("/races", year)} prefetch={false}>
              <span className="pitwall-entry-title">Race weekends</span>
              <p>
                Results, recorded session conditions and championship context.
              </p>
              <span className="pitwall-entry-action">Choose a weekend</span>
            </Link>
          </li>
          <li>
            <Link href={seasonHref("/drivers", year)} prefetch={false}>
              <span className="pitwall-entry-title">Driver profiles</span>
              <p>
                A driver’s recorded results in the season and weekend you
                select.
              </p>
              <span className="pitwall-entry-action">Choose a driver</span>
            </Link>
          </li>
          <li>
            <Link href={seasonHref("/telemetry", year)} prefetch={false}>
              <span className="pitwall-entry-title">Telemetry Lab</span>
              <p>
                Select a session and check its recorded laps and channels before
                asking about a comparison.
              </p>
              <span className="pitwall-entry-action">
                Choose a session and laps
              </span>
            </Link>
          </li>
          <li>
            <Link href={seasonHref("/strategy", year)} prefetch={false}>
              <span className="pitwall-entry-title">Strategy + Tyres</span>
              <p>
                Recorded stint sequence, pit timing, tyre age and observed pace.
              </p>
              <span className="pitwall-entry-action">
                Choose a race and drivers
              </span>
            </Link>
          </li>
        </ul>
        <p className="section-note">
          Every answer separates source data, calculations and interpretation.
          Missing records remain unavailable. Analysis cannot confirm team
          intent.
        </p>
      </section>
    </>
  );
}
