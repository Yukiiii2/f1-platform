import Link from "next/link";
import type { ReactNode } from "react";
import type { Season, SessionStatus } from "../_lib/contracts";
import { statusNames } from "../_lib/contracts";
export function PageHeading({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {intro && <p className="intro">{intro}</p>}
      </div>
      {children}
    </div>
  );
}
export function SectionHeading({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <div className="muted">{children}</div>
    </div>
  );
}
export function NoSeason() {
  return (
    <EmptyState title="No race data for this season">
      <p>
        This season has no imported records. Choose another available season or
        return after race data has been added.
      </p>
      <Link href="/races" prefetch={false}>
        Browse available seasons
      </Link>
    </EmptyState>
  );
}
export function SeasonSelector({
  seasons,
  selected,
  preserve = {},
  action,
}: {
  seasons: Season[];
  selected: Season | null;
  preserve?: Record<string, string>;
  action?: string;
}) {
  if (!seasons.length) return null;
  return (
    <form className="filter-form" method="get" action={action}>
      {Object.entries(preserve).map(([key, value]) => (
        <input key={key} type="hidden" name={key} value={value} />
      ))}
      <div className="field">
        <label htmlFor="season">Season</label>
        <select
          key={selected?.year ?? "missing"}
          id="season"
          name="season"
          defaultValue={selected?.year ?? ""}
        >
          {!selected && (
            <option value="" disabled>
              Choose a season
            </option>
          )}
          {seasons
            .filter((season) => season.availability !== "unavailable")
            .map((season) => (
              <option key={season.id} value={season.year}>
                {season.year}
                {season.availability === "partial"
                  ? " · Partially imported"
                  : " · Imported"}
              </option>
            ))}
        </select>
      </div>
      <button type="submit" className="button button-quiet">
        View season
      </button>
      {selected?.availability === "partial" && (
        <p className="section-note">
          Partially imported season. Missing results or standings remain
          unavailable.
        </p>
      )}
    </form>
  );
}
export function Status({ value }: { value: SessionStatus }) {
  return (
    <span className={`session-status status-${value}`}>
      {statusNames[value]}
    </span>
  );
}
export function TableRegion({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="table-region" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
