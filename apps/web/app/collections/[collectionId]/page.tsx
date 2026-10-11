import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, workspaceRequest } from "../../_lib/api";
import { accountState, sessionHeaders } from "../../_lib/auth-api";
import type { SearchParams } from "../../_lib/contracts";
import type { CollectionDetail } from "../../_lib/workspace";
import { SignInRequired } from "../../_components/sign-in-required";
import { PageHeading, EmptyState } from "../../_components/ui";
import {
  EditCollection,
  ReferenceList,
} from "../../workspace/workspace-controls";
import "../../workspace/workspace.css";

export const metadata = { title: "Collection" };
export default async function CollectionPage({
  params,
  searchParams,
}: {
  params: Promise<{ collectionId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ collectionId }, query] = await Promise.all([params, searchParams]);
  const year =
    typeof query.season === "string" && /^\d{4}$/.test(query.season)
      ? query.season
      : undefined;
  const offset = typeof query.offset === "string" ? query.offset : "0";
  const href = (next = Number(offset)) =>
    `/collections/${collectionId}?${new URLSearchParams({ ...(year ? { season: year } : {}), offset: String(next) })}`;
  if (!/^\d{1,7}$/.test(offset) || Number(offset) > 1000000)
    return (
      <EmptyState title="Invalid collection page">
        <Link href={href(0)}>Open collection</Link>
      </EmptyState>
    );
  const account = await accountState();
  if (account.error)
    return (
      <EmptyState title="Collection temporarily unavailable">
        <a href={href()}>Retry</a>
      </EmptyState>
    );
  if (!account.user)
    return (
      <SignInRequired next={href()} title="Sign in to open your collection" />
    );
  let collection: CollectionDetail;
  try {
    collection = await workspaceRequest<CollectionDetail>(
      `collections/${collectionId}`,
      "GET",
      undefined,
      { limit: 50, offset: Number(offset) },
      await sessionHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) notFound();
    if (error.status === 401)
      return (
        <SignInRequired
          next={href()}
          title="Sign in again to open your collection"
        />
      );
    return (
      <EmptyState title="Collection temporarily unavailable">
        <p>Your collection is unchanged.</p>
        <a href={href()}>Retry collection</a>
      </EmptyState>
    );
  }
  return (
    <>
      <Link
        className="back-link"
        href={`/workspace${year ? `?season=${year}` : ""}`}
        prefetch={false}
      >
        Back to workspace
      </Link>
      <PageHeading
        title={collection.title}
        intro={collection.description ?? "Your private analysis references."}
      />
      <p className="section-note">
        {collection.item_count} items · Only you can view or edit this
        collection.
      </p>
      <EditCollection
        key={collection.updated_at}
        collection={collection}
        returnTo={href()}
      />
      {collection.items.length ? (
        <ReferenceList
          rows={collection.items}
          collectionId={collection.id}
          returnTo={href()}
        />
      ) : (
        <EmptyState title="No items in this view">
          <p>
            Add material from race weekends, driver pages, recorded sessions or
            Saved Comparisons.
          </p>
        </EmptyState>
      )}
      <nav className="workspace-actions" aria-label="Collection item pages">
        {Number(offset) > 0 && (
          <Link href={href(Math.max(0, Number(offset) - 50))}>Previous</Link>
        )}
        {collection.items.length === 50 && (
          <Link href={href(Number(offset) + 50)}>Next</Link>
        )}
      </nav>
    </>
  );
}
