import type { Metadata } from "next";
import Link from "next/link";
import {
  PageHeading,
  EmptyState,
  SeasonSelector,
} from "../../../_components/ui";
import { SessionUpdates } from "../../../_components/session-updates";
import { RaceReplay } from "../../../_components/race-replay";
import { Pitwall } from "../../../_components/pitwall";
import { suggestedQuestions } from "../../../_lib/pitwall";
import { raceContext } from "../../../_lib/data";
import { getSessionReplay } from "../../../_lib/api";
import type { SearchParams } from "../../../_lib/contracts";
import { sessionNames } from "../../../_lib/contracts";
import type { SessionReplay } from "../../../_lib/replay-contracts";
import { replayHref } from "../../../_lib/replay";
import "./replay.css";

export const metadata: Metadata = { title: "Recorded race replay" };
export default async function ReplayPage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ eventId }, query] = await Promise.all([params, searchParams]);
  const {
    event,
    sessions,
    seasons,
    season,
    selected: session,
  } = await raceContext(eventId, query);
  const replay = session
    ? await getSessionReplay<SessionReplay>(session.id)
    : null;
  const year = season?.year ?? replay?.season;
  return (
    <>
      <Link
        className="back-link"
        href={`/races/${event.id}?${new URLSearchParams({ ...(year !== undefined ? { season: String(year) } : {}), ...(session ? { session: session.id } : {}) })}`}
        prefetch={false}
      >
        Back to {event.name}
      </Link>
      <PageHeading
        title="Recorded race replay"
        intro={`${year !== undefined ? `${year} · ` : ""}${event.name}${session ? ` · ${sessionNames[session.type]}` : ""}`}
      >
        <SeasonSelector
          seasons={seasons}
          selected={season ?? null}
          action="/races"
        />
      </PageHeading>
      <nav className="session-nav" aria-label="Replay session">
        {sessions
          .filter((row) => ["race", "sprint"].includes(row.type))
          .map((row) => (
            <Link
              key={row.id}
              href={replayHref(event.id, year, row.id)}
              aria-current={row.id === session?.id ? "page" : undefined}
              prefetch={false}
            >
              {sessionNames[row.type]}
            </Link>
          ))}
      </nav>
      {replay && <SessionUpdates session={replay.session} />}
      {replay?.provisional && replay.capability === "unavailable" && (
        <p className="section-note">
          <strong>Provisional session data.</strong> Replay coverage is not
          sufficient yet; recorded updates may still be corrected. This is not
          final race classification.
        </p>
      )}
      {!replay ? (
        <EmptyState title="Race session unavailable">
          <p>
            No session records have been imported for this weekend. Return to
            race detail to view available core records.
          </p>
        </EmptyState>
      ) : replay.capability === "unavailable" ? (
        <EmptyState title="Replay unavailable">
          <p>
            {session && !["race", "sprint"].includes(session.type)
              ? "Recorded order replay supports race and sprint sessions only."
              : "This session does not have sufficient overlapping recorded order samples for multiple drivers. Historical results alone cannot provide replay."}
          </p>
          <p>
            Race results and other imported session data remain available from
            the race weekend.
          </p>
        </EmptyState>
      ) : (
        <>
          <p className="section-note">
            <strong>
              {replay.capability === "partial"
                ? "Partial / approximate replay"
                : "Recorded order replay available"}
              {replay.provisional ? " · Provisional data" : ""}.
            </strong>{" "}
            {replay.provisional
              ? "This snapshot may be corrected and is not final classification. Refresh session data to load a newer snapshot."
              : "Playback covers the recorded sample window, which may not be the full session."}
          </p>
          <details className="replay-quality">
            <summary>Source and replay quality</summary>
            <p className="section-note">
              Normalized recorded session data. Order and timestamps are source
              values; elapsed time, sample selection and playback holds are
              deterministic calculations. Track coordinates and retirement state
              are unavailable.
            </p>
            <p className="section-note">
              Source:{" "}
              {replay.provider === "openf1"
                ? "OpenF1"
                : "Recorded application data"}
              . Sample window:{" "}
              {replay.starts_at && (
                <time dateTime={replay.starts_at}>
                  {replay.starts_at
                    .replace("T", " ")
                    .replace("+00:00", " UTC")
                    .replace("Z", " UTC")}
                </time>
              )}{" "}
              to{" "}
              {replay.ends_at && (
                <time dateTime={replay.ends_at}>
                  {replay.ends_at
                    .replace("T", " ")
                    .replace("+00:00", " UTC")
                    .replace("Z", " UTC")}
                </time>
              )}
              .
            </p>
            <ul>
              {replay.quality.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
          <RaceReplay
            key={`${session!.id}:${replay.ends_at}`}
            replay={replay}
          />
        </>
      )}
      <Pitwall
        context={{
          route: `/races/${event.id}`,
          event_id: event.id,
          ...(year !== undefined ? { season: year } : {}),
          ...(session ? { session_id: session.id } : {}),
        }}
        label={`${year !== undefined ? `${year} · ` : ""}${event.name}`}
        contextDetails={[
          {
            label: "Session",
            value: session ? sessionNames[session.type] : "No session selected",
          },
        ]}
        names={Object.fromEntries(
          (replay?.drivers ?? []).map(({ driver }) => [
            driver.id,
            `${driver.given_name} ${driver.family_name}`,
          ]),
        )}
        suggestions={suggestedQuestions({
          page: "race",
          hasSession: Boolean(session),
          hasResults: false,
        })}
      />
    </>
  );
}
