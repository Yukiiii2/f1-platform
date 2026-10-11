import type { Metadata } from "next";
import Link from "next/link";
import type { SearchPageProps } from "../_lib/contracts";
import type { SavedComparison } from "../_lib/saved-comparison-contracts";
import { ApiError, getComparisonPage } from "../_lib/api";
import { single } from "../_lib/format";
import { accountState, sessionHeaders } from "../_lib/auth-api";
import { SignInRequired } from "../_components/sign-in-required";
import { EmptyState, PageHeading } from "../_components/ui";
import { ManageComparisons } from "./manage-comparisons";
import "./comparisons.css";

export const metadata: Metadata = { title: "Saved Comparisons" };
export default async function ComparisonsPage({
  searchParams,
}: SearchPageProps) {
  const query = await searchParams;
  const year = single(query.season);
  const offsetValue = single(query.offset) ?? "0";
  if (
    (year && (!/^\d{4}$/.test(year) || Number(year) < 1950)) ||
    !/^\d{1,7}$/.test(offsetValue)
  ) {
    return (
      <EmptyState title="Invalid saved-comparison filter">
        <Link href="/comparisons">View all saved comparisons</Link>
      </EmptyState>
    );
  }
  const offset = Number(offsetValue);
  const pageHref = (next: number) =>
    `/comparisons?${new URLSearchParams({ ...(year ? { season: year } : {}), offset: String(next) })}`;
  const account = await accountState();
  if (account.error)
    return (
      <EmptyState title="Account access temporarily unavailable">
        <p>Your saved selections are unchanged.</p>
        <a href={pageHref(offset)}>Retry</a>
      </EmptyState>
    );
  if (!account.user) return <SignInRequired next={pageHref(offset)} />;
  let rows: SavedComparison[] = [];
  let unavailable = false;
  try {
    rows = await getComparisonPage<SavedComparison>(
      {
        ...(year ? { season: year } : {}),
        offset,
      },
      await sessionHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    unavailable = true;
  }
  return (
    <>
      <PageHeading
        title="Saved Comparisons."
        intro="Return to recorded lap and strategy selections. Each comparison is recalculated from the data available when you open it."
      />
      <p className="section-note">
        Your saved comparisons
        {year ? ` · Season ${year}` : " · All seasons"}.{" "}
        {year && (
          <Link href="/comparisons" prefetch={false}>
            View all seasons
          </Link>
        )}
      </p>
      {unavailable ? (
        <EmptyState title="Saved comparisons temporarily unavailable">
          <p>
            Your saved selections have not been changed. Retry when race data is
            reachable.
          </p>
          <a className="button button-quiet" href={pageHref(offset)}>
            Retry saved comparisons
          </a>
        </EmptyState>
      ) : !rows.length ? (
        <EmptyState title="No saved comparisons here">
          <p>
            Open a lap pair in Telemetry Lab or compare two recorded driver
            strategies, then choose Save comparison.
          </p>
          <div className="saved-comparison-actions">
            <Link
              className="button button-quiet"
              href={`/telemetry${year ? `?season=${year}` : ""}`}
              prefetch={false}
            >
              Telemetry Lab
            </Link>
            <Link
              className="button button-quiet"
              href={`/strategy${year ? `?season=${year}` : ""}`}
              prefetch={false}
            >
              Strategy + Tyres
            </Link>
          </div>
        </EmptyState>
      ) : (
        <ManageComparisons rows={rows} />
      )}
      {!unavailable && (offset > 0 || rows.length === 50) && (
        <nav
          className="saved-comparison-actions"
          aria-label="Saved comparison pages"
        >
          {offset > 0 && (
            <Link
              className="button button-quiet"
              href={pageHref(Math.max(0, offset - 50))}
              prefetch={false}
            >
              Previous
            </Link>
          )}
          {rows.length === 50 && (
            <Link
              className="button button-quiet"
              href={pageHref(offset + 50)}
              prefetch={false}
            >
              Next
            </Link>
          )}
        </nav>
      )}
    </>
  );
}
