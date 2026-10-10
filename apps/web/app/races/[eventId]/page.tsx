import type { Metadata } from "next";
import Link from "next/link";
import { SessionUpdates } from "../../_components/session-updates";
import { Pitwall } from "../../_components/pitwall";
import { suggestedQuestions } from "../../_lib/pitwall";
import { notFound, redirect } from "next/navigation";
import type { RaceEvent, SearchParams, Season } from "../../_lib/contracts";
import { sessionNames } from "../../_lib/contracts";
import { getList } from "../../_lib/api";
import {
  circuitDetail,
  detail,
  eventSessions,
  resultNames,
  sessionResults,
} from "../../_lib/data";
import { formatSchedule, single } from "../../_lib/format";
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
  const { eventId } = await params;
  const event = await detail<RaceEvent>("events", eventId);
  const [circuit, sessions, seasons, query] = await Promise.all([
    circuitDetail(event.circuit_id),
    eventSessions(event.id),
    getList<Season>("seasons"),
    searchParams,
  ]);
  const season = seasons.find((row) => row.id === event.season_id);
  if (
    season &&
    single(query.season) !== undefined &&
    single(query.season) !== String(season.year)
  )
    notFound();
  if (season && single(query.season) === undefined) {
    const canonical = new URLSearchParams({ season: String(season.year) });
    if (single(query.session)) canonical.set("session", single(query.session)!);
    redirect(`/races/${event.id}?${canonical}`);
  }
  const selectedId = single(query.session);
  const selected = selectedId
    ? sessions.find((session) => session.id === selectedId)
    : (sessions.find((session) => session.type === "race") ?? sessions[0]);
  if (selectedId && !selected) notFound();
  const results = selected ? await sessionResults(selected.id) : [];
  const names = await resultNames(results);
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
      <a className="back-link" href="#pitwall">
        Ask Pitwall about this weekend
      </a>
      {sessions.find(
        (session) => session.type === "race" && session.status === "completed",
      ) && (
        <Link
          className="back-link"
          href={`/strategy?${season ? `season=${season.year}&` : ""}event=${event.id}`}
          prefetch={false}
        >
          Explore race strategy and tyres
        </Link>
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
