"use client";

import { useId, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { SavedComparison } from "../_lib/saved-comparison-contracts";
import { renameComparison, deleteComparison } from "./actions";
import { comparisonError } from "../_lib/saved-comparisons";
import { AddToCollection } from "../_components/reference-controls";

const labels = {
  telemetry_laps: "Telemetry lap comparison",
  strategy_tyres: "Strategy and tyres",
};
function SavedRow({ row }: { row: SavedComparison }) {
  const router = useRouter();
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [title, setTitle] = useState(row.title);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const date = (value: string) =>
    new Date(value).toLocaleString("en-GB", {
      timeZone: "UTC",
      dateStyle: "medium",
      timeStyle: "short",
    });
  return (
    <li className="saved-comparison-row">
      <article aria-labelledby={id}>
        <div className="saved-comparison-heading">
          <h2 id={id}>{row.title}</h2>
          <span className="muted">
            {row.availability === "available"
              ? "Selections available"
              : row.availability === "partial"
                ? "Partial data"
                : "Unavailable"}
          </span>
        </div>
        <p>
          {labels[row.comparison_type]} · {row.configuration.season} ·{" "}
          {row.event_name ?? "Weekend unavailable"} ·{" "}
          {row.session_name ?? "Session unavailable"}
        </p>
        <p className="muted">
          {row.driver_a_name ?? "Driver A unavailable"}
          {row.lap_a_number !== null && ` · Lap ${row.lap_a_number}`} /{" "}
          {row.driver_b_name ?? "Driver B unavailable"}
          {row.lap_b_number !== null && ` · Lap ${row.lap_b_number}`}
        </p>
        {row.notices.map((notice) => (
          <p className="section-note" key={notice}>
            {notice}
          </p>
        ))}
        <p className="saved-comparison-dates muted">
          Created{" "}
          <time dateTime={row.created_at}>{date(row.created_at)} UTC</time> ·
          Updated{" "}
          <time dateTime={row.updated_at}>{date(row.updated_at)} UTC</time>
        </p>
        <div className="saved-comparison-actions">
          {row.open_url && row.availability !== "unavailable" && (
            <Link
              className="button"
              href={`/comparisons/${row.id}/open?season=${row.configuration.season}`}
              prefetch={false}
            >
              Open
            </Link>
          )}
          <button
            className="button button-quiet"
            disabled={pending}
            onClick={() => {
              setEditing(!editing);
              setConfirming(false);
              setError(null);
            }}
          >
            Rename<span className="sr-only"> {row.title}</span>
          </button>
          <button
            className="button button-quiet"
            disabled={pending}
            onClick={() => {
              setConfirming(!confirming);
              setEditing(false);
              setError(null);
            }}
          >
            Delete<span className="sr-only"> {row.title}</span>
          </button>
        </div>
        {editing && (
          <form
            className="filter-form saved-comparison-edit"
            onSubmit={(event) => {
              event.preventDefault();
              if (pending) return;
              startTransition(async () => {
                try {
                  const result = await renameComparison(row.id, title.trim());
                  if (result.error) setError(result.error);
                  else {
                    setEditing(false);
                    setError(null);
                    router.refresh();
                  }
                } catch {
                  setError(comparisonError(503));
                }
              });
            }}
          >
            <div className="field">
              <label htmlFor={`${id}-title`}>Comparison title</label>
              <input
                id={`${id}-title`}
                value={title}
                maxLength={120}
                required
                disabled={pending}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
            <button
              className="button button-quiet"
              type="submit"
              disabled={pending || !title.trim()}
            >
              {pending ? "Renaming…" : "Save title"}
            </button>
            <button
              className="button button-quiet"
              type="button"
              disabled={pending}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </form>
        )}
        {confirming && (
          <div className="saved-comparison-delete">
            <p>Delete “{row.title}”? Recorded race data will be preserved.</p>
            <div className="saved-comparison-actions">
              <button
                className="button button-quiet"
                disabled={pending}
                onClick={() => {
                  if (pending) return;
                  startTransition(async () => {
                    try {
                      const result = await deleteComparison(row.id);
                      if (result.error) setError(result.error);
                      else {
                        setConfirming(false);
                        setError(null);
                        router.refresh();
                      }
                    } catch {
                      setError(comparisonError(503));
                    }
                  });
                }}
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
        <div role="status" aria-live="polite">
          {error && <p>{error}</p>}
        </div>
        <AddToCollection
          reference={{
            reference_type: "comparison",
            reference_id: row.id,
            season: row.configuration.season,
          }}
          returnTo={`/comparisons?season=${row.configuration.season}`}
        />
      </article>
    </li>
  );
}
export function ManageComparisons({ rows }: { rows: SavedComparison[] }) {
  return (
    <ul className="saved-comparison-list">
      {rows.map((row) => (
        <SavedRow key={`${row.id}:${row.updated_at}`} row={row} />
      ))}
    </ul>
  );
}
