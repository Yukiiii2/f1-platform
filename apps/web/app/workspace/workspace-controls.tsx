"use client";
import Link from "next/link";
import { useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { mutateWorkspace } from "./actions";
import { WorkspaceFeedback } from "../_components/reference-controls";
import {
  workspaceDate,
  workspaceRoute,
  workspaceError,
  referenceLabels,
  type Collection,
  type WorkspaceReference,
  type WorkspaceResult,
} from "../_lib/workspace";

export function CreateCollection({
  returnTo = "/workspace",
}: { returnTo?: string } = {}) {
  const id = useId();
  const router = useRouter();
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [pending, startTransition] = useTransition();
  return (
    <details className="workspace-editor">
      <summary>Create collection</summary>
      <form
        className="account-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (pending) return;
          const form = e.currentTarget,
            data = new FormData(form);
          startTransition(async () => {
            try {
              const response = await mutateWorkspace("create", {
                title: String(data.get("title")),
                description: String(data.get("description")),
              });
              if (response.success && response.response) {
                form.reset();
                router.push(
                  workspaceRoute(
                    `/collections/${response.response.id}`,
                    returnTo,
                  ),
                );
                router.refresh();
              } else setResult(response);
            } catch {
              setResult({ error: workspaceError() });
            }
          });
        }}
      >
        <div className="field">
          <label htmlFor={`${id}-title`}>Collection title</label>
          <input
            id={`${id}-title`}
            name="title"
            required
            maxLength={120}
            disabled={pending}
          />
        </div>
        <div className="field">
          <label htmlFor={`${id}-description`}>Description (optional)</label>
          <textarea
            id={`${id}-description`}
            name="description"
            maxLength={1000}
            rows={3}
            disabled={pending}
          />
        </div>
        <button className="button" disabled={pending} type="submit">
          {pending ? "Creating…" : "Create collection"}
        </button>
        <WorkspaceFeedback result={result} returnTo={returnTo} />
      </form>
    </details>
  );
}

export function EditCollection({
  collection,
  returnTo = `/collections/${collection.id}`,
}: {
  collection: Collection;
  returnTo?: string;
}) {
  const id = useId();
  const router = useRouter();
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [pending, startTransition] = useTransition();
  return (
    <div className="workspace-editor">
      <details>
        <summary>Edit collection</summary>
        <form
          className="account-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (pending) return;
            const data = new FormData(e.currentTarget);
            startTransition(async () => {
              try {
                const response = await mutateWorkspace("update", {
                  id: collection.id,
                  title: String(data.get("title")),
                  description: String(data.get("description")),
                });
                setResult(response);
                if (response.success) router.refresh();
              } catch {
                setResult({ error: workspaceError() });
              }
            });
          }}
        >
          <div className="field">
            <label htmlFor={`${id}-title`}>Collection title</label>
            <input
              id={`${id}-title`}
              name="title"
              defaultValue={collection.title}
              required
              maxLength={120}
              disabled={pending}
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-description`}>Description (optional)</label>
            <textarea
              id={`${id}-description`}
              name="description"
              defaultValue={collection.description ?? ""}
              maxLength={1000}
              rows={3}
              disabled={pending}
            />
          </div>
          <button
            type="submit"
            className="button button-quiet"
            disabled={pending}
          >
            {pending ? "Saving…" : "Save collection"}
          </button>
        </form>
      </details>
      <button
        type="button"
        className="button button-quiet"
        disabled={pending}
        onClick={() => setConfirming(!confirming)}
      >
        Delete collection
      </button>
      {confirming && (
        <div>
          <p>
            Delete “{collection.title}” and its item references? Saved
            comparisons and public race data will be preserved.
          </p>
          <div className="workspace-actions">
            <button
              className="button button-quiet"
              disabled={pending}
              onClick={() =>
                startTransition(async () => {
                  try {
                    const response = await mutateWorkspace("delete", {
                      id: collection.id,
                    });
                    if (response.success) {
                      router.replace(workspaceRoute("/workspace", returnTo));
                      router.refresh();
                    } else setResult(response);
                  } catch {
                    setResult({ error: workspaceError() });
                  }
                })
              }
            >
              {pending ? "Deleting…" : "Confirm delete"}
            </button>
            <button
              className="button button-quiet"
              disabled={pending}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      <WorkspaceFeedback result={result} returnTo={returnTo} />
    </div>
  );
}

export function ReferenceList({
  rows,
  collectionId,
  returnTo = collectionId ? `/collections/${collectionId}` : "/workspace",
}: {
  rows: WorkspaceReference[];
  collectionId?: string;
  returnTo?: string;
}) {
  const router = useRouter();
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [pending, startTransition] = useTransition();
  return (
    <>
      <ul className="workspace-list">
        {rows.map((row) => (
          <li key={row.id}>
            <div>
              <strong>{row.label}</strong>
              <p className="section-note">
                {referenceLabels[row.reference_type]} · {row.season}
                {row.availability !== "available"
                  ? ` · ${row.availability === "partial" ? "Partial data" : "Unavailable"}`
                  : ""}
              </p>
              {row.notices.map((notice) => (
                <p className="section-note" key={notice}>
                  {notice}
                </p>
              ))}
              <p className="section-note">
                Saved{" "}
                <time dateTime={row.created_at}>
                  {workspaceDate(row.created_at)}
                </time>
              </p>
            </div>
            <div className="workspace-actions">
              {row.open_url && (
                <Link
                  className="button button-quiet"
                  href={row.open_url}
                  prefetch={false}
                >
                  Open<span className="sr-only"> {row.label}</span>
                </Link>
              )}
              <button
                type="button"
                className="button button-quiet"
                disabled={pending}
                onClick={() => {
                  if (pending) return;
                  startTransition(async () => {
                    try {
                      const response = await mutateWorkspace(
                        collectionId ? "remove" : "unfavorite",
                        collectionId
                          ? { id: collectionId, item_id: row.id }
                          : { id: row.id },
                      );
                      if (response.success) {
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
                  ? "Removing…"
                  : collectionId
                    ? "Remove from collection"
                    : "Unfavorite"}
                <span className="sr-only"> {row.label}</span>
              </button>
            </div>
          </li>
        ))}
      </ul>
      <WorkspaceFeedback result={result} returnTo={returnTo} />
    </>
  );
}
