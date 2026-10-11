"use client";

import { useId, useState, useTransition } from "react";
import Link from "next/link";
import { authHref } from "../_lib/auth";
import { saveComparison } from "../comparisons/actions";
import { comparisonError } from "../_lib/saved-comparisons";
import type { Preset, SaveResult } from "../_lib/saved-comparison-contracts";

export function SaveComparison({
  preset,
  suggestedTitle,
  signedIn,
  returnTo,
  authUnavailable = false,
}: {
  preset: Preset;
  suggestedTitle: string;
  signedIn: boolean;
  returnTo: string;
  authUnavailable?: boolean;
}) {
  const id = useId();
  const [title, setTitle] = useState(suggestedTitle.slice(0, 120));
  const [result, setResult] = useState<SaveResult | null>(null);
  const [pending, startTransition] = useTransition();
  if (authUnavailable)
    return (
      <p className="section-note" role="status">
        Account access is temporarily unavailable. Your analysis selections are
        unchanged.
      </p>
    );
  if (!signedIn)
    return (
      <p className="section-note">
        <Link href={authHref("sign-in", returnTo)} prefetch={false}>
          Sign in to save this comparison
        </Link>
      </p>
    );
  return (
    <details className="save-comparison">
      <summary>Save comparison</summary>
      <form
        className="filter-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (pending) return;
          startTransition(async () => {
            try {
              setResult(
                await saveComparison({ ...preset, title: title.trim() }),
              );
            } catch {
              setResult({ error: comparisonError(503) });
            }
          });
        }}
      >
        <div className="field">
          <label htmlFor={id}>Comparison title</label>
          <input
            id={id}
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
          {pending ? "Saving…" : "Save comparison"}
        </button>
      </form>
      <p className="section-note">
        Saves these selections to your account. Analysis is recalculated from
        recorded data when reopened.
      </p>
      <div role="status" aria-live="polite">
        {result?.error && <p>{result.error}</p>}
        {result?.signInRequired && (
          <Link href={authHref("sign-in", returnTo)} prefetch={false}>
            Sign in to save this comparison
          </Link>
        )}
        {result?.response && (
          <p>
            Comparison saved.{" "}
            <Link
              href={`/comparisons?season=${preset.configuration.season}`}
              prefetch={false}
            >
              View Saved Comparisons
            </Link>
          </p>
        )}
      </div>
    </details>
  );
}
