import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { SessionUpdates } from "../_components/session-updates";
import { Pitwall } from "../_components/pitwall";
import { suggestedQuestions } from "../_lib/pitwall";
import { ApiError, getList, postEntity } from "../_lib/api";
import type { Driver, SearchPageProps } from "../_lib/contracts";
import { sessionNames, statusNames } from "../_lib/contracts";
import {
  eventSessions,
  references,
  seasonContext,
  seasonEvents,
} from "../_lib/data";
import { driverName, single } from "../_lib/format";
import { comparisonRequest } from "../_lib/telemetry";
import type { Comparison, Lap } from "../_lib/telemetry-contracts";
import {
  EmptyState,
  NoSeason,
  PageHeading,
  SeasonSelector,
  SectionHeading,
} from "../_components/ui";
import { CompareForm } from "./compare-form";
import { ComparisonView } from "./comparison-view";
import { SaveComparison } from "../_components/save-comparison";
import { accountState } from "../_lib/auth-api";
import { telemetryPreset } from "../_lib/saved-comparisons";
import "./telemetry.css";

export const metadata: Metadata = { title: "Telemetry Lab" };

export default async function TelemetryPage({ searchParams }: SearchPageProps) {
  const query = await searchParams;
  const account = await accountState();
  const returnTo = `/telemetry?${new URLSearchParams(
    Object.entries(query).flatMap(([key, value]) => {
      const item = single(value);
      return item === undefined ? [] : [[key, item]];
    }),
  )}`;
  const selected = Object.fromEntries(
    Object.entries(query).map(([key, value]) => [key, single(value)]),
  );
  const { seasons, season } = await seasonContext(query);
  const events = season ? await seasonEvents(season.year) : [];
  const event = events.find((row) => row.id === selected.event);
  if (season && selected.event && !event) notFound();
  const sessions = event ? await eventSessions(event.id) : [];
  const session = sessions.find((row) => row.id === selected.session);
  if (event && selected.session && !session) notFound();
  const laps = session ? await getList<Lap>(`sessions/${session.id}/laps`) : [];
  const driverMap = await references<Driver>(
    "drivers",
    laps.map((lap) => lap.driver_id),
  );
  const drivers = [...driverMap.values()].sort((a, b) =>
    driverName(a).localeCompare(driverName(b)),
  );
  let comparison: Comparison | null = null;
  let error: string | null = null;
  if (selected.compare === "1" && session) {
    const request = comparisonRequest(laps, selected);
    if (!request)
      error =
        "Choose two different recorded laps with matching drivers and a supported alignment, then compare again.";
    else {
      try {
        comparison = await postEntity<Comparison>("telemetry/compare", request);
      } catch (failure) {
        if (!(failure instanceof ApiError)) throw failure;
        error =
          failure.status === 404
            ? "A selected lap is no longer available. Choose another lap and compare again."
            : failure.status === 422
              ? "The API could not compare this selection. Choose another pair of laps and retry."
              : "The comparison service is temporarily unreachable. Retry with the Compare laps button.";
      }
    }
  }
  const selectedComparison =
    session && selected.compare === "1"
      ? comparisonRequest(laps, selected)
      : null;
  const chosenLaps = selectedComparison
    ? [selectedComparison.lap_a_id, selectedComparison.lap_b_id].map((id) =>
        laps.find((row) => row.id === id)!,
      )
    : [];
  const preset =
    event && session && season && comparison && selectedComparison
      ? telemetryPreset(
          { season: season.year, event_id: event.id, session_id: session.id },
          chosenLaps,
          selectedComparison,
        )
      : null;
  return (
    <>
      <PageHeading
        title="Telemetry Lab."
        intro="Two laps. A shared reference. Compare the recorded timing and channels."
      >
        <SeasonSelector seasons={seasons} selected={season} />
      </PageHeading>
      {event && session && (
        <a className="back-link" href="#pitwall">
          Ask Pitwall about this session
        </a>
      )}
      {session && <SessionUpdates session={session} />}
      {!season ? (
        <NoSeason />
      ) : (
        <>
          <section aria-label="Choose a session">
            <SectionHeading title="Choose a session" />
            <div className="telemetry-context">
              <form
                action="/telemetry"
                method="get"
                className="filter-form telemetry-filter"
              >
                <input type="hidden" name="season" value={season.year} />
                <div className="field">
                  <label htmlFor="event">Race weekend</label>
                  <select
                    id="event"
                    name="event"
                    defaultValue={event?.id ?? ""}
                    required
                    disabled={!events.length}
                  >
                    <option value="" disabled>
                      Choose a weekend
                    </option>
                    {events
                      .sort((a, b) => a.round - b.round)
                      .map((row) => (
                        <option key={row.id} value={row.id}>
                          Round {row.round} · {row.name}
                        </option>
                      ))}
                  </select>
                </div>
                <button
                  className="button button-quiet"
                  type="submit"
                  disabled={!events.length}
                >
                  Load weekend
                </button>
              </form>
              {event && sessions.length > 0 && (
                <form
                  action="/telemetry"
                  method="get"
                  className="filter-form telemetry-filter"
                >
                  <input type="hidden" name="season" value={season.year} />
                  <input type="hidden" name="event" value={event.id} />
                  <div className="field">
                    <label htmlFor="session">Session</label>
                    <select
                      id="session"
                      name="session"
                      defaultValue={session?.id ?? ""}
                      required
                    >
                      <option value="" disabled>
                        Choose a session
                      </option>
                      {sessions.map((row) => (
                        <option key={row.id} value={row.id}>
                          {sessionNames[row.type]} · {statusNames[row.status]}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button className="button button-quiet" type="submit">
                    Load laps
                  </button>
                </form>
              )}
            </div>
            {event && (
              <p className="section-note">
                <Link
                  href={`/races/${event.id}?season=${season.year}${session ? `&session=${session.id}` : ""}`}
                  prefetch={false}
                >
                  {event.name}
                </Link>
                {session &&
                  ` · ${sessionNames[session.type]} · ${statusNames[session.status]}`}
              </p>
            )}
          </section>
          {!events.length ? (
            <EmptyState title="No weekends in this season">
              <p>Choose another imported season to find a session.</p>
            </EmptyState>
          ) : !event ? (
            <EmptyState title="Start with a race weekend">
              <p>Choose a weekend, then a session with imported lap data.</p>
            </EmptyState>
          ) : !sessions.length ? (
            <EmptyState title="No session records">
              <p>
                This weekend has no imported sessions. Choose another weekend.
              </p>
            </EmptyState>
          ) : !session ? (
            <EmptyState title="Choose a session to load laps">
              <p>
                Lap records and available drivers will appear after you load a
                session.
              </p>
            </EmptyState>
          ) : laps.length < 2 ? (
            <EmptyState title="Not enough recorded laps">
              <p>
                {laps.length
                  ? "Only one lap is recorded."
                  : "No lap records have been imported for this session."}{" "}
                Choose another session or return after historical telemetry data
                has been imported. Core race results alone do not contain
                telemetry.
              </p>
            </EmptyState>
          ) : (
            <section aria-label="Select comparison laps">
              <SectionHeading title="Select your laps" />
              <CompareForm
                key={`${session.id}:${JSON.stringify(selected)}`}
                laps={laps}
                drivers={drivers}
                context={{
                  season: season.year,
                  event: event.id,
                  session: session.id,
                }}
                selected={selected}
              />
            </section>
          )}
          <section id="comparison" aria-label="Lap comparison result">
            {preset && (
              <SaveComparison
                key={JSON.stringify(preset)}
                preset={preset}
                signedIn={!!account.user}
                authUnavailable={!!account.error}
                returnTo={returnTo}
                suggestedTitle={`${season.year} ${event!.name} · Laps ${chosenLaps[0].lap_number} / ${chosenLaps[1].lap_number}`}
              />
            )}
            {error ? (
              <div className="empty-state" role="alert">
                <h2>Comparison unavailable</h2>
                <p className="muted">{error}</p>
              </div>
            ) : comparison ? (
              <ComparisonView comparison={comparison} drivers={driverMap} />
            ) : session && laps.length >= 2 ? (
              <EmptyState title="Ready to compare">
                <p>
                  Select Driver A and Driver B, choose their laps, and press
                  Compare laps. No telemetry is shown until a comparison has
                  been requested.
                </p>
              </EmptyState>
            ) : null}
          </section>
        </>
      )}
      {event && session && season && (
        <Pitwall
          context={{
            route: "/telemetry",
            season: season.year,
            event_id: event.id,
            session_id: session.id,
            ...(selectedComparison
              ? {
                  comparison: selectedComparison,
                  lap_id: selectedComparison.lap_a_id,
                  allow_approximate: selectedComparison.allow_approximate,
                }
              : {}),
          }}
          label={`${season.year} · ${event.name}`}
          contextDetails={[
            {
              label: "Session",
              value: `${sessionNames[session.type]} · ${statusNames[session.status]}`,
            },
            ...chosenLaps.map((lap, index) => ({
              label: `Lap ${index === 0 ? "A" : "B"}`,
              value: `${driverName(driverMap.get(lap.driver_id)!)} · Lap ${lap.lap_number}`,
            })),
            ...(!chosenLaps.length
              ? [
                  {
                    label: "Laps",
                    value: laps.length
                      ? "No comparison selected"
                      : "No recorded laps",
                  },
                ]
              : []),
          ]}
          names={Object.fromEntries(
            [...driverMap].map(([id, row]) => [id, driverName(row)]),
          )}
          suggestions={suggestedQuestions({
            page: "telemetry",
            hasLaps: laps.length > 0,
            comparison,
          })}
        />
      )}
    </>
  );
}
