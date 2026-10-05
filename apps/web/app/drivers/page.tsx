import type { Metadata } from "next";
import Link from "next/link";
import type { Driver, SearchPageProps } from "../_lib/contracts";
import { getList } from "../_lib/api";
import { driverName, single } from "../_lib/format";
import { EmptyState, PageHeading } from "../_components/ui";
export const metadata: Metadata = { title: "Drivers" };
export default async function DriversPage({ searchParams }: SearchPageProps) {
  const [drivers, params] = await Promise.all([
    getList<Driver>("drivers"),
    searchParams,
  ]);
  const query = (single(params.q) ?? "").trim();
  const visible = drivers
    .filter((driver) =>
      `${driverName(driver)} ${driver.code ?? ""}`
        .toLocaleLowerCase("en")
        .includes(query.toLocaleLowerCase("en")),
    )
    .sort(
      (a, b) =>
        a.family_name.localeCompare(b.family_name, "en") ||
        a.given_name.localeCompare(b.given_name, "en"),
    );
  return (
    <>
      <PageHeading
        title="The drivers."
        intro="Explore the drivers recorded across available seasons."
      />
      <form method="get" className="search-form">
        <div className="field">
          <label htmlFor="driver-search">Find a driver</label>
          <input
            key={query}
            id="driver-search"
            type="search"
            name="q"
            placeholder="Name or driver code"
            defaultValue={query}
            maxLength={100}
          />
        </div>
        <button className="button button-quiet" type="submit">
          Search
        </button>
        {query && (
          <Link href="/drivers" prefetch={false}>
            Clear search
          </Link>
        )}
      </form>
      {visible.length ? (
        <>
          <p className="section-note">
            {visible.length} {visible.length === 1 ? "driver" : "drivers"}
            {query ? ` matching “${query}”` : " in the directory"}.
          </p>
          <ul className="driver-list">
            {visible.map((driver) => (
              <li key={driver.id}>
                <div
                  className="driver-number"
                  aria-label={
                    driver.permanent_number !== null
                      ? `Permanent number ${driver.permanent_number}`
                      : "Permanent number unavailable"
                  }
                >
                  {driver.permanent_number ?? "—"}
                </div>
                <div>
                  <h2>
                    <Link href={`/drivers/${driver.id}`} prefetch={false}>
                      {driverName(driver)}
                    </Link>
                  </h2>
                  <p>
                    {driver.nationality ?? "Nationality unavailable"}
                    {driver.code && ` · ${driver.code}`}
                  </p>
                </div>
                <Link
                  className="profile-link"
                  href={`/drivers/${driver.id}`}
                  prefetch={false}
                  aria-label={`View ${driverName(driver)} profile`}
                >
                  View profile
                </Link>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <EmptyState
          title={query ? "No matching drivers" : "No drivers available"}
        >
          <p>
            {query
              ? "Try a different name or driver code."
              : "No driver records have been imported yet. Return after race data has been added."}
          </p>
          {query && (
            <Link href="/drivers" prefetch={false}>
              Show all drivers
            </Link>
          )}
        </EmptyState>
      )}
    </>
  );
}
