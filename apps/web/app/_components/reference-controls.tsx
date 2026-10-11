"use client";
import "../workspace/workspace.css";
import Link from "next/link";
import { useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { authHref } from "../_lib/auth";
import { collectionOptions, mutateWorkspace } from "../workspace/actions";
import {
  workspaceError,
  type ReferenceInput,
  type WorkspaceReference,
  type Collection,
  type WorkspaceResult,
} from "../_lib/workspace";

export function WorkspaceFeedback({
  result,
  returnTo,
}: {
  result: WorkspaceResult | null;
  returnTo: string;
}) {
  return (
    <div role="status" aria-live="polite">
      {result?.error && (
        <p>
          {result.error}{" "}
          {result.signInRequired && (
            <Link href={authHref("sign-in", returnTo)} prefetch={false}>
              Sign in again
            </Link>
          )}
        </p>
      )}
      {result?.success && <p>Saved to your workspace.</p>}
    </div>
  );
}
export function AddToCollection({
  reference,
  returnTo,
}: {
  reference: ReferenceInput;
  returnTo: string;
}) {
  const id = useId();
  const [rows, setRows] = useState<Collection[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [pending, startTransition] = useTransition();
  function loadMore() {
    if (pending) return;
    startTransition(async () => {
      try {
        const response = await collectionOptions(rows?.length ?? 0);
        if (response.error) setResult(response);
        else {
          setRows((old) => [
            ...(old ?? []),
            ...(response.rows ?? []).filter(
              (r) => !old?.some((o) => o.id === r.id),
            ),
          ]);
          setHasMore(response.rows?.length === 50);
          setResult(null);
        }
      } catch {
        setResult({ error: workspaceError() });
      }
    });
  }
  return (
    <details
      className="collection-picker"
      onToggle={(e) => {
        if (e.currentTarget.open && rows === null) loadMore();
      }}
    >
      <summary>Add to collection</summary>
      {rows?.length ? (
        <form
          className="filter-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (pending) return;
            const collectionId = String(
              new FormData(e.currentTarget).get("collection"),
            );
            startTransition(async () => {
              try {
                setResult(
                  await mutateWorkspace("add", { id: collectionId, reference }),
                );
              } catch {
                setResult({ error: workspaceError() });
              }
            });
          }}
        >
          <div className="field">
            <label htmlFor={id}>Collection</label>
            <select id={id} name="collection" required disabled={pending}>
              {rows.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.title}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="button button-quiet"
            disabled={pending}
          >
            {pending ? "Saving…" : "Add item"}
          </button>
        </form>
      ) : (
        rows && (
          <p>
            No collections yet.{" "}
            <Link
              href={`/workspace?season=${reference.season}`}
              prefetch={false}
            >
              Create a collection in your workspace
            </Link>
            , then return to add this reference.
          </p>
        )
      )}
      {(hasMore || rows === null) && (
        <button
          className="button button-quiet"
          type="button"
          disabled={pending}
          onClick={loadMore}
        >
          {pending
            ? "Loading collections…"
            : rows === null
              ? "Retry loading collections"
              : "Load more collections"}
        </button>
      )}
      <WorkspaceFeedback result={result} returnTo={returnTo} />
    </details>
  );
}

export function ReferenceControls({
  reference,
  returnTo,
  initialFavorite,
  favoriteUnavailable = false,
}: {
  reference: ReferenceInput;
  returnTo: string;
  initialFavorite?: WorkspaceReference;
  favoriteUnavailable?: boolean;
}) {
  const router = useRouter();
  const [favorite, setFavorite] = useState(initialFavorite);
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [pending, startTransition] = useTransition();
  const noun = reference.reference_type === "event" ? "weekend" : "driver";
  return (
    <div className="private-reference-actions">
      {["event", "driver"].includes(reference.reference_type) && (
        <button
          className="button button-quiet"
          type="button"
          disabled={pending || favoriteUnavailable}
          aria-pressed={Boolean(favorite)}
          onClick={() => {
            if (pending) return;
            startTransition(async () => {
              try {
                const response = await mutateWorkspace(
                  favorite ? "unfavorite" : "favorite",
                  favorite ? { id: favorite.id } : { reference },
                );
                if (response.success) {
                  setFavorite(
                    favorite
                      ? undefined
                      : (response.response as WorkspaceReference),
                  );
                  setResult(null);
                  router.refresh();
                } else setResult(response);
              } catch {
                setResult({ error: workspaceError() });
              }
            });
          }}
        >
          {pending
            ? "Saving…"
            : favorite
              ? `Unfavorite ${noun}`
              : `Favorite ${noun}`}
        </button>
      )}
      {favoriteUnavailable && (
        <p className="section-note">
          Favorite status is temporarily unavailable. Reload to retry.
        </p>
      )}
      <AddToCollection reference={reference} returnTo={returnTo} />
      <WorkspaceFeedback result={result} returnTo={returnTo} />
    </div>
  );
}
