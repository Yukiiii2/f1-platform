import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiError, getSavedComparison } from "../../../_lib/api";
import type { SavedComparison } from "../../../_lib/saved-comparison-contracts";
import { EmptyState } from "../../../_components/ui";
import { sessionHeaders } from "../../../_lib/auth-api";
import { SignInRequired } from "../../../_components/sign-in-required";

export default async function OpenComparison({
  params,
}: {
  params: Promise<{ comparisonId: string }>;
}) {
  const { comparisonId } = await params;
  let row: SavedComparison;
  try {
    row = await getSavedComparison<SavedComparison>(
      comparisonId,
      await sessionHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401)
      return <SignInRequired next={`/comparisons/${comparisonId}/open`} />;
    return (
      <EmptyState
        title={
          error.status === 404
            ? "Saved comparison not found"
            : "Saved comparison temporarily unavailable"
        }
      >
        <p>
          Return to Saved Comparisons and retry. Your recorded race data is
          unchanged.
        </p>
        <Link href="/comparisons" prefetch={false}>
          Saved Comparisons
        </Link>
      </EmptyState>
    );
  }
  if (row.availability !== "unavailable" && row.open_url)
    redirect(row.open_url);
  return (
    <EmptyState title="Saved comparison unavailable">
      {row.notices.map((notice) => (
        <p key={notice}>{notice}</p>
      ))}
      <p>No replacement driver, lap or session has been selected.</p>
      <Link
        href={`/comparisons?season=${row.configuration.season}`}
        prefetch={false}
      >
        Back to Saved Comparisons
      </Link>
    </EmptyState>
  );
}
