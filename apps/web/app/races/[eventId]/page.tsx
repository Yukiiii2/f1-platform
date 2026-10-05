import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
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
      />
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
                href={`/races/${event.id}?session=${session.id}#results`}
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
    </>
  );
}
