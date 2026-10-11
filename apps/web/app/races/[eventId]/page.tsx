import type { Metadata } from "next";
import Link from "next/link";
import { SessionUpdates } from "../../_components/session-updates";
import { ReferenceActions } from "../../_components/reference-actions";
import { Pitwall } from "../../_components/pitwall";
import { suggestedQuestions } from "../../_lib/pitwall";
import { redirect } from "next/navigation";
import type { SearchParams } from "../../_lib/contracts";
import { sessionNames } from "../../_lib/contracts";
import {
  circuitDetail,
  raceContext,
  resultNames,
  sessionResults,
} from "../../_lib/data";
import { formatSchedule, single } from "../../_lib/format";
import { replayHref } from "../../_lib/replay";
import { ResultsTable } from "../../_components/tables";
import {
  EmptyState,
  PageHeading,
  SectionHeading,
  Status,
  SeasonSelector,
} from "../../_components/ui";
export const metadata: Metadata = { title: "Race weekend" };
export default async function RacePage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ eventId }, query] = await Promise.all([params, searchParams]);
  const { event, sessions, seasons, season, selected } = await raceContext(
    eventId,
    query,
  );
  if (season && single(query.season) === undefined) {
    const canonical = new URLSearchParams({ season: String(season.year) });
    if (single(query.session)) canonical.set("session", single(query.session)!);
    redirect(`/races/${event.id}?${canonical}`);
  }
  const [circuit, results] = await Promise.all([
    circuitDetail(event.circuit_id),
    selected ? sessionResults(selected.id) : Promise.resolve([]),
  ]);
  const names = await resultNames(results);
  const replaySession =
    selected && ["race", "sprint"].includes(selected.type)
      ? selected
      : (sessions.find((session) => session.type === "race") ??
        sessions.find((session) => session.type === "sprint"));
  return (
    <>
      <Link
        className="back-link"
        href={`/races${season ? `?season=${season.year}` : ""}`}
        prefetch={false}
      >
        Back to race weekends
      </Link>
      <PageHeading
        title={event.name}
        intro={`${circuit.name} · ${circuit.country}`}
      >
        <SeasonSelector
          seasons={seasons}
          selected={season ?? null}
          action="/races"
        />
      </PageHeading>
      <nav className="race-actions" aria-label="Race weekend actions">
        <a className="back-link" href="#pitwall">
          Ask Pitwall about this weekend
        </a>
        {replaySession && (
          <Link
            className="back-link"
            href={replayHref(event.id, season?.year, replaySession.id)}
            prefetch={false}
          >
            Open race replay
          </Link>
        )}
        {sessions.find(
          (session) =>
            session.type === "race" && session.status === "completed",
        ) && (
          <Link
            className="back-link"
            href={`/strategy?${season ? `season=${season.year}&` : ""}event=${event.id}`}
            prefetch={false}
          >
            Explore race strategy and tyres
          </Link>
        )}
      </nav>
      {season && (
        <ReferenceActions
          reference={{
            reference_type: "event",
            reference_id: event.id,
            season: season.year,
          }}
          returnTo={`/races/${event.id}?season=${season.year}${selected ? `&session=${selected.id}` : ""}`}
        />
      )}
      <dl className="facts">
        <div>
          <dt>Season</dt>
          <dd>{season?.year ?? "Not available"}</dd>
        </div>
        <div>
          <dt>Round</dt>
          <dd>{event.round}</dd>
        </div>
        <div>
          <dt>Race schedule</dt>
          <dd>
            <time
              dateTime={event.starts_at ?? event.scheduled_date ?? undefined}
            >
              {formatSchedule(event)}
            </time>
          </dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>{circuit.locality ?? "Not available"}</dd>
        </div>
      </dl>
      <section>
        <SectionHeading title="Weekend schedule" />
        <p className="section-note">
          Times are shown in UTC. Session status comes from the recorded data.
        </p>
        {sessions.length ? (
          <ol className="schedule-list">
            {sessions.map((session) => (
              <li key={session.id}>
                <h3>{sessionNames[session.type]}</h3>
                <time
                  dateTime={
                    session.starts_at ?? session.scheduled_date ?? undefined
                  }
                >
                  {formatSchedule(session)}
                </time>
                <Status value={session.status} />
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState title="Schedule not available">
            <p>No session records have been imported for this weekend.</p>
          </EmptyState>
        )}
      </section>
      <section id="results">
        <SectionHeading title="Session results" />
        {sessions.length > 0 && (
          <nav className="session-nav" aria-label="Choose a session">
            {sessions.map((session) => (
              <Link
                key={session.id}
                href={`/races/${event.id}?season=${season?.year}&session=${session.id}#results`}
                prefetch={false}
                aria-current={selected?.id === session.id ? "page" : undefined}
              >
                {sessionNames[session.type]}
              </Link>
            ))}
          </nav>
        )}
        {selected && (
          <div className="section-heading">
            <h3>{sessionNames[selected.type]}</h3>
            <Status value={selected.status} />
          </div>
        )}
        {selected && <SessionUpdates session={selected} />}
        {selected && season && (
          <ReferenceActions
            reference={{
              reference_type: "session",
              reference_id: selected.id,
              season: season.year,
            }}
            returnTo={`/races/${event.id}?season=${season.year}&session=${selected.id}#results`}
          />
        )}
        {results.length > 0 && selected ? (
          <>
            <ResultsTable
              results={results}
              {...names}
              type={selected.type}
              year={season?.year}
            />
            {selected.type === "qualifying" && (
              <p className="section-note">
                Qualifying classification is available. Individual qualifying
                lap times are not included in these records.
              </p>
            )}
          </>
        ) : (
          <EmptyState title="Results not available">
            {selected &&
            !["race", "qualifying", "sprint"].includes(selected.type) ? (
              <p>
                Practice and sprint qualifying classifications are not available
                here. Choose race, qualifying or sprint to view classifications.
              </p>
            ) : (
              <p>
                No classification has been imported for{" "}
                {selected
                  ? sessionNames[selected.type].toLowerCase()
                  : "this weekend"}
                . Choose another session or check back after results have been
                added.
              </p>
            )}
          </EmptyState>
        )}
      </section>
      <Pitwall
        context={{
          route: `/races/${event.id}`,
          event_id: event.id,
          ...(selected ? { session_id: selected.id } : {}),
          ...(season ? { season: season.year } : {}),
        }}
        label={`${season ? `${season.year} · ` : ""}${event.name}`}
        contextDetails={[
          {
            label: "Session",
            value: selected
              ? sessionNames[selected.type]
              : "No session selected",
          },
        ]}
        names={Object.fromEntries(
          [...names.drivers].map(([id, row]) => [
            id,
            `${row.given_name} ${row.family_name}`,
          ]),
        )}
        suggestions={suggestedQuestions({
          page: "race",
          hasSession: Boolean(selected),
          hasResults: results.length > 0,
        })}
      />
    </>
  );
}
