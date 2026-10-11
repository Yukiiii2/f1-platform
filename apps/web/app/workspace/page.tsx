import Link from "next/link";
import { ApiError, workspaceRequest, getComparisonPage } from "../_lib/api";
import { accountState, sessionHeaders } from "../_lib/auth-api";
import type { SearchPageProps } from "../_lib/contracts";
import type { SavedComparison } from "../_lib/saved-comparison-contracts";
import {
  workspaceDate,
  type Collection,
  type WorkspaceReference,
} from "../_lib/workspace";
import { SignInRequired } from "../_components/sign-in-required";
import { PageHeading, EmptyState } from "../_components/ui";
import { CreateCollection, ReferenceList } from "./workspace-controls";
import "./workspace.css";

export const metadata = { title: "Workspace" };
export default async function WorkspacePage({ searchParams }: SearchPageProps) {
  const query = await searchParams;
  const value = (key: string) =>
    typeof query[key] === "string" ? (query[key] as string) : undefined;
  const year = value("season");
  const offsets = ["collections", "drivers", "weekends"].map(
    (key) => value(key) ?? "0",
  );
  if (
    (year && !/^\d{4}$/.test(year)) ||
    offsets.some((v) => !/^\d{1,7}$/.test(v) || Number(v) > 1000000)
  )
    return (
      <EmptyState title="Invalid workspace page">
        <Link href="/workspace">Open your workspace</Link>
      </EmptyState>
    );
  const href = (key?: string, offset?: number) => {
    const params = new URLSearchParams({
      ...(year ? { season: year } : {}),
      ...Object.fromEntries(
        ["collections", "drivers", "weekends"].map((k, i) => [k, offsets[i]]),
      ),
    });
    if (key && offset !== undefined) params.set(key, String(offset));
    return `/workspace?${params}`;
  };
  const account = await accountState();
  if (account.error)
    return (
      <EmptyState title="Workspace temporarily unavailable">
        <p>Your private material is unchanged.</p>
        <a href={href()}>Retry</a>
      </EmptyState>
    );
  if (!account.user)
    return (
      <SignInRequired next={href()} title="Sign in to open your workspace" />
    );
  let collections: Collection[],
    drivers: WorkspaceReference[],
    weekends: WorkspaceReference[],
    comparisons: SavedComparison[];
  try {
    const headers = await sessionHeaders();
    [collections, drivers, weekends, comparisons] = await Promise.all([
      workspaceRequest<Collection[]>(
        "collections",
        "GET",
        undefined,
        { limit: 50, offset: Number(offsets[0]) },
        headers,
      ),
      workspaceRequest<WorkspaceReference[]>(
        "favorites",
        "GET",
        undefined,
        { reference_type: "driver", limit: 50, offset: Number(offsets[1]) },
        headers,
      ),
      workspaceRequest<WorkspaceReference[]>(
        "favorites",
        "GET",
        undefined,
        { reference_type: "event", limit: 50, offset: Number(offsets[2]) },
        headers,
      ),
      getComparisonPage<SavedComparison>({ limit: 50 }, headers),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401)
      return (
        <SignInRequired
          next={href()}
          title="Sign in again to open your workspace"
        />
      );
    return (
      <EmptyState title="Workspace temporarily unavailable">
        <p>Your private material is unchanged.</p>
        <a href={href()}>Retry workspace</a>
      </EmptyState>
    );
  }
  const pages = (key: string, i: number, length: number) => (
    <nav className="workspace-actions" aria-label={`${key} pages`}>
      {Number(offsets[i]) > 0 && (
        <Link
          href={href(key, Math.max(0, Number(offsets[i]) - 50))}
          prefetch={false}
        >
          Previous
        </Link>
      )}
      {length === 50 && (
        <Link href={href(key, Number(offsets[i]) + 50)} prefetch={false}>
          Next
        </Link>
      )}
    </nav>
  );
  return (
    <>
      <PageHeading
        title="Workspace."
        intro="Your private collection of recorded race analysis. Public source data stays shared; saved comparisons recalculate when opened."
      />
      <nav className="workspace-actions" aria-label="Workspace navigation">
        <Link
          href={`/comparisons${year ? `?season=${year}` : ""}`}
          prefetch={false}
        >
          Manage Saved Comparisons
        </Link>
        <Link
          href={`/account${year ? `?season=${year}` : ""}`}
          prefetch={false}
        >
          Account settings
        </Link>
      </nav>
      <section className="workspace-section">
        <h2>Saved comparisons</h2>
        <p className="section-note">
          Your five most recently updated presets across all seasons.
        </p>
        {comparisons.length ? (
          <ul className="workspace-list">
            {comparisons.slice(0, 5).map((row) => (
              <li key={row.id}>
                <div>
                  <strong>{row.title}</strong>
                  <p className="section-note">
                    {row.configuration.season} ·{" "}
                    {row.event_name ?? "Weekend unavailable"} ·{" "}
                    {row.availability}
                  </p>
                  <p className="section-note">
                    Updated{" "}
                    <time dateTime={row.updated_at}>
                      {workspaceDate(row.updated_at)}
                    </time>
                  </p>
                </div>
                <div className="workspace-actions">
                  {row.open_url && (
                    <Link
                      href={`/comparisons/${row.id}/open?season=${row.configuration.season}`}
                      prefetch={false}
                    >
                      Open comparison
                    </Link>
                  )}
                  <Link
                    href={`/comparisons?season=${row.configuration.season}`}
                    prefetch={false}
                  >
                    Manage comparison
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>
            No saved comparisons yet. Save a lap pair in{" "}
            <Link href={`/telemetry${year ? `?season=${year}` : ""}`}>
              Telemetry Lab
            </Link>{" "}
            or a driver pair in{" "}
            <Link href={`/strategy${year ? `?season=${year}` : ""}`}>
              Strategy + Tyres
            </Link>
            .
          </p>
        )}
      </section>
      <section className="workspace-section">
        <h2>Collections</h2>
        <CreateCollection returnTo={href()} />
        {collections.length ? (
          <ul className="workspace-list">
            {collections.map((row) => (
              <li key={row.id}>
                <div>
                  <Link
                    href={`/collections/${row.id}${year ? `?season=${year}` : ""}`}
                    prefetch={false}
                  >
                    {row.title}
                  </Link>
                  <p>{row.description}</p>
                  <p className="section-note">
                    {row.item_count} items · Updated{" "}
                    <time dateTime={row.updated_at}>
                      {workspaceDate(row.updated_at)}
                    </time>
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>
            No collections yet. Create one, then add weekends, drivers, sessions
            or saved comparisons from their pages.
          </p>
        )}
        {pages("collections", 0, collections.length)}
      </section>
      <section className="workspace-section">
        <h2>Favorite drivers</h2>
        {drivers.length ? (
          <ReferenceList rows={drivers} returnTo={href()} />
        ) : (
          <p>
            No favorite drivers yet.{" "}
            <Link href={`/drivers${year ? `?season=${year}` : ""}`}>
              Browse drivers
            </Link>{" "}
            and choose Favorite driver.
          </p>
        )}
        {pages("drivers", 1, drivers.length)}
      </section>
      <section className="workspace-section">
        <h2>Favorite race weekends</h2>
        {weekends.length ? (
          <ReferenceList rows={weekends} returnTo={href()} />
        ) : (
          <p>
            No favorite weekends yet.{" "}
            <Link href={`/races${year ? `?season=${year}` : ""}`}>
              Browse race weekends
            </Link>{" "}
            and choose Favorite weekend.
          </p>
        )}
        {pages("weekends", 2, weekends.length)}
      </section>
    </>
  );
}
