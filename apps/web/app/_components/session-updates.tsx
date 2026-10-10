"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import type { RaceSession } from "../_lib/contracts";

export function SessionUpdates({ session }: { session: RaceSession }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const updates = session.updates;
  if (!updates || updates.data_status === "not_tracked") return null;
  if (updates.data_status === "finalized")
    return <p className="section-note">Finalized session data.</p>;
  return (
    <div aria-label="Session data status">
      <p className="section-note" role="status">
        <strong>
          {session.status === "cancelled"
            ? "Session cancelled"
            : updates.live_active
              ? "Live session"
              : session.status === "completed"
                ? "Final update pending"
                : "Session updates pending"}{" "}
          · Provisional data.
        </strong>{" "}
        Records may be incomplete or corrected; this is not a final
        classification.
        {updates.live_updated_at && (
          <>
            {" "}
            Last refreshed:{" "}
            <time dateTime={updates.live_updated_at}>
              {new Date(updates.live_updated_at)
                .toISOString()
                .replace("T", " ")
                .slice(0, 19)}{" "}
              UTC
            </time>
            .
          </>
        )}
        {updates.live_suspended && (
          <>
            {" "}
            Live updates are temporarily unavailable. Recorded data remains
            available; the final update is still pending.
          </>
        )}
      </p>
      <button
        className="button button-quiet"
        type="button"
        disabled={pending}
        onClick={() => startTransition(() => router.refresh())}
      >
        {pending ? "Refreshing session data…" : "Refresh session data"}
      </button>
    </div>
  );
}
