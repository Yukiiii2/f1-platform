import type { Metadata } from "next";
import Link from "next/link";
import { PageHeading, SectionHeading } from "../_components/ui";
import "./pitwall.css";

export const metadata: Metadata = { title: "Pitwall" };
export default function PitwallPage() {
  return (
    <>
      <PageHeading
        title="Pitwall."
        intro="Ask about the race data you are exploring. Open a page, choose your context, then ask Pitwall for analysis."
      />
      <section aria-label="Choose an analysis context">
        <SectionHeading title="Start with the records" />
        <ul className="pitwall-entry-list">
          <li>
            <Link href="/races" prefetch={false}>
              <span className="pitwall-entry-title">Race weekends</span>
              <p>
                Results, recorded session conditions and championship context.
              </p>
              <span className="pitwall-entry-action">Choose a weekend</span>
            </Link>
          </li>
          <li>
            <Link href="/drivers" prefetch={false}>
              <span className="pitwall-entry-title">Driver profiles</span>
              <p>
                A driver’s recorded results in the season and weekend you
                select.
              </p>
              <span className="pitwall-entry-action">Choose a driver</span>
            </Link>
          </li>
          <li>
            <Link href="/telemetry" prefetch={false}>
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
            <Link href="/strategy" prefetch={false}>
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
